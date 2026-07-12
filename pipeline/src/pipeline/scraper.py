"""Ingestion orchestrator: client -> discovery -> selection -> parser -> normalizer
-> change-detection -> loader.

Modes (§7): backfill / full_resync fetch every game; incremental fetches only selected
games (§7.3). Change detection (content_hash) decides load vs touch-last-fetched-only.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

import psycopg

from . import db, queries
from .client import MsportsClient
from .config import GRAPHQL_URL
from .discovery import DiscoveredSeason, discover_schedule, discover_seasons
from .normalizer import normalize_game
from .parser import parse_game
from .refresh import select_incremental
from .rosters import TeamRosterCache


@dataclass
class GameResult:
    game_id: str
    season_id: str
    is_ended: bool
    status: str  # loaded | unchanged | failed
    coverage: str  # full | partial | missing
    player_stat_rows: int
    parse_failures: int
    orphan_athletes: int
    fallback_athletes: int
    unknown_stat_terms: int
    points_mismatch: bool
    note: str = ""


@dataclass
class BackfillSummary:
    seasons: list[DiscoveredSeason]
    mode: str = "backfill"
    results: list[GameResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"


_URL_CREDENTIALS = re.compile(r"(postgres(?:ql)?://)[^@\s]+@", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+"
)


def _safe_error(exc: BaseException | str, limit: int = 300) -> str:
    """Return a concise error suitable for durable run notes."""
    text = str(exc).replace("\n", " ").strip()
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1=<redacted>", text)
    return text[:limit]


def _quality_issues(result: GameResult) -> list[str]:
    issues: list[str] = []
    if result.parse_failures:
        issues.append(f"parse_failures={result.parse_failures}")
    if result.orphan_athletes:
        issues.append(f"orphan_athletes={result.orphan_athletes}")
    if result.fallback_athletes:
        issues.append(f"fallback_athletes={result.fallback_athletes}")
    if result.unknown_stat_terms:
        issues.append(f"unknown_stat_terms={result.unknown_stat_terms}")
    if result.points_mismatch:
        issues.append("points_mismatch")
    if result.is_ended and result.coverage != "full":
        issues.append(f"ended_game_coverage={result.coverage}")
    return issues


def _summary_status(summary: BackfillSummary) -> str:
    if summary.errors or any(r.status == "failed" for r in summary.results):
        return "partial"
    if any(_quality_issues(r) for r in summary.results):
        return "partial"
    return "ok"


def _summary_notes(summary: BackfillSummary) -> str | None:
    failed = [
        {"game_id": r.game_id, "error": _safe_error(r.note)}
        for r in summary.results
        if r.status == "failed"
    ]
    quality = [
        {"game_id": r.game_id, "issues": _quality_issues(r)}
        for r in summary.results
        if r.status != "failed" and _quality_issues(r)
    ]
    payload = {
        "failed_count": len(failed),
        "quality_issue_count": len(quality),
        "failed_games": failed[:10],
        "quality_issues": quality[:10],
        "errors": [_safe_error(error, limit=200) for error in summary.errors[:10]],
    }
    if not failed and not quality and not summary.errors:
        return None
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _normalized_quality_issues(ng, coverage: str) -> list[str]:
    issues: list[str] = []
    if ng.parse_failures:
        issues.append(f"parse failures: {ng.parse_failures}")
    if ng.orphan_stat_athletes:
        issues.append(f"orphan stat athletes: {len(ng.orphan_stat_athletes)}")
    if ng.fallback_resolved_athletes:
        issues.append(f"roster fallback athletes: {len(ng.fallback_resolved_athletes)}")
    if ng.unknown_stat_terms:
        issues.append(f"unknown stat terms: {len(ng.unknown_stat_terms)}")
    if ng.points_mismatch:
        issues.append("official score does not match stat-derived points")
    if ng.is_ended and coverage != "full":
        issues.append(f"ended game has {coverage} box-score coverage")
    return issues


def _rollback_for_finalization(session: "db.Session") -> None:
    try:
        session.conn.rollback()
    except Exception:
        session.reset()


def _finalize_run(
    session: "db.Session",
    run_id: str,
    summary: BackfillSummary,
    status: str,
) -> None:
    db.finalize_scrape_run(
        session.conn,
        run_id,
        status=status,
        games_checked=len(summary.results),
        games_changed=sum(1 for r in summary.results if r.status == "loaded"),
        notes=_summary_notes(summary),
    )


def _seed_seasons(conn: psycopg.Connection, seasons: list[DiscoveredSeason]) -> None:
    with conn.cursor() as cur:
        for s in seasons:
            cur.execute(
                """
                INSERT INTO seasons (id, name, start_date, end_date, parent_league_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name, start_date = EXCLUDED.start_date,
                  end_date = EXCLUDED.end_date, parent_league_id = EXCLUDED.parent_league_id
                """,
                (s.id, s.name, s.start_date, s.end_date, s.parent_league_id),
            )
            cur.execute(
                """
                INSERT INTO divisions (id, season_id, name) VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET season_id = EXCLUDED.season_id, name = EXCLUDED.name
                """,
                (s.mens_division_id, s.id, s.mens_division_name),
            )
    conn.commit()


def completeness_gate(ng) -> tuple[bool, str]:
    """§7.6 gate (revised per approval): a snapshot is complete iff it has two team
    score nodes, a term dictionary, a roster, and a successful stats parse. The
    "periods present" check is intentionally dropped — a valid game can have 0 periods
    (e.g. a zero-event game). Reaching here means parsing already succeeded."""
    reasons = []
    if not ng.has_two_team_scores:
        reasons.append("missing two team score nodes")
    if not ng.has_terms:
        reasons.append("missing term dictionary")
    if ng.unknown_stat_terms:
        reasons.append(f"unknown stat terms ({len(ng.unknown_stat_terms)})")
    if not ng.has_roster:
        reasons.append("missing roster")
    return (len(reasons) == 0, "; ".join(reasons))


def _classify(ng) -> tuple[str, str]:
    # Coverage label on a LOADED game (gate already passed).
    if ng.player_stat_row_count >= 1:
        return "full", ""
    note = "no stat rows (upcoming/unplayed)" if not ng.is_ended else "zero-event game"
    return "partial", note


def _select(
    mode: str,
    schedule: list,
    existing: dict[str, dict],
    game_ids: set[str] | None,
) -> list:
    if game_ids is not None:
        return [g for g in schedule if g.id in game_ids]
    if mode == "incremental":
        return select_incremental(schedule, existing)
    return list(schedule)  # backfill / full_resync: every game


def run_ingest(
    mode: str = "backfill",
    season_ids: set[str] | None = None,
    game_ids: set[str] | None = None,
    progress: bool = True,
) -> BackfillSummary:
    client = MsportsClient()
    session = db.Session()
    summary: BackfillSummary | None = None
    run_id: str | None = None
    db_mode = {"backfill": "backfill", "incremental": "incremental", "full_resync": "full_resync"}.get(
        mode, mode
    )
    try:
        run_id = db.create_scrape_run(session.conn, db_mode)

        seasons = discover_seasons(client)
        if season_ids:
            seasons = [s for s in seasons if s.id in season_ids]
        _seed_seasons(session.conn, seasons)
        summary = BackfillSummary(seasons=seasons, mode=mode)
        roster_cache = TeamRosterCache(client)
        existing = db.get_existing_games(session.conn)  # change detection + selection

        for s in seasons:
            schedule = discover_schedule(client, s.mens_division_id)
            selected = _select(mode, schedule, existing, game_ids)
            if progress:
                print(
                    f"[{s.name}] {s.mens_division_id}: schedule={len(schedule)} "
                    f"selected={len(selected)} (mode={mode})",
                    file=sys.stderr,
                )
            for i, dg in enumerate(selected, 1):
                stored_hash = (existing.get(dg.id) or {}).get("content_hash")
                # Retry once on a dropped connection (transient pooler disconnect).
                for attempt in range(2):
                    try:
                        res = _process_game(
                            client, session, dg.id, s.id, roster_cache, stored_hash
                        )
                        break
                    except psycopg.OperationalError as exc:
                        session.reset()
                        if attempt == 1:
                            error = _safe_error(exc)
                            summary.errors.append(f"{dg.id}: connection lost: {error}")
                            res = GameResult(
                                game_id=dg.id, season_id=s.id, is_ended=False,
                                status="failed", coverage="missing", player_stat_rows=0,
                                parse_failures=0, orphan_athletes=0, fallback_athletes=0,
                                unknown_stat_terms=0, points_mismatch=False,
                                note=f"connection lost: {error}"[:200],
                            )
                summary.results.append(res)
                if progress and (i % 10 == 0 or i == len(selected)):
                    full = sum(1 for r in summary.results if r.coverage == "full")
                    print(f"  {s.name}: {i}/{len(selected)} (full={full})", file=sys.stderr)

        # Recompute standings for every season touched (§7.9). Always safe to recompute;
        # cheap and keeps the physical table consistent after any load.
        from .statcalc import recompute_standings

        for s in seasons:
            recompute_standings(session.conn, s.id)

        summary.status = _summary_status(summary)
        _finalize_run(session, run_id, summary, summary.status)
        return summary
    except Exception as exc:
        if summary is None:
            summary = BackfillSummary(seasons=[], mode=mode)
        summary.status = "failed"
        summary.errors.append(f"{type(exc).__name__}: {_safe_error(exc)}")
        if run_id is not None:
            _rollback_for_finalization(session)
            try:
                _finalize_run(session, run_id, summary, "failed")
            except Exception as finalize_exc:
                print(
                    "Failed to finalize scrape run "
                    f"{run_id}: {type(finalize_exc).__name__}: {_safe_error(finalize_exc)}",
                    file=sys.stderr,
                )
        raise
    finally:
        client.close()
        session.close()


def run_backfill(progress: bool = True) -> BackfillSummary:
    return run_ingest("backfill", progress=progress)


def _process_game(
    client: MsportsClient,
    session: "db.Session",
    game_id: str,
    season_id: str,
    roster_cache: TeamRosterCache,
    stored_hash: str | None = None,
) -> GameResult:
    variables = {"id": game_id}
    record_id: str | None = None
    try:
        payload, snapshot_path = client.fetch_and_snapshot(
            "Game", variables, queries.GAME_QUERY, f"game_{game_id}"
        )
        record_id = db.create_source_record(
            session.conn,
            source_url=GRAPHQL_URL,
            operation_name="Game",
            variables=variables,
            raw_snapshot_path=snapshot_path,
            entity_type="game",
            entity_id=game_id,
        )
        pg = parse_game(payload)
        team_ids = [s.teamId or (s.team.id if s.team else None) for s in pg.scores]
        team_ids = [t for t in team_ids if t]
        stat_athletes = {s.athleteId for s in pg.stats if s.athleteId}
        active = (
            roster_cache.resolve_active_plus(team_ids, pg.date.isoformat(), stat_athletes)
            if team_ids
            else None
        )
        ng = normalize_game(pg, active_members=active)

        # Completeness gate BEFORE any write: never replace good data with partial data.
        passed, gate_reasons = completeness_gate(ng)
        if not passed:
            db.set_load_status(session.conn, record_id, "failed")
            return GameResult(
                game_id=game_id,
                season_id=season_id,
                is_ended=ng.is_ended,
                status="failed",
                coverage="missing",
                player_stat_rows=ng.player_stat_row_count,
                parse_failures=ng.parse_failures,
                orphan_athletes=len(ng.orphan_stat_athletes),
                fallback_athletes=len(ng.fallback_resolved_athletes),
                unknown_stat_terms=len(ng.unknown_stat_terms),
                points_mismatch=ng.points_mismatch,
                note=f"completeness gate: {gate_reasons}",
            )

        coverage, note = _classify(ng)
        quality_issues = _normalized_quality_issues(ng, coverage)
        if quality_issues:
            note = "; ".join(filter(None, [note, *quality_issues]))
        load_status = "partial" if quality_issues else "loaded"

        # Change detection: identical normalized payload → only bump last_fetched_at,
        # write no normalized rows. Else load (delete-and-replace) + advance last_changed_at.
        if stored_hash is not None and stored_hash == ng.content_hash:
            db.touch_last_fetched(
                session.conn,
                game_id,
                record_id,
                load_status="partial" if quality_issues else "unchanged",
            )
            return GameResult(
                game_id=game_id,
                season_id=season_id,
                is_ended=ng.is_ended,
                status="unchanged",
                coverage=coverage,
                player_stat_rows=ng.player_stat_row_count,
                parse_failures=ng.parse_failures,
                orphan_athletes=len(ng.orphan_stat_athletes),
                fallback_athletes=len(ng.fallback_resolved_athletes),
                unknown_stat_terms=len(ng.unknown_stat_terms),
                points_mismatch=ng.points_mismatch,
                note=note,
            )

        from .loader import load_game

        load_game(session.conn, ng, record_id, changed=True, load_status=load_status)
        return GameResult(
            game_id=game_id,
            season_id=season_id,
            is_ended=ng.is_ended,
            status="loaded",
            coverage=coverage,
            player_stat_rows=ng.player_stat_row_count,
            parse_failures=ng.parse_failures,
            orphan_athletes=len(ng.orphan_stat_athletes),
            fallback_athletes=len(ng.fallback_resolved_athletes),
            unknown_stat_terms=len(ng.unknown_stat_terms),
            points_mismatch=ng.points_mismatch,
            note=note,
        )
    except psycopg.OperationalError:
        # Dropped connection — let run_backfill reconnect and retry this game.
        raise
    except Exception as exc:  # noqa: BLE001 — backfill continues past a single bad game
        try:
            if record_id is not None:
                db.set_load_status(session.conn, record_id, "failed")
            else:
                session.conn.rollback()
        except psycopg.OperationalError:
            session.reset()
        return GameResult(
            game_id=game_id,
            season_id=season_id,
            is_ended=False,
            status="failed",
            coverage="missing",
            player_stat_rows=0,
            parse_failures=0,
            orphan_athletes=0,
            fallback_athletes=0,
            unknown_stat_terms=0,
            points_mismatch=False,
            note=f"{type(exc).__name__}: {_safe_error(exc)}"[:200],
        )
