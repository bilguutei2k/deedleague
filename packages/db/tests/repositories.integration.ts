import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import postgres from "postgres";

const testUrl = process.env.TEST_DATABASE_URL;

test(
  "repository appearance denominators and eligibility use PostgreSQL semantics",
  { skip: testUrl ? false : "TEST_DATABASE_URL is not configured" },
  async () => {
    assert.ok(testUrl);
    const admin = postgres(testUrl, { max: 1, prepare: false });
    let closeRepository: (() => Promise<void>) | undefined;
    let disposableConfirmed = false;
    try {
      const existing = await admin<{ tablename: string }[]>`
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
      `;
      assert.equal(existing.length, 0, "TEST_DATABASE_URL must point to an empty disposable database");
      disposableConfirmed = true;

      const migration = readFileSync(
        new URL("../drizzle/0000_init.sql", import.meta.url),
        "utf8",
      ).replaceAll("--> statement-breakpoint", "");
      await admin.unsafe(migration);

      await admin`
        INSERT INTO seasons (id, name) VALUES ('season', 'Season')
      `;
      await admin`
        INSERT INTO divisions (id, season_id, name) VALUES ('division', 'season', 'Men')
      `;
      await admin`
        INSERT INTO teams (id, name) VALUES ('team', 'Team')
      `;
      await admin`
        INSERT INTO players (id, name) VALUES
          ('qualified', 'Qualified'), ('tiny', 'Tiny sample'), ('dnp', 'Roster only')
      `;
      await admin`
        INSERT INTO stat_terms (id, unique_name, short_name, registrable) VALUES
          ('two-made', 'BSKT_2PTM', '2PM', true),
          ('off-rebound', 'BSKT_RO', 'OR', true),
          ('assist', 'BSKT_AS', 'AST', true)
      `;
      await admin`
        INSERT INTO games (id, season_id, division_id, date, is_ended) VALUES
          ('game-1', 'season', 'division', now(), true),
          ('game-2', 'season', 'division', now(), true),
          ('tiny-game', 'season', 'division', now(), true)
      `;
      await admin`
        INSERT INTO game_rosters (game_id, player_id, team_id) VALUES
          ('game-1', 'qualified', 'team'),
          ('game-2', 'qualified', 'team'),
          ('tiny-game', 'tiny', 'team'),
          ('game-1', 'dnp', 'team')
      `;
      await admin`
        INSERT INTO game_player_stats
          (game_id, player_id, team_id, term_id, period_id, value)
        VALUES
          ('game-1', 'qualified', 'team', 'assist', null, 1),
          ('game-1', 'qualified', 'team', 'assist', 'period-2', 1),
          ('game-2', 'qualified', 'team', 'two-made', null, 2),
          ('game-2', 'qualified', 'team', 'off-rebound', null, 2),
          ('tiny-game', 'tiny', 'team', 'off-rebound', null, 10)
      `;

      process.env.DATABASE_URL = testUrl;
      process.env.LEADER_MIN_GAMES = "2";
      const repositories = await import("../src/index");
      closeRepository = repositories.closeDb;

      const leaders = await repositories.getLeaders("season", 10);
      const points = leaders.categories.find((category) => category.category === "pts")?.rows;
      const rebounds = leaders.categories.find((category) => category.category === "reb")?.rows;
      assert.deepEqual(points?.map((row) => [row.playerId, row.value, row.games]), [
        ["qualified", 2, 2],
      ]);
      assert.deepEqual(rebounds?.map((row) => [row.playerId, row.value, row.games]), [
        ["qualified", 1, 2],
      ]);

      const terms = await repositories.getTerms();
      const seasonLine = await repositories.getPlayerSeasonLine("qualified", "season", terms);
      assert.equal(seasonLine.gamesPlayed, 2);

      const roster = await repositories.getTeamRoster("team", "season");
      assert.equal(roster.find((player) => player.playerId === "qualified")?.games, 2);
      assert.equal(roster.find((player) => player.playerId === "dnp")?.games, 0);
    } finally {
      if (closeRepository) await closeRepository();
      if (disposableConfirmed) {
        await admin.unsafe("DROP SCHEMA public CASCADE; CREATE SCHEMA public");
      }
      await admin.end();
      delete process.env.LEADER_MIN_GAMES;
    }
  },
);
