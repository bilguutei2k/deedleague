// Read layer — the only way the frontend touches data (server components call these).
// Derived stats are computed at read time from atomic counts via the formula engine.

import { sql } from "drizzle-orm";

import { db } from "../client";
import { BOX_COLUMNS, computeLine, type Term } from "./formula";
import {
  getLeaderEligibility,
  LEADER_CATEGORIES,
  type LeaderCategorySpec,
  type LeaderEligibility,
} from "./policy";
import { resolveSeasonId, type SeasonResolution } from "./season";

export * from "./formula";
export * from "./policy";
export * from "./season";

async function q<T = Record<string, unknown>>(query: ReturnType<typeof sql>): Promise<T[]> {
  const rows = await db.execute(query);
  return rows as unknown as T[];
}

// ---------------------------------------------------------------- terms / seasons

export async function getTerms(): Promise<Term[]> {
  return q<Term>(sql`
    SELECT id, unique_name AS "uniqueName", short_name AS "shortName", formula,
           registrable, show_on_user AS "showOnUser", order_index AS "orderIndex"
    FROM stat_terms ORDER BY order_index NULLS LAST`);
}

export type Season = { id: string; name: string; startDate: string | null; endDate: string | null };

export async function getSeasons(): Promise<Season[]> {
  return q<Season>(sql`
    SELECT id, name, start_date AS "startDate", end_date AS "endDate"
    FROM seasons ORDER BY start_date DESC NULLS LAST`);
}

export async function getCurrentSeasonId(): Promise<string | null> {
  const rows = await getSeasons();
  return resolveSeasonId(rows, undefined, process.env.CURRENT_SEASON_ID).seasonId;
}

export async function getSeasonContext(requested?: string): Promise<{
  seasons: Season[];
  resolution: SeasonResolution;
}> {
  const seasons = await getSeasons();
  return {
    seasons,
    resolution: resolveSeasonId(seasons, requested, process.env.CURRENT_SEASON_ID),
  };
}

// ---------------------------------------------------------------- standings

export type StandingRow = {
  teamId: string; name: string; wins: number; losses: number;
  pct: number | null; pf: number; pa: number; diff: number;
};

export async function getStandings(seasonId: string): Promise<StandingRow[]> {
  return q<StandingRow>(sql`
    SELECT st.team_id AS "teamId", t.name, st.wins, st.losses, st.pct, st.pf, st.pa, st.diff
    FROM standings st JOIN teams t ON t.id = st.team_id
    WHERE st.season_id = ${seasonId}
    ORDER BY st.pct DESC NULLS LAST, st.diff DESC`);
}

// ---------------------------------------------------------------- coverage badge

export type Coverage = { full: number; partial: number; lastUpdated: string | null };

export async function getCoverage(seasonId: string): Promise<Coverage> {
  // A competitor has a real box score iff it has points present AND either points=0 or
  // recorded made-shots (a team with a score but zero made-shots is a one-sided source
  // gap -> partial). full = both competitors box-score-complete; otherwise partial.
  // This intentionally reports only ingested records. Expected/missing games cannot be
  // calculated until schedule identities are persisted independently of loaded games.
  const rows = await q<{ ok_teams: number; n: number }>(sql`
    SELECT ok_teams, COUNT(*)::int AS n FROM (
      SELECT g.id,
        (SELECT COUNT(*) FROM game_competitors gc
         WHERE gc.game_id = g.id AND gc.points IS NOT NULL
           AND (gc.points = 0 OR EXISTS (
             SELECT 1 FROM game_player_stats s JOIN stat_terms st ON st.id = s.term_id
             WHERE s.game_id = g.id AND s.team_id = gc.team_id
               AND st.unique_name IN ('BSKT_2PTM','BSKT_3PTM','BSKT_FTM') AND s.value > 0
           ))) AS ok_teams
      FROM games g WHERE g.season_id = ${seasonId}
    ) x GROUP BY ok_teams`);
  let full = 0, partial = 0;
  for (const r of rows) {
    if (Number(r.ok_teams) >= 2) full += Number(r.n);
    else partial += Number(r.n);
  }
  const upd = await q<{ ts: string | null }>(sql`
    SELECT MAX(finished_at)::text AS ts FROM scrape_runs WHERE status IN ('ok','partial')`);
  return { full, partial, lastUpdated: upd[0]?.ts ?? null };
}

// ---------------------------------------------------------------- recent results

