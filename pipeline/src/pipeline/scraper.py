"""Ingestion orchestrator: client -> discovery -> selection -> parser -> normalizer
-> change-detection -> loader.

Modes (§7): backfill / full_resync fetch every game; incremental fetches only selected
games (§7.3). Change detection (content_hash) decides load vs touch-last-fetched-only.
"""

from __future__ import annotations

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
    points_mismatch: bool
    note: str = ""


@dataclass
class BackfillSummary:
    seasons: list[DiscoveredSeason]
    mode: str = "backfill"
    results: list[GameResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
        with session.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scrape_runs (mode, status) VALUES (%s, 'running') RETURNING id",
                (db_mode,),
            )
            run_id = str(cur.fetchone()[0])
        session.conn.commit()

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
                            summary.errors.append(f"{dg.id}: connection lost: {exc}")
                            res = GameResult(
                                game_id=dg.id, season_id=s.id, is_ended=False,
                                status="failed", coverage="missing", player_stat_rows=0,
                                parse_failures=0, orphan_athletes=0, points_mismatch=False,
                                note=f"connection lost: {exc}"[:200],
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

        checked = len(summary.results)
        changed = sum(1 for r in summary.results if r.status == "loaded")
        with session.conn.cursor() as cur:
            cur.execute(
                "UPDATE scrape_runs SET finished_at = now(), games_checked = %s, "
                "games_changed = %s, status = %s WHERE id = %s",
                (checked, changed, "ok" if not summary.errors else "partial", run_id),
            )
        session.conn.commit()
        return summary
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
                points_mismatch=ng.points_mismatch,
                note=f"completeness gate: {gate_reasons}",
            )

        coverage, note = _classify(ng)

        # Change detection: identical normalized payload → only bump last_fetched_at,
        # write no normalized rows. Else load (delete-and-replace) + advance last_changed_at.
        if stored_hash is not None and stored_hash == ng.content_hash:
            db.touch_last_fetched(session.conn, game_id, record_id)
            return GameResult(
                game_id=game_id,
                season_id=season_id,
                is_ended=ng.is_ended,
                status="unchanged",
                coverage=coverage,
                player_stat_rows=ng.player_stat_row_count,
                parse_failures=ng.parse_failures,
                orphan_athletes=len(ng.orphan_stat_athletes),
                points_mismatch=ng.points_mismatch,
                note=note,
            )

        from .loader import load_game

        load_game(session.conn, ng, record_id, changed=True)
        return GameResult(
            game_id=game_id,
            season_id=season_id,
            is_ended=ng.is_ended,
            status="loaded",
            coverage=coverage,
            player_stat_rows=ng.player_stat_row_count,
            parse_failures=ng.parse_failures,
            orphan_athletes=len(ng.orphan_stat_athletes),
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
            points_mismatch=False,
            note=f"{type(exc).__name__}: {exc}"[:200],
        )
