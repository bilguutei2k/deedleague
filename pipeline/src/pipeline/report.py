"""Backfill reporting + DB-side golden validation (read-only)."""

from __future__ import annotations

import re
from collections import Counter

import psycopg

# Supported formula grammar (Step 1 finding): {TERM} refs, integer literals,
# operators + - * /, parentheses, whitespace. A referenced term absent from the
# recorded counts resolves to 0.
_FORMULA_TOKEN = re.compile(r"\s*(\{[A-Z0-9_]+\}|\d+|[()+\-*/])\s*")

GOLDEN_GAME = "44a47063-82c6-4c75-a096-074ca6bdb473"
GOLDEN_PLAYER = "f250ba30-e95e-4f3f-a6d0-95fd0cd9ef91"  # Justin "J.Moss" Moss
GOLDEN_EXPECTED = {"FGM": 18, "FGA": 26, "FG%": 69.2, "FTM": 12, "FTA": 17, "PTS": 48, "TOTRB": 8}


def coverage_counts(results) -> dict:
    cov = Counter(r.coverage for r in results)
    status = Counter(r.status for r in results)
    return {
        "total": len(results),
        "full": cov.get("full", 0),
        "partial": cov.get("partial", 0),
        "missing": cov.get("missing", 0),
        "loaded": status.get("loaded", 0),
        "failed": status.get("failed", 0),
        "points_mismatches": sum(1 for r in results if r.points_mismatch),
        "parse_failures": sum(r.parse_failures for r in results),
        "orphan_athletes": sum(r.orphan_athletes for r in results),
    }


def validate_golden_from_db(conn: psycopg.Connection) -> dict:
    """Recompute J.Moss's golden line from the loaded DB rows (sum across all
    period buckets including null), applying the derived-stat formulas."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT st.unique_name, COALESCE(SUM(gps.value), 0)
            FROM game_player_stats gps
            JOIN stat_terms st ON st.id = gps.term_id
            WHERE gps.game_id = %s AND gps.player_id = %s
            GROUP BY st.unique_name
            """,
            (GOLDEN_GAME, GOLDEN_PLAYER),
        )
        counts = {row[0]: int(row[1]) for row in cur.fetchall()}

    def c(u: str) -> int:
        return counts.get(u, 0)  # absent term => 0 (e.g. BSKT_1PTM)

    fgm = c("BSKT_2PTM") + c("BSKT_3PTM") + c("BSKT_1PTM")
    fga = c("BSKT_2PTA") + c("BSKT_3PTA") + c("BSKT_1PTA")
    fg = round(fgm * 100 / fga, 1) if fga else None
    ftm, fta = c("BSKT_FTM"), c("BSKT_FTA")
    pts = 2 * c("BSKT_2PTM") + 3 * c("BSKT_3PTM") + c("BSKT_FTM") + c("BSKT_1PTM")
    totrb = c("BSKT_RO") + c("BSKT_RD")
    got = {"FGM": fgm, "FGA": fga, "FG%": fg, "FTM": ftm, "FTA": fta, "PTS": pts, "TOTRB": totrb}
    return {"got": got, "expected": GOLDEN_EXPECTED, "pass": got == GOLDEN_EXPECTED}


def _formula_is_supported(formula: str) -> bool:
    """True iff `formula` is fully consumable by the supported grammar."""
    pos = 0
    while pos < len(formula):
        m = _FORMULA_TOKEN.match(formula, pos)
        if not m:
            return False
        pos = m.end()
    return True


def formula_support_check(conn: psycopg.Connection) -> dict:
    """Verify registrable->atomic/derived split and that every derived formula fits
    the supported grammar. Returns split violations + unsupported formulas."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, unique_name, short_name, registrable, formula FROM stat_terms"
        )
        rows = cur.fetchall()
    split_violations = []
    unsupported = []
    atomic = derived = 0
    for term_id, unique_name, short_name, registrable, formula in rows:
        has_formula = bool(formula)
        if has_formula:
            derived += 1
        else:
            atomic += 1
        # Hypothesis: registrable=true <=> atomic (no formula); registrable=false/None <=> derived.
        if bool(registrable) and has_formula:
            split_violations.append((unique_name or short_name, "registrable but has formula"))
        if not registrable and not has_formula:
            split_violations.append((unique_name or short_name, "not registrable but no formula"))
        if has_formula and not _formula_is_supported(formula):
            unsupported.append((unique_name or short_name, formula))
    return {
        "total": len(rows),
        "atomic": atomic,
        "derived": derived,
        "split_holds": len(split_violations) == 0,
        "split_violations": split_violations,
        "unsupported_formulas": unsupported,
    }


def standings_sanity_from_db(conn: psycopg.Connection, season_id: str, limit: int = 5) -> dict:
    """Lightweight W/L from game_competitors (NOT the computed standings table —
    that is Step 4). For the report only."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH decided AS (
              SELECT gc.team_id, gc.is_winner
              FROM game_competitors gc
              JOIN games g ON g.id = gc.game_id
              WHERE g.season_id = %s AND gc.points IS NOT NULL AND gc.is_winner IS NOT NULL
            )
            SELECT t.name,
                   SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN d.is_winner THEN 0 ELSE 1 END) AS losses
            FROM decided d JOIN teams t ON t.id = d.team_id
            GROUP BY t.name
            ORDER BY wins DESC, losses ASC
            """,
            (season_id,),
        )
        rows = [(r[0], int(r[1]), int(r[2])) for r in cur.fetchall()]
    return {"top": rows[:limit], "bottom": rows[-limit:]}