export type ResultRow = {
  gameId: string; date: string; aTeamId: string; aName: string; aPts: number | null;
  bTeamId: string; bName: string; bPts: number | null;
};

export async function getRecentResults(seasonId: string, limit = 10): Promise<ResultRow[]> {
  return q<ResultRow>(sql`
    SELECT g.id AS "gameId", g.date::text AS date,
      a.team_id AS "aTeamId", ta.name AS "aName", a.points AS "aPts",
      b.team_id AS "bTeamId", tb.name AS "bName", b.points AS "bPts"
    FROM games g
    JOIN game_competitors a ON a.game_id = g.id AND a.competitor_order = 0
    JOIN game_competitors b ON b.game_id = g.id AND b.competitor_order = 1
    JOIN teams ta ON ta.id = a.team_id
    JOIN teams tb ON tb.id = b.team_id
    WHERE g.season_id = ${seasonId} AND g.is_ended = true
      AND a.points IS NOT NULL AND b.points IS NOT NULL
    ORDER BY g.date DESC LIMIT ${limit}`);
}

// ---------------------------------------------------------------- leaders

export type LeaderRow = { playerId: string; name: string; surname: string | null; value: number; games: number; extra?: string };
export type LeaderCategory = { category: string; label: string; rows: LeaderRow[] };
export type Leaders = { categories: LeaderCategory[]; eligibility: LeaderEligibility };

async function weightedLeader(
  seasonId: string,
  spec: LeaderCategorySpec,
  minimumGames: number,
  limit: number,
): Promise<LeaderRow[]> {
  const valueExpression = sql.join(
    spec.terms.map(
      (term) => sql`CASE WHEN st.unique_name = ${term.uniqueName}
                         THEN s.value * ${term.weight} ELSE 0 END`,
    ),
    sql` + `,
  );

  // A recorded appearance is a player/game with any player-stat event. The source roster
  // is broader and does not distinguish DNPs from players who participated with zero in a
  // category. Category totals are therefore left-joined and zero-filled over appearances.
  return q<LeaderRow>(sql`
    WITH appearances AS (
      SELECT DISTINCT s.player_id, s.game_id
      FROM game_player_stats s
      JOIN games g ON g.id = s.game_id
      WHERE g.season_id = ${seasonId}
    ), category_by_game AS (
      SELECT s.player_id, s.game_id, SUM(${valueExpression})::numeric AS value
      FROM game_player_stats s
      JOIN stat_terms st ON st.id = s.term_id
      JOIN games g ON g.id = s.game_id
      WHERE g.season_id = ${seasonId}
      GROUP BY s.player_id, s.game_id
    )
    SELECT a.player_id AS "playerId", p.name, p.surname,
      ROUND(COALESCE(SUM(c.value), 0) / COUNT(*)::numeric, 1)::float AS value,
      COUNT(*)::int AS games
    FROM appearances a
    JOIN players p ON p.id = a.player_id
    LEFT JOIN category_by_game c ON c.player_id = a.player_id AND c.game_id = a.game_id
    GROUP BY a.player_id, p.name, p.surname
    HAVING COUNT(*) >= ${minimumGames}
    ORDER BY value DESC LIMIT ${limit}`);
}

export async function getLeaders(seasonId: string, limit = 5): Promise<Leaders> {
  const eligibility = getLeaderEligibility();
  const rows = await Promise.all(
    LEADER_CATEGORIES.map((spec) =>
      weightedLeader(seasonId, spec, eligibility.minimumGames, limit),
    ),
  );
  return {
    eligibility,
    categories: LEADER_CATEGORIES.map((spec, index) => ({
      category: spec.category,
      label: spec.label,
      rows: rows[index],
    })),
  };
}

// ---------------------------------------------------------------- team

export type TeamInfo = { id: string; name: string; logo: string | null };

export async function getTeam(teamId: string): Promise<TeamInfo | null> {
  const r = await q<TeamInfo>(sql`SELECT id, name, logo FROM teams WHERE id = ${teamId}`);
  return r[0] ?? null;
}

export async function getTeamStanding(teamId: string, seasonId: string): Promise<StandingRow | null> {
  const r = await q<StandingRow>(sql`
    SELECT st.team_id AS "teamId", t.name, st.wins, st.losses, st.pct, st.pf, st.pa, st.diff
    FROM standings st JOIN teams t ON t.id = st.team_id
    WHERE st.season_id = ${seasonId} AND st.team_id = ${teamId}`);
  return r[0] ?? null;
}

