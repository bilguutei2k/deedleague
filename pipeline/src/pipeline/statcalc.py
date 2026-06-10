"""Stat-calculation layer (§8).

- A formula engine for the ONLY grammar observed in the two seasons: {TERM} references,
  integer literals, operators + - * /, parentheses. A referenced term absent from the
  atomic counts resolves to 0. Division by zero -> None (rendered as "—").
- recompute_standings: physical standings table from game_competitors (scores).
- Season aggregates for players/teams from game_player_stats.

SCORE-ONLY-GAME RULE (e.g. game c2dc8d65, where a team has a final score but no
per-player stats):
  * Standings / point-differential are computed from game_competitors (the official
    scores), so a score-only game COUNTS normally — the result is real, only the box
    score is missing.
  * Per-player / per-team STAT aggregates are computed from game_player_stats and count
    only "statted games" (games where that entity actually has stat rows), so a score-only
    game does NOT deflate any team's or player's per-game averages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

_TOKEN = re.compile(r"\s*(\{[A-Z0-9_]+\}|\d+\.?\d*|[()+\-*/])\s*")


@dataclass
class _Tok:
    kind: str  # 'num' | 'term' | 'op' | 'lpar' | 'rpar'
    value: str


def _tokenize(formula: str) -> list[_Tok]:
    toks: list[_Tok] = []
    pos = 0
    while pos < len(formula):
        m = _TOKEN.match(formula, pos)
        if not m:
            raise ValueError(f"unsupported token at {pos!r} in formula {formula!r}")
        pos = m.end()
        t = m.group(1)
        if t.startswith("{"):
            toks.append(_Tok("term", t[1:-1]))
        elif t in "+-*/":
            toks.append(_Tok("op", t))
        elif t == "(":
            toks.append(_Tok("lpar", t))
        elif t == ")":
            toks.append(_Tok("rpar", t))
        else:
            toks.append(_Tok("num", t))
    return toks


class FormulaEngine:
    """Evaluates a formula against atomic counts keyed by term uniqueName.
    Returns a float, or None if any division-by-zero occurs (propagated)."""

    def __init__(self, counts: dict[str, float]):
        self._counts = counts

    def evaluate(self, formula: str) -> float | None:
        self._toks = _tokenize(formula)
        self._i = 0
        val = self._expr()
        if self._i != len(self._toks):
            raise ValueError(f"trailing tokens in formula {formula!r}")
        return val

    def _peek(self) -> _Tok | None:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _expr(self) -> float | None:
        val = self._term()
        while (t := self._peek()) and t.kind == "op" and t.value in "+-":
            self._i += 1
            rhs = self._term()
            if val is None or rhs is None:
                val = None
            else:
                val = val + rhs if t.value == "+" else val - rhs
        return val

    def _term(self) -> float | None:
        val = self._factor()
        while (t := self._peek()) and t.kind == "op" and t.value in "*/":
            self._i += 1
            rhs = self._factor()
            if val is None or rhs is None:
                val = None
            elif t.value == "*":
                val = val * rhs
            else:  # division
                val = None if rhs == 0 else val / rhs
        return val

    def _factor(self) -> float | None:
        t = self._peek()
        if t is None:
            raise ValueError("unexpected end of formula")
        if t.kind == "num":
            self._i += 1
            return float(t.value)
        if t.kind == "term":
            self._i += 1
            return float(self._counts.get(t.value, 0))  # absent term -> 0
        if t.kind == "lpar":
            self._i += 1
            val = self._expr()
            if not (self._peek() and self._peek().kind == "rpar"):
                raise ValueError("missing closing paren")
            self._i += 1
            return val
        raise ValueError(f"unexpected token {t.value!r}")


def compute_derived(
    counts: dict[str, float], terms: list[dict]
) -> dict[str, float | None]:
    """Given atomic counts (uniqueName->value) and the term dictionary, return every
    derived term's value keyed by uniqueName. Percentages keep full precision; round at
    display time (one decimal, half-up)."""
    engine = FormulaEngine(counts)
    out: dict[str, float | None] = {}
    for t in terms:
        if t.get("formula"):
            out[t["unique_name"]] = engine.evaluate(t["formula"])
    return out


# ---------------------------------------------------------------------------
# Standings (physical table) — from game_competitors (scores). Score-only games count.
# ---------------------------------------------------------------------------

def recompute_standings(conn: psycopg.Connection, season_id: str) -> int:
    """Delete-and-replace this season's standings from decided games (points +
    is_winner present). Returns the number of team rows written."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM standings WHERE season_id = %s", (season_id,))
        cur.execute(
            """
            INSERT INTO standings (season_id, team_id, wins, losses, pct, pf, pa, diff)
            SELECT %s, d.team_id,
                   SUM((d.is_winner)::int)                                  AS wins,
                   SUM((NOT d.is_winner)::int)                              AS losses,
                   CASE WHEN COUNT(*) > 0
                        THEN ROUND(SUM((d.is_winner)::int)::numeric / COUNT(*), 3) END AS pct,
                   SUM(d.points)                                           AS pf,
                   SUM(d.opp)                                              AS pa,
                   SUM(d.points) - SUM(d.opp)                              AS diff
            FROM (
              SELECT gc.team_id, gc.is_winner, gc.points,
                     (SELECT o.points FROM game_competitors o
                      WHERE o.game_id = gc.game_id AND o.team_id <> gc.team_id) AS opp
              FROM game_competitors gc
              JOIN games g ON g.id = gc.game_id
              WHERE g.season_id = %s
                AND gc.points IS NOT NULL AND gc.is_winner IS NOT NULL
            ) d
            GROUP BY d.team_id
            """,
            (season_id, season_id),
        )
        n = cur.rowcount
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# Season aggregates — from game_player_stats; count only STATTED games.
# ---------------------------------------------------------------------------

