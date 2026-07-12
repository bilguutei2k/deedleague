"""As-of-date roster resolution (§8 fix).

`game.memberships` returns each team's CURRENT roster, not the roster as of the game
date — so players who transferred after a game vanish from it and their stat events get
dropped. Instead we fetch each team's full membership history once (cached; only ~12
teams) and select the memberships whose [from, to] window covers the game date.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import queries
from .client import MsportsClient


@dataclass
class ActiveMember:
    athlete_id: str
    team_id: str
    number: int | None
    name: str | None
    surname: str | None
    image: str | None
    resolution: str = "active"


def _date10(value: str | None) -> str | None:
    return value[:10] if value else None


class TeamRosterCache:
    """Caches per-team membership history; resolves the active roster for a game date."""

    def __init__(self, client: MsportsClient) -> None:
        self._client = client
        self._by_team: dict[str, list[dict]] = {}

    def _memberships(self, team_id: str) -> list[dict]:
        if team_id not in self._by_team:
            payload = self._client.post_graphql(
                "MembershipsByTeam", {"teamId": team_id}, queries.MEMBERSHIPS_BY_TEAM_QUERY
            )
            self._by_team[team_id] = payload["data"]["memberships"]["nodes"]
        return self._by_team[team_id]

    def active_roster(self, team_ids: list[str], game_date_iso: str) -> list[ActiveMember]:
        """Memberships of the given teams whose window covers the game date
        (inclusive both ends; null `to` = still active). At most one row per
        (athlete, team) — the one with the latest `from` if several windows overlap."""
        d = _date10(game_date_iso)
        best: dict[tuple[str, str], dict] = {}
        for team_id in team_ids:
            for m in self._memberships(team_id):
                frm, to = _date10(m.get("from")), _date10(m.get("to"))
                if frm is None:
                    continue
                if frm <= d and (to is None or d <= to):
                    key = (m["athlete"]["id"], m["teamId"])
                    prev = best.get(key)
                    if prev is None or frm >= _date10(prev["from"]):
                        best[key] = m
        members = []
        for m in best.values():
            a = m["athlete"]
            members.append(
                ActiveMember(
                    athlete_id=a["id"],
                    team_id=m["teamId"],
                    number=m.get("number"),
                    name=a.get("name"),
                    surname=a.get("surname"),
                    image=a.get("image"),
                    resolution="fallback",
                )
            )
        return members

    def resolve_active_plus(
        self, team_ids: list[str], game_date_iso: str, stat_athlete_ids: set[str]
    ) -> list[ActiveMember]:
        """active_roster + a second tier for stat athletes the date-window misses:
        attribute them to whichever competing team they have ANY membership with.
        Handles source membership end-dates that contradict actual game participation
        (e.g. an import whose stint end-date is recorded a few days early)."""
        active = self.active_roster(team_ids, game_date_iso)
        covered = {am.athlete_id for am in active}
        d = _date10(game_date_iso)
        for aid in stat_athlete_ids:
            if aid in covered:
                continue
            candidates: list[tuple[str, dict]] = []
            for team_id in team_ids:
                for m in self._memberships(team_id):
                    if m["athlete"]["id"] == aid:
                        candidates.append((team_id, m))
            if not candidates:
                continue  # left to the nested fallback / orphan handling in the normalizer
            # Prefer a membership already started by the game date, then the latest start.
            def _rank(c: tuple[str, dict]) -> tuple[bool, str]:
                frm = _date10(c[1].get("from")) or ""
                return ((frm <= d) if d else False, frm)

            team_id, m = max(candidates, key=_rank)
            a = m["athlete"]
            active.append(
                ActiveMember(
                    athlete_id=aid,
                    team_id=team_id,
                    number=m.get("number"),
                    name=a.get("name"),
                    surname=a.get("surname"),
                    image=a.get("image"),
                )
            )
            covered.add(aid)
        return active