export type TeamGameRow = {
  gameId: string; date: string; oppId: string; oppName: string;
  teamPts: number | null; oppPts: number | null; isWinner: boolean | null;
};

export async function getTeamGames(teamId: string, seasonId: string): Promise<TeamGameRow[]> {
  return q<TeamGameRow>(sql`
    SELECT g.id AS "gameId", g.date::text AS date,
      o.team_id AS "oppId", ot.name AS "oppName",
      me.points AS "teamPts", o.points AS "oppPts", me.is_winner AS "isWinner"
    FROM games g
    JOIN game_competitors me ON me.game_id = g.id AND me.team_id = ${teamId}
    JOIN game_competitors o ON o.game_id = g.id AND o.team_id <> ${teamId}
    JOIN teams ot ON ot.id = o.team_id
    WHERE g.season_id = ${seasonId}
    ORDER BY g.date`);
}

export async function getTeamRoster(teamId: string, seasonId: string) {
  return q<{ playerId: string; name: string; surname: string | null; number: number | null; games: number }>(sql`
    SELECT r.player_id AS "playerId", p.name, p.surname,
      (ARRAY_AGG(r.number ORDER BY g.date DESC))[1] AS number,
      COUNT(DISTINCT a.game_id)::int AS games
    FROM game_rosters r JOIN games g ON g.id = r.game_id JOIN players p ON p.id = r.player_id
    LEFT JOIN (
      SELECT DISTINCT game_id, player_id, team_id FROM game_player_stats
    ) a ON a.game_id = r.game_id AND a.player_id = r.player_id AND a.team_id = r.team_id
    WHERE r.team_id = ${teamId} AND g.season_id = ${seasonId}
    GROUP BY r.player_id, p.name, p.surname
    ORDER BY games DESC, number NULLS LAST`);
}

export async function getTeamRollingDiff(teamId: string, seasonId: string): Promise<{ date: string; cum: number }[]> {
  const rows = await q<{ date: string; diff: number }>(sql`
    SELECT g.date::date::text AS date,
      (me.points - o.points) AS diff
    FROM games g
    JOIN game_competitors me ON me.game_id = g.id AND me.team_id = ${teamId}
    JOIN game_competitors o ON o.game_id = g.id AND o.team_id <> ${teamId}
    WHERE g.season_id = ${seasonId} AND me.points IS NOT NULL AND o.points IS NOT NULL
    ORDER BY g.date`);
  let cum = 0;
  return rows.map((r) => { cum += Number(r.diff); return { date: r.date, cum }; });
}

// ---------------------------------------------------------------- player

export type PlayerInfo = { id: string; name: string; surname: string | null; image: string | null };

export async function getPlayer(playerId: string): Promise<PlayerInfo | null> {
  const r = await q<PlayerInfo>(sql`SELECT id, name, surname, image FROM players WHERE id = ${playerId}`);
  return r[0] ?? null;
}

export async function getPlayerTeams(playerId: string, seasonId: string) {
  return q<{ teamId: string; name: string }>(sql`
    SELECT DISTINCT r.team_id AS "teamId", t.name
    FROM game_rosters r JOIN games g ON g.id = r.game_id JOIN teams t ON t.id = r.team_id
    WHERE r.player_id = ${playerId} AND g.season_id = ${seasonId}`);
}

// Player games are recorded appearances: any player-stat event in the game. This excludes
// roster-only/DNP records while retaining zeroes for categories with no event rows.
export async function getPlayerStatRows(playerId: string, seasonId: string) {
  return q<{ gameId: string; date: string; uniqueName: string; value: number }>(sql`
    SELECT s.game_id AS "gameId", g.date::text AS date, st.unique_name AS "uniqueName", SUM(s.value)::int AS value
    FROM game_player_stats s JOIN stat_terms st ON st.id = s.term_id JOIN games g ON g.id = s.game_id
    WHERE s.player_id = ${playerId} AND g.season_id = ${seasonId}
    GROUP BY s.game_id, g.date, st.unique_name
    ORDER BY g.date`);
}

export async function getPlayerSeasonLine(playerId: string, seasonId: string, terms: Term[]) {
  const rows = await getPlayerStatRows(playerId, seasonId);
  const totals: Record<string, number> = {};
  const games = new Set<string>();
  for (const r of rows) { totals[r.uniqueName] = (totals[r.uniqueName] ?? 0) + Number(r.value); games.add(r.gameId); }
  return { gamesPlayed: games.size, line: computeLine(totals, terms), totals };
}

