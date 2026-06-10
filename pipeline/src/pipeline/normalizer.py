"""§5 normalization: turn a ParsedGame into normalized dimension + fact rows.

Key rules (validated in Step 1):
- Atomic grain: COUNT identical events; repeated events are real, never deduped.
- Player stat nodes carry NO teamId -> team is derived from the game's memberships.
- periodId null = a real "unknown-period" bucket, not a game-total row.
- Stat with neither athleteId nor teamId = parse failure (counted, not dropped).
- content_hash covers the full normalized persisted payload, excluding fetch ts/currentTime
  and raw event order/gameTime (we hash aggregated counts, not raw events).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

from .parser import ParsedGame


@dataclass
class Competitor:
    team_id: str
    competitor_order: int
    points: int | None
    is_winner: bool | None


@dataclass
class RosterEntry:
    player_id: str
    team_id: str
    number: int | None


@dataclass
class NormalizedGame:
    game_id: str
    season: dict
    division: dict
    teams: list[dict]
    players: list[dict]
    terms: list[dict]
    competitors: list[Competitor]
    rosters: list[RosterEntry]
    player_stats: list[tuple[str, str, str, str | None, int]]  # (player,team,term,period,value)
    team_stats: list[tuple[str, str, str | None, int]]  # (team,term,period,value)
    date: str
    location: str | None
    is_ended: bool
    content_hash: str
    # provenance / quality
    parse_failures: int
    orphan_stat_athletes: list[str]
    # coverage signals
    has_two_team_scores: bool
    has_score_values: bool
    has_roster: bool
    has_terms: bool
    player_stat_row_count: int
    # validation
    recomputed_points: dict[str, int]
    points_mismatch: bool


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return None


def normalize_game(pg: ParsedGame, active_members=None) -> NormalizedGame:
    """Normalize a parsed game. `active_members` (list of rosters.ActiveMember) is the
    §8 date-windowed roster; when None, the nested game.memberships roster is used
    (legacy / fixture path), preserving prior behavior."""
    # Teams come from the score nodes (carry id/name/logo).
    teams: dict[str, dict] = {}
    for s in pg.scores:
        if s.team and s.team.id:
            teams.setdefault(s.team.id, {"id": s.team.id, "name": s.team.name, "logo": s.team.logo})

    # --- Roster / team resolution (§8) ---
    # Nested game.memberships is the CURRENT roster: fallback + legacy/fixture path.
    nested_team: dict[str, str] = {}
    nested_meta: dict[str, dict] = {}
    for m in pg.memberships:
        a = m.athlete
        nested_team[a.id] = m.teamId
        nested_meta[a.id] = {
            "team_id": m.teamId, "number": m.number,
            "name": a.name, "surname": a.surname, "image": a.image,
        }
    # Primary = date-windowed active roster when supplied, else the nested roster.
    primary_team: dict[str, str] = {}
    primary_meta: dict[str, dict] = {}
    if active_members is not None:
        for am in active_members:
            primary_team[am.athlete_id] = am.team_id
            primary_meta[am.athlete_id] = {
                "team_id": am.team_id, "number": am.number,
                "name": am.name, "surname": am.surname, "image": am.image,
            }
    else:
        primary_team = dict(nested_team)
        primary_meta = dict(nested_meta)

    terms = [
        {
            "id": t.id,
            "unique_name": t.uniqueName,
            "short_name": t.shortName,
            "name": t.name,
            "formula": t.formula,
            "registrable": t.registrable,
            "term_type": t.type,
            "order_index": t.order,
            "show_on_user": t.showOnUser,
            "is_default": t.isDefault,
        }
        for t in pg.terms
    ]

    # Competitors (scores parse): order, points, winner. No home/away.
    competitors = [
        Competitor(
            team_id=s.teamId or (s.team.id if s.team else ""),
            competitor_order=s.order,
            points=_to_int(s.value),
            is_winner=s.isWinner,
        )
        for s in pg.scores
        if (s.teamId or (s.team and s.team.id))
    ]
    competitors.sort(key=lambda c: c.competitor_order)

    # Aggregate stat events into counts. Team is resolved from the primary (date-windowed)
    # roster, falling back to the nested current roster for any straggler.
    player_counter: Counter[tuple[str, str, str, str | None]] = Counter()
    team_counter: Counter[tuple[str, str, str | None]] = Counter()
    orphan_stat_athletes: set[str] = set()
    resolved_via_fallback: set[str] = set()
    for ev in pg.stats:
        term_id = ev.term.id
        period_id = ev.periodId  # None => unknown-period bucket
        if ev.athleteId:
            team_id = primary_team.get(ev.athleteId)
            if not team_id:
                team_id = nested_team.get(ev.athleteId)
                if team_id:
                    resolved_via_fallback.add(ev.athleteId)
            if not team_id:
                orphan_stat_athletes.add(ev.athleteId)
                continue
            player_counter[(ev.athleteId, team_id, term_id, period_id)] += 1
        elif ev.teamId:
            team_counter[(ev.teamId, term_id, period_id)] += 1
        # neither -> already counted as parse_failure in the parser

    player_stats = [
        (player_id, team_id, term_id, period_id, value)
        for (player_id, team_id, term_id, period_id), value in player_counter.items()
    ]
    team_stats = [
        (team_id, term_id, period_id, value)
        for (team_id, term_id, period_id), value in team_counter.items()
    ]

    # Roster rows = the as-of-date primary roster, plus any fallback-resolved players who
    # actually had events but were absent from it (so the box score still lists them).
    roster_meta: dict[str, dict] = dict(primary_meta)
    for aid in resolved_via_fallback:
        if aid not in roster_meta and aid in nested_meta:
            roster_meta[aid] = nested_meta[aid]
    rosters = [
        RosterEntry(player_id=aid, team_id=meta["team_id"], number=meta["number"])
        for aid, meta in roster_meta.items()
    ]
    # Players = everyone in the (final) roster; names/images live on the membership.
    players: dict[str, dict] = {
        aid: {"id": aid, "name": meta["name"], "surname": meta["surname"], "image": meta["image"]}
        for aid, meta in roster_meta.items()
    }

    # Lightweight PTS cross-check (validation only): 2PTM*2 + 3PTM*3 + FTM (+1PTM=0).
    un_by_id = {t.id: t.uniqueName for t in pg.terms}
    per_team_pts: dict[str, int] = defaultdict(int)
    for _player_id, team_id, term_id, _period, value in player_stats:
        un = un_by_id.get(term_id)
        if un == "BSKT_2PTM":
            per_team_pts[team_id] += 2 * value
        elif un == "BSKT_3PTM":
            per_team_pts[team_id] += 3 * value
        elif un == "BSKT_FTM":
            per_team_pts[team_id] += value
    recomputed_points = dict(per_team_pts)
    points_mismatch = False
    for c in competitors:
        if c.points is not None and c.team_id in recomputed_points:
            if recomputed_points[c.team_id] != c.points:
                points_mismatch = True

    # Coverage signals.
    has_two_team_scores = len(competitors) == 2
    has_score_values = bool(competitors) and all(c.points is not None for c in competitors)
    has_roster = len(rosters) > 0
    has_terms = len(terms) > 0

    # content_hash over the normalized persisted payload (sorted, deterministic).
    # Sort by a JSON-string key so rows containing None sort safely (None vs str is
    # not orderable in Python 3); the resulting order is stable across runs.
    def _sorted(rows: list) -> list:
        return sorted(rows, key=lambda r: json.dumps(r, ensure_ascii=False, default=str))

    canonical = {
        "id": pg.id,
        "date": pg.date.isoformat(),
        "location": pg.location,
        "is_ended": pg.isEnded,
        "season_id": pg.season_id,
        "division_id": pg.divisionId,
        "competitors": _sorted(
            [[c.competitor_order, c.team_id, c.points, c.is_winner] for c in competitors]
        ),
        "teams": _sorted([[t["id"], t["name"], t["logo"]] for t in teams.values()]),
        "players": _sorted(
            [[p["id"], p["name"], p["surname"], p["image"]] for p in players.values()]
        ),
        "terms": _sorted([[t["id"], t["unique_name"], t["formula"], t["registrable"]] for t in terms]),
        "rosters": _sorted([[r.player_id, r.team_id, r.number] for r in rosters]),
        "player_stats": _sorted([list(row) for row in player_stats]),
        "team_stats": _sorted([list(row) for row in team_stats]),
    }
    content_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return NormalizedGame(
        game_id=pg.id,
        season={"id": pg.season_id, "name": pg.season_name},
        division={"id": pg.divisionId, "season_id": pg.season_id, "name": pg.division_name},
        teams=list(teams.values()),
        players=list(players.values()),
        terms=terms,
        competitors=competitors,
        rosters=rosters,
        player_stats=player_stats,
        team_stats=team_stats,
        date=pg.date.isoformat(),
        location=pg.location,
        is_ended=pg.isEnded,
        content_hash=content_hash,
        parse_failures=pg.parse_failures,
        orphan_stat_athletes=sorted(orphan_stat_athletes),
        has_two_team_scores=has_two_team_scores,
        has_score_values=has_score_values,
        has_roster=has_roster,
        has_terms=has_terms,
        player_stat_row_count=len(player_stats),
        recomputed_points=recomputed_points,
        points_mismatch=points_mismatch,
    )
