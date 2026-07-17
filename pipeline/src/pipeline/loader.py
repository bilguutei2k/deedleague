"""Transactional per-game load (DML only). Drizzle owns the DDL.

Per §7.8: upsert dimensions; upsert game; delete-and-replace game-keyed facts
(competitors, rosters, player/team stats) so corrections overwrite cleanly with no
accumulation. load_status flips to 'loaded' as the final write inside the same
transaction, so it only becomes 'loaded' once the commit succeeds.
"""

from __future__ import annotations

import psycopg

from .normalizer import NormalizedGame


class TermConflictError(RuntimeError):
    """A stat_term id arrived with a different unique_name/formula/registrable
    than what is already stored (§6: fail rather than silently overwrite)."""


def _seed_season_min(cur: psycopg.Cursor, season: dict) -> None:
    # Per-game season touch: never null out start/end/parent seeded by discovery.
    cur.execute(
        """
        INSERT INTO seasons (id, name) VALUES (%s, %s)
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """,
        (season["id"], season["name"]),
    )


def _upsert_division(cur: psycopg.Cursor, division: dict) -> None:
    cur.execute(
        """
        INSERT INTO divisions (id, season_id, name) VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET season_id = EXCLUDED.season_id, name = EXCLUDED.name
        """,
        (division["id"], division["season_id"], division["name"]),
    )


def _upsert_teams(cur: psycopg.Cursor, teams: list[dict]) -> None:
    for t in teams:
        cur.execute(
            """
            INSERT INTO teams (id, name, logo) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, logo = EXCLUDED.logo
            """,
            (t["id"], t["name"], t["logo"]),
        )


def _upsert_players(cur: psycopg.Cursor, players: list[dict]) -> None:
    for p in players:
        cur.execute(
            """
            INSERT INTO players (id, name, surname, image) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, surname = EXCLUDED.surname, image = EXCLUDED.image
            """,
            (p["id"], p["name"] or "", p["surname"], p["image"]),
        )


def _upsert_terms(cur: psycopg.Cursor, terms: list[dict]) -> None:
    # §6 conflict guard: fail if (unique_name, formula, registrable) changes for an id.
    ids = [t["id"] for t in terms]
    existing: dict[str, tuple] = {}
    if ids:
        cur.execute(
            "SELECT id, unique_name, formula, registrable FROM stat_terms WHERE id = ANY(%s)",
            (ids,),
        )
        existing = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}
    for t in terms:
        incoming = (t["unique_name"], t["formula"], t["registrable"])
        if t["id"] in existing and existing[t["id"]] != incoming:
            raise TermConflictError(
                f"stat_term {t['id']} conflict: stored {existing[t['id']]} != incoming {incoming}"
            )
    for t in terms:
        cur.execute(
            """
            INSERT INTO stat_terms
              (id, unique_name, short_name, name, formula, registrable, term_type,
               order_index, show_on_user, is_default)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              unique_name = EXCLUDED.unique_name, short_name = EXCLUDED.short_name,
              name = EXCLUDED.name, formula = EXCLUDED.formula,
              registrable = EXCLUDED.registrable, term_type = EXCLUDED.term_type,
              order_index = EXCLUDED.order_index, show_on_user = EXCLUDED.show_on_user,
              is_default = EXCLUDED.is_default
            """,
            (
                t["id"], t["unique_name"], t["short_name"], t["name"], t["formula"],
                t["registrable"], t["term_type"], t["order_index"], t["show_on_user"],
                t["is_default"],
            ),
        )


def load_game(
    conn: psycopg.Connection,
    ng: NormalizedGame,
    source_record_id: str,
    *,
    changed: bool,
    load_status: str = "loaded",
) -> None:
    """Load one normalized game in a single transaction. Raises on failure
    (caller marks the source_record failed)."""
    try:
        with conn.cursor() as cur:
            _seed_season_min(cur, ng.season)
            _upsert_division(cur, ng.division)
            _upsert_teams(cur, ng.teams)
            _upsert_players(cur, ng.players)
            _upsert_terms(cur, ng.terms)

            # games upsert (+ hash/timestamps). last_changed_at advances only on change.
            cur.execute(
                """
                INSERT INTO games
                  (id, season_id, division_id, date, location, is_ended, content_hash,
                   last_fetched_at, last_changed_at, source_record_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now(), %s)
                ON CONFLICT (id) DO UPDATE SET
                  season_id = EXCLUDED.season_id, division_id = EXCLUDED.division_id,
                  date = EXCLUDED.date, location = EXCLUDED.location,
                  is_ended = EXCLUDED.is_ended, content_hash = EXCLUDED.content_hash,
                  last_fetched_at = now(),
                  last_changed_at = CASE WHEN %s THEN now() ELSE games.last_changed_at END,
                  source_record_id = EXCLUDED.source_record_id
                """,
                (
                    ng.game_id, ng.season["id"], ng.division["id"], ng.date, ng.location,
                    ng.is_ended, ng.content_hash, source_record_id, changed,
                ),
            )

            # delete-and-replace all game-keyed facts.
            for table in (
                "game_player_stats",
                "game_team_stats",
                "game_competitors",
                "game_rosters",
            ):
                cur.execute(f"DELETE FROM {table} WHERE game_id = %s", (ng.game_id,))

            for c in ng.competitors:
                cur.execute(
                    """
                    INSERT INTO game_competitors
                      (game_id, team_id, competitor_order, points, is_winner)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (ng.game_id, c.team_id, c.competitor_order, c.points, c.is_winner),
                )

            for r in ng.rosters:
                cur.execute(
                    "INSERT INTO game_rosters (game_id, player_id, team_id, number) "
                    "VALUES (%s, %s, %s, %s)",
                    (ng.game_id, r.player_id, r.team_id, r.number),
                )

            if ng.player_stats:
                cur.executemany(
                    """
                    INSERT INTO game_player_stats
                      (game_id, player_id, team_id, term_id, period_id, value, source_record_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (ng.game_id, pid, tid, term, per, val, source_record_id)
                        for (pid, tid, term, per, val) in ng.player_stats
                    ],
                )

            if ng.team_stats:
                cur.executemany(
                    """
                    INSERT INTO game_team_stats
                      (game_id, team_id, term_id, period_id, value, source_record_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (ng.game_id, tid, term, per, val, source_record_id)
                        for (tid, term, per, val) in ng.team_stats
                    ],
                )

            # Final write in the same transaction: 'loaded' commits atomically with data.
            cur.execute(
                "UPDATE source_records SET load_status = %s WHERE id = %s",
                (load_status, source_record_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
