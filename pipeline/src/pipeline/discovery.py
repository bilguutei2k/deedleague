"""Discovery: enumerate seasons -> men's divisions -> game schedule.

Enforces the §2 STOP rule: if the parent league exposes more (or different) child
seasons than the two approved ones, halt and report rather than scraping further.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import queries
from .client import MsportsClient
from .config import APPROVED_SEASON_IDS, MENS_DIVISION_NAME, PARENT_LEAGUE_ID


class SeasonDiscoveryStop(RuntimeError):
    """Raised when discovery finds seasons beyond the approved set (§2)."""


@dataclass
class DiscoveredSeason:
    id: str
    name: str
    start_date: str | None
    end_date: str | None
    parent_league_id: str | None
    mens_division_id: str
    mens_division_name: str


@dataclass
class DiscoveredGame:
    id: str
    date: str
    is_ended: bool
    division_id: str


def discover_seasons(client: MsportsClient) -> list[DiscoveredSeason]:
    payload = client.post_graphql(
        "LeagueChildren", {"id": PARENT_LEAGUE_ID}, queries.LEAGUE_CHILDREN_QUERY
    )
    league = payload["data"]["tournament"]
    children = league["children"]["nodes"]
    child_ids = {c["id"] for c in children}
    approved = set(APPROVED_SEASON_IDS)

    extra = child_ids - approved
    missing = approved - child_ids
    if extra:
        raise SeasonDiscoveryStop(
            f"Parent league {PARENT_LEAGUE_ID} exposes {len(children)} child seasons; "
            f"unapproved extra seasons present: {sorted(extra)}. "
            f"STOP per §2 — human review required before scraping beyond the approved two."
        )
    if missing:
        raise SeasonDiscoveryStop(
            f"Approved seasons not found under parent league: {sorted(missing)}. "
            f"Discovery returned {sorted(child_ids)}. STOP and report."
        )

    seasons: list[DiscoveredSeason] = []
    for sid in APPROVED_SEASON_IDS:
        sp = client.post_graphql("Season", {"id": sid}, queries.SEASON_QUERY)["data"][
            "tournament"
        ]
        divs = sp["divisions"]["nodes"]
        mens = next((d for d in divs if d["name"] == MENS_DIVISION_NAME), None)
        if not mens:
            raise SeasonDiscoveryStop(
                f"Season {sid} has no '{MENS_DIVISION_NAME}' division; found "
                f"{[d['name'] for d in divs]}. STOP and report."
            )
        seasons.append(
            DiscoveredSeason(
                id=sp["id"],
                name=sp["name"],
                start_date=sp.get("startDate"),
                end_date=sp.get("endDate"),
                parent_league_id=sp.get("parentId"),
                mens_division_id=mens["id"],
                mens_division_name=mens["name"],
            )
        )
    return seasons


def discover_schedule(client: MsportsClient, division_id: str) -> list[DiscoveredGame]:
    games: list[DiscoveredGame] = []
    take, skip = 200, 0
    while True:
        page = client.post_graphql(
            "Schedule",
            {"divisionId": division_id, "take": take, "skip": skip},
            queries.SCHEDULE_QUERY,
        )["data"]["games"]
        nodes = page["nodes"]
        for n in nodes:
            games.append(
                DiscoveredGame(
                    id=n["id"],
                    date=n["date"],
                    is_ended=bool(n["isEnded"]),
                    division_id=n["divisionId"],
                )
            )
        if len(nodes) < take or len(games) >= page["count"]:
            break
        skip += take
    return games
