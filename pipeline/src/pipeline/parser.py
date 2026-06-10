"""Pydantic models for the raw Game payload + a tolerant parser.

Parsing is structural only; the §5 normalization semantics (counting, routing,
period bucketing) live in normalizer.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Athlete(BaseModel):
    id: str
    name: str | None = None
    surname: str | None = None
    image: str | None = None


class TeamRef(BaseModel):
    id: str
    name: str | None = None
    logo: str | None = None


class Term(BaseModel):
    id: str
    name: str | None = None
    shortName: str | None = None
    uniqueName: str | None = None
    formula: str | None = None
    registrable: bool | None = None
    showOnUser: bool | None = None
    isDefault: bool | None = None
    type: str | None = None
    order: int | None = None


class Period(BaseModel):
    id: str
    name: str | None = None
    current: bool | None = None
    order: int | None = None


class Score(BaseModel):
    id: str
    value: str | None = None
    isWinner: bool | None = None
    order: int
    competitorType: str | None = None
    teamId: str | None = None
    team: TeamRef | None = None
    athlete: Athlete | None = None


class Membership(BaseModel):
    id: str
    number: int | None = None
    position: str | None = None
    teamId: str
    athlete: Athlete


class StatTermRef(BaseModel):
    id: str
    uniqueName: str | None = None


class StatEvent(BaseModel):
    gameTime: int | None = None
    teamId: str | None = None
    athleteId: str | None = None
    periodId: str | None = None
    term: StatTermRef


class ParsedGame(BaseModel):
    id: str
    date: datetime
    isEnded: bool
    location: str | None = None
    divisionId: str
    division_name: str
    season_id: str
    season_name: str
    terms: list[Term]
    periods: list[Period]
    scores: list[Score]
    memberships: list[Membership]
    stats: list[StatEvent]
    # Stat nodes with neither athleteId nor teamId — recorded, never silently dropped.
    parse_failures: int = 0


def parse_game(raw_payload: dict[str, Any]) -> ParsedGame:
    """Parse a raw `{"data": {"game": {...}}}` payload into a ParsedGame."""
    game = (raw_payload or {}).get("data", {}).get("game")
    if not game:
        raise ValueError("payload has no data.game")

    division = game.get("division") or {}
    tournament = division.get("tournament") or {}

    def nodes(obj: Any, key: str) -> list[dict[str, Any]]:
        container = (obj or {}).get(key) or {}
        return container.get("nodes") or []

    stats_raw = nodes(game, "stats")
    parse_failures = sum(
        1 for s in stats_raw if not s.get("athleteId") and not s.get("teamId")
    )

    return ParsedGame(
        id=game["id"],
        date=game["date"],
        isEnded=bool(game["isEnded"]),
        location=game.get("location"),
        divisionId=game["divisionId"],
        division_name=division.get("name") or "",
        season_id=division.get("tournamentId") or tournament.get("id") or "",
        season_name=tournament.get("name") or "",
        terms=[Term(**t) for t in nodes(tournament, "terms")],
        periods=[Period(**p) for p in nodes(game, "periods")],
        scores=[Score(**s) for s in nodes(game, "scores")],
        memberships=[Membership(**m) for m in nodes(game, "memberships")],
        stats=[StatEvent(**s) for s in stats_raw],
        parse_failures=parse_failures,
    )
