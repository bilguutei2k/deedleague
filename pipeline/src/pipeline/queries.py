"""GraphQL operations. The GAME_QUERY selection MUST stay in sync with the captured
golden fixture (pipeline/tests/fixtures/golden_game_44a47063.json) so the parser behaves
identically on live data and on the fixture."""

# Enumerate the parent league's child seasons (the season-count STOP check).
LEAGUE_CHILDREN_QUERY = """
query LeagueChildren($id: String!) {
  tournament(where: {id: $id}) {
    id name startDate endDate
    children(orderBy: {startDate: desc}) {
      count
      nodes { id name type startDate endDate parentId }
    }
  }
}
"""

# A single season tournament: divisions (to pick men's) + dates.
SEASON_QUERY = """
query Season($id: String!) {
  tournament(where: {id: $id}) {
    id name type startDate endDate parentId
    divisions { nodes { id name } }
  }
}
"""

# Schedule for a division (men's). Exposes id/date/isEnded — the §5 minimum.
SCHEDULE_QUERY = """
query Schedule($divisionId: String!, $take: Int!, $skip: Int!) {
  games(
    where: {divisionId: {equals: $divisionId}}
    orderBy: {date: asc}
    take: $take
    skip: $skip
  ) {
    count
    nodes { id date isEnded divisionId }
  }
}
"""

# All memberships for a team across time (with from/to windows). Used to resolve the
# as-of-date roster, since game.memberships returns only the CURRENT roster (§8 finding).
MEMBERSHIPS_BY_TEAM_QUERY = """
query MembershipsByTeam($teamId: String!) {
  memberships(where: {teamId: {equals: $teamId}}) {
    count
    nodes { id number from to teamId athlete { id name surname image } }
  }
}
"""

# The proven per-game query. Verbatim-anchored, extended with the ids/fields the
# normalizer needs. Player stat nodes carry NO teamId (team is derived from membership).
GAME_QUERY = """
query Game($id: String!) {
  game(where: {id: $id}) {
    id date isEnded location currentTime highlightUrl divisionId
    division {
      id name tournamentId
      tournament {
        id name
        terms(orderBy: {order: asc}) {
          nodes { id name shortName uniqueName formula registrable showOnUser isDefault type order }
        }
      }
    }
    periods(orderBy: {order: asc}) { nodes { id name current order } }
    scores(orderBy: {order: asc}) {
      nodes { id value isWinner order competitorType teamId team { id name logo } athlete { id name surname } }
    }
    memberships { nodes { id number position teamId athlete { id name surname image } } }
    stats { nodes { gameTime teamId athleteId periodId term { id uniqueName } } }
  }
}
"""
