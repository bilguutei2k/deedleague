// Deed League Index — canonical schema (Drizzle owns all DDL/migrations).
// Written after the Step 1 source-shape probe; see docs/step1-source-shape-probe.md.
//
// Keying: all canonical PKs are the source's stable UUIDs (text). Never name-keyed.
// Stat grain is per-(entity, term, period) COUNTS of atomic events. period_id is a raw
// nullable bucket key (no periods dimension table); the null bucket is a real
// "unknown-period" bucket and uniqueness uses NULLS NOT DISTINCT.

import { sql } from "drizzle-orm";
import {
  pgTable,
  text,
  integer,
  boolean,
  date,
  timestamp,
  jsonb,
  uuid,
  uniqueIndex,
  unique,
  index,
  numeric,
  primaryKey,
} from "drizzle-orm/pg-core";

// ---------------------------------------------------------------------------
// Provenance
// ---------------------------------------------------------------------------

// Append-only provenance. One row per raw fetch. load_status flips to 'loaded'
// only after the per-game load transaction commits.
export const sourceRecords = pgTable("source_records", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  sourceName: text("source_name").notNull().default("msports"),
  sourceUrl: text("source_url").notNull(),
  operationName: text("operation_name"),
  variables: jsonb("variables"),
  fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
  rawSnapshotPath: text("raw_snapshot_path"),
  parserVersion: text("parser_version"),
  entityType: text("entity_type"), // 'game' in v1
  entityId: text("entity_id"),
  // pending | loaded | unchanged | partial | failed
  loadStatus: text("load_status").notNull().default("pending"),
});

// One row per ingestion run.
export const scrapeRuns = pgTable("scrape_runs", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  mode: text("mode").notNull(), // backfill | incremental | full_resync
  gamesChecked: integer("games_checked").notNull().default(0),
  gamesChanged: integer("games_changed").notNull().default(0),
  status: text("status").notNull().default("running"), // running | ok | partial | failed
  notes: text("notes"),
});

// ---------------------------------------------------------------------------
// Dimensions
// ---------------------------------------------------------------------------

// seasons.id = the season tournament ("competition") UUID.
export const seasons = pgTable("seasons", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  startDate: date("start_date"),
  endDate: date("end_date"),
  parentLeagueId: text("parent_league_id"), // lineage: parent league tournament
});

// Only men's (ЭРЭГТЭЙ) divisions are ingested in v1; women's deliberately excluded.
export const divisions = pgTable("divisions", {
  id: text("id").primaryKey(),
  seasonId: text("season_id")
    .notNull()
    .references(() => seasons.id),
  name: text("name").notNull(),
});

export const teams = pgTable("teams", {
  id: text("id").primaryKey(),
  name: text("name").notNull(), // stored as-returned (Cyrillic or Latin)
  logo: text("logo"),
});

// Display/cross-season drift only — never used as a key.
export const teamAliases = pgTable(
  "team_aliases",
  {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    alias: text("alias").notNull(),
    source: text("source"),
  },
  (t) => [uniqueIndex("team_aliases_team_alias_uq").on(t.teamId, t.alias)],
);

// NOTE: source field `name` holds the family name, `surname` the given name
// (inverted vs Western order). Stored as-returned; no jersey number here.
export const players = pgTable("players", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  surname: text("surname"),
  image: text("image"),
});

// stat_terms = the term dictionary. §6 conflict-check keys on
// (unique_name, formula, registrable) for a given id across seasons.
export const statTerms = pgTable("stat_terms", {
  id: text("id").primaryKey(),
  uniqueName: text("unique_name"), // schema-nullable; UUID is the real key
  shortName: text("short_name").notNull(),
  name: text("name"),
  formula: text("formula"), // null for atomic terms
  registrable: boolean("registrable"), // nullable Boolean (three-valued in source)
  termType: text("term_type"),
  orderIndex: integer("order_index"),
  showOnUser: boolean("show_on_user"),
  isDefault: boolean("is_default"),
});

// ---------------------------------------------------------------------------
// Games + facts
// ---------------------------------------------------------------------------