def player_season_line(
    conn: psycopg.Connection, season_id: str, player_id: str
) -> dict:
    """A player's season totals + derived line, summing atomic counts over their
    statted games. games_played = distinct games with >=1 stat row for the player."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT st.unique_name, SUM(s.value)
            FROM game_player_stats s
            JOIN stat_terms st ON st.id = s.term_id
            JOIN games g ON g.id = s.game_id
            WHERE g.season_id = %s AND s.player_id = %s
            GROUP BY st.unique_name
            """,
            (season_id, player_id),
        )
        counts = {r[0]: float(r[1]) for r in cur.fetchall()}
        cur.execute(
            """
            SELECT COUNT(DISTINCT s.game_id)
            FROM game_player_stats s JOIN games g ON g.id = s.game_id
            WHERE g.season_id = %s AND s.player_id = %s
            """,
            (season_id, player_id),
        )
        games_played = cur.fetchone()[0]
        cur.execute(
            "SELECT id, unique_name, formula FROM stat_terms WHERE formula IS NOT NULL"
        )
        terms = [{"id": r[0], "unique_name": r[1], "formula": r[2]} for r in cur.fetchall()]
    derived = compute_derived(counts, terms)
    return {"games_played": games_played, "totals": counts, "derived": derived}


def rolling_point_diff(
    conn: psycopg.Connection, season_id: str, team_id: str
) -> list[tuple[str, int]]:
    """Cumulative point differential per game (chronological) for the chart — from
    game_competitors scores. Returns [(game_date, cumulative_diff)]."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.date::date,
                   gc.points - (SELECT o.points FROM game_competitors o
                                WHERE o.game_id = gc.game_id AND o.team_id <> gc.team_id) AS diff
            FROM game_competitors gc JOIN games g ON g.id = gc.game_id
            WHERE g.season_id = %s AND gc.team_id = %s AND gc.points IS NOT NULL
            ORDER BY g.date
            """,
            (season_id, team_id),
        )
        rows = cur.fetchall()
    out: list[tuple[str, int]] = []
    cum = 0
    for d, diff in rows:
        if diff is None:
            continue
        cum += diff
        out.append((str(d), cum))
    return out