export async function getPlayerGameLog(playerId: string, seasonId: string, terms: Term[]) {
  const rows = await getPlayerStatRows(playerId, seasonId);
  const byGame = new Map<string, { date: string; counts: Record<string, number> }>();
  for (const r of rows) {
    const g = byGame.get(r.gameId) ?? { date: r.date, counts: {} };
    g.counts[r.uniqueName] = Number(r.value);
    byGame.set(r.gameId, g);
  }
  return [...byGame.entries()].map(([gameId, g]) => ({
    gameId, date: g.date, line: computeLine(g.counts, terms),
  }));
}

// ---------------------------------------------------------------- game / box score

export async function getGame(gameId: string) {
  const r = await q<{
    id: string; date: string; isEnded: boolean; location: string | null;
    seasonId: string; seasonName: string; divisionName: string;
  }>(sql`
    SELECT g.id, g.date::text AS date, g.is_ended AS "isEnded", g.location,
      g.season_id AS "seasonId", se.name AS "seasonName", d.name AS "divisionName"
    FROM games g JOIN seasons se ON se.id = g.season_id JOIN divisions d ON d.id = g.division_id
    WHERE g.id = ${gameId}`);
  if (!r[0]) return null;
  const competitors = await q<{ teamId: string; name: string; order: number; points: number | null; isWinner: boolean | null }>(sql`
    SELECT gc.team_id AS "teamId", t.name, gc.competitor_order AS "order", gc.points, gc.is_winner AS "isWinner"
    FROM game_competitors gc JOIN teams t ON t.id = gc.team_id
    WHERE gc.game_id = ${gameId} ORDER BY gc.competitor_order`);
  return { ...r[0], competitors };
}

// Per-team box score: rostered players (incl. zero-stat) with computed lines.
export async function getBoxScore(gameId: string, terms: Term[]) {
  const roster = await q<{ playerId: string; teamId: string; name: string; surname: string | null; number: number | null }>(sql`
    SELECT r.player_id AS "playerId", r.team_id AS "teamId", p.name, p.surname, r.number
    FROM game_rosters r JOIN players p ON p.id = r.player_id WHERE r.game_id = ${gameId}`);
  const stats = await q<{ playerId: string; teamId: string; uniqueName: string; value: number }>(sql`
    SELECT s.player_id AS "playerId", s.team_id AS "teamId", st.unique_name AS "uniqueName", SUM(s.value)::int AS value
    FROM game_player_stats s JOIN stat_terms st ON st.id = s.term_id
    WHERE s.game_id = ${gameId} GROUP BY s.player_id, s.team_id, st.unique_name`);
  const countsByPlayer = new Map<string, Record<string, number>>();
  for (const s of stats) {
    const key = `${s.teamId}|${s.playerId}`;
    const c = countsByPlayer.get(key) ?? {};
    c[s.uniqueName] = Number(s.value);
    countsByPlayer.set(key, c);
  }
  const byTeam = new Map<string, { playerId: string; name: string; surname: string | null; number: number | null; line: Record<string, number | null> }[]>();
  for (const r of roster) {
    const counts = countsByPlayer.get(`${r.teamId}|${r.playerId}`) ?? {};
    const list = byTeam.get(r.teamId) ?? [];
    list.push({ playerId: r.playerId, name: r.name, surname: r.surname, number: r.number, line: computeLine(counts, terms) });
    byTeam.set(r.teamId, list);
  }
  // sort each team's players by PTS desc
  for (const list of byTeam.values()) {
    list.sort((a, b) => Number(b.line["BSKT_PTS"] ?? 0) - Number(a.line["BSKT_PTS"] ?? 0));
  }
  // team totals
  const teamTotals = new Map<string, Record<string, number>>();
  for (const s of stats) {
    const c = teamTotals.get(s.teamId) ?? {};
    c[s.uniqueName] = (c[s.uniqueName] ?? 0) + Number(s.value);
    teamTotals.set(s.teamId, c);
  }
  const totalsLine = new Map<string, Record<string, number | null>>();
  for (const [teamId, counts] of teamTotals) totalsLine.set(teamId, computeLine(counts, terms));
  return { byTeam, totalsLine };
}

export { BOX_COLUMNS };