export const games = pgTable(
  "games",
  {
    id: text("id").primaryKey(),
    seasonId: text("season_id")
      .notNull()
      .references(() => seasons.id),
    divisionId: text("division_id")
      .notNull()
      .references(() => divisions.id),
    date: timestamp("date", { withTimezone: true }).notNull(),
    location: text("location"),
    isEnded: boolean("is_ended").notNull(),
    // Hash over the full normalized persisted payload (excl. fetch ts & currentTime).
    contentHash: text("content_hash"),
    lastFetchedAt: timestamp("last_fetched_at", { withTimezone: true }),
    lastChangedAt: timestamp("last_changed_at", { withTimezone: true }),
    sourceRecordId: uuid("source_record_id").references(() => sourceRecords.id),
  },
  (t) => [
    index("games_season_idx").on(t.seasonId),
    index("games_division_date_idx").on(t.divisionId, t.date),
  ],
);

// Persists the scores-parse: per-team competitor_order + final points + winner.
// Home/away NOT asserted. Standings (W/L, PF/PA) and the PTS cross-check read this.
export const gameCompetitors = pgTable(
  "game_competitors",
  {
    gameId: text("game_id")
      .notNull()
      .references(() => games.id),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    competitorOrder: integer("competitor_order").notNull(), // 0/1, source order
    points: integer("points"), // null when source score value is empty/unplayed
    isWinner: boolean("is_winner"),
  },
  (t) => [
    primaryKey({ columns: [t.gameId, t.teamId] }),
    uniqueIndex("game_competitors_order_uq").on(t.gameId, t.competitorOrder),
  ],
);

// One row per membership in the game (incl. zero-stat players). Jersey number here.
export const gameRosters = pgTable(
  "game_rosters",
  {
    gameId: text("game_id")
      .notNull()
      .references(() => games.id),
    playerId: text("player_id")
      .notNull()
      .references(() => players.id),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    number: integer("number"), // nullable jersey, per-game/team
  },
  (t) => [primaryKey({ columns: [t.gameId, t.playerId, t.teamId] })],
);

// Aggregated COUNTS of atomic player events. Derived terms are NOT stored here
// (computed at read/aggregate time). period_id nullable = unknown-period bucket.
export const gamePlayerStats = pgTable(
  "game_player_stats",
  {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    gameId: text("game_id")
      .notNull()
      .references(() => games.id),
    playerId: text("player_id")
      .notNull()
      .references(() => players.id),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    termId: text("term_id")
      .notNull()
      .references(() => statTerms.id),
    periodId: text("period_id"), // nullable bucket key; no periods table
    value: integer("value").notNull(), // count of events
    sourceRecordId: uuid("source_record_id").references(() => sourceRecords.id),
  },
  (t) => [
    unique("game_player_stats_uq")
      .on(t.gameId, t.playerId, t.teamId, t.termId, t.periodId)
      .nullsNotDistinct(),
    index("game_player_stats_player_idx").on(t.playerId),
    index("game_player_stats_game_idx").on(t.gameId),
  ],
);

// Team-level atomic events (athleteId-null). Empty in v1 data; built defensively.
export const gameTeamStats = pgTable(
  "game_team_stats",
  {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    gameId: text("game_id")
      .notNull()
      .references(() => games.id),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    termId: text("term_id")
      .notNull()
      .references(() => statTerms.id),
    periodId: text("period_id"),
    value: integer("value").notNull(),
    sourceRecordId: uuid("source_record_id").references(() => sourceRecords.id),
  },
  (t) => [
    unique("game_team_stats_uq")
      .on(t.gameId, t.teamId, t.termId, t.periodId)
      .nullsNotDistinct(),
    index("game_team_stats_game_idx").on(t.gameId),
  ],
);

// Physical, COMPUTED (not scraped) — recomputed by upsert per season.
export const standings = pgTable(
  "standings",
  {
    seasonId: text("season_id")
      .notNull()
      .references(() => seasons.id),
    teamId: text("team_id")
      .notNull()
      .references(() => teams.id),
    wins: integer("wins").notNull().default(0),
    losses: integer("losses").notNull().default(0),
    pct: numeric("pct"), // null when no decided games
    pf: integer("pf").notNull().default(0),
    pa: integer("pa").notNull().default(0),
    diff: integer("diff").notNull().default(0),
  },
  (t) => [primaryKey({ columns: [t.seasonId, t.teamId] })],
);
