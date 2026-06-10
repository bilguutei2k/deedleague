CREATE TABLE "divisions" (
	"id" text PRIMARY KEY NOT NULL,
	"season_id" text NOT NULL,
	"name" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "game_competitors" (
	"game_id" text NOT NULL,
	"team_id" text NOT NULL,
	"competitor_order" integer NOT NULL,
	"points" integer,
	"is_winner" boolean,
	CONSTRAINT "game_competitors_game_id_team_id_pk" PRIMARY KEY("game_id","team_id")
);
--> statement-breakpoint
CREATE TABLE "game_player_stats" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"game_id" text NOT NULL,
	"player_id" text NOT NULL,
	"team_id" text NOT NULL,
	"term_id" text NOT NULL,
	"period_id" text,
	"value" integer NOT NULL,
	"source_record_id" uuid,
	CONSTRAINT "game_player_stats_uq" UNIQUE NULLS NOT DISTINCT("game_id","player_id","team_id","term_id","period_id")
);
--> statement-breakpoint
CREATE TABLE "game_rosters" (
	"game_id" text NOT NULL,
	"player_id" text NOT NULL,
	"team_id" text NOT NULL,
	"number" integer,
	CONSTRAINT "game_rosters_game_id_player_id_team_id_pk" PRIMARY KEY("game_id","player_id","team_id")
);
--> statement-breakpoint
CREATE TABLE "game_team_stats" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"game_id" text NOT NULL,
	"team_id" text NOT NULL,
	"term_id" text NOT NULL,
	"period_id" text,
	"value" integer NOT NULL,
	"source_record_id" uuid,
	CONSTRAINT "game_team_stats_uq" UNIQUE NULLS NOT DISTINCT("game_id","team_id","term_id","period_id")
);
--> statement-breakpoint
CREATE TABLE "games" (
	"id" text PRIMARY KEY NOT NULL,
	"season_id" text NOT NULL,
	"division_id" text NOT NULL,
	"date" timestamp with time zone NOT NULL,
	"location" text,
	"is_ended" boolean NOT NULL,
	"content_hash" text,
	"last_fetched_at" timestamp with time zone,
	"last_changed_at" timestamp with time zone,
	"source_record_id" uuid
);
--> statement-breakpoint
CREATE TABLE "players" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"surname" text,
	"image" text
);
--> statement-breakpoint
CREATE TABLE "scrape_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"mode" text NOT NULL,
	"games_checked" integer DEFAULT 0 NOT NULL,
	"games_changed" integer DEFAULT 0 NOT NULL,
	"status" text DEFAULT 'running' NOT NULL,
	"notes" text
);
--> statement-breakpoint
CREATE TABLE "seasons" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"start_date" date,
	"end_date" date,
	"parent_league_id" text
);
--> statement-breakpoint
CREATE TABLE "source_records" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_name" text DEFAULT 'msports' NOT NULL,
	"source_url" text NOT NULL,
	"operation_name" text,
	"variables" jsonb,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL,
	"raw_snapshot_path" text,
	"parser_version" text,
	"entity_type" text,
	"entity_id" text,
	"load_status" text DEFAULT 'pending' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "standings" (
	"season_id" text NOT NULL,
	"team_id" text NOT NULL,
	"wins" integer DEFAULT 0 NOT NULL,
	"losses" integer DEFAULT 0 NOT NULL,
	"pct" numeric,
	"pf" integer DEFAULT 0 NOT NULL,
	"pa" integer DEFAULT 0 NOT NULL,
	"diff" integer DEFAULT 0 NOT NULL,
	CONSTRAINT "standings_season_id_team_id_pk" PRIMARY KEY("season_id","team_id")
);
--> statement-breakpoint
CREATE TABLE "stat_terms" (
	"id" text PRIMARY KEY NOT NULL,
	"unique_name" text,
	"short_name" text NOT NULL,
	"name" text,
	"formula" text,
	"registrable" boolean,
	"term_type" text,
	"order_index" integer,
	"show_on_user" boolean,
	"is_default" boolean
);
--> statement-breakpoint
CREATE TABLE "team_aliases" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"team_id" text NOT NULL,
	"alias" text NOT NULL,
	"source" text
);
--> statement-breakpoint
CREATE TABLE "teams" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"logo" text
);
--> statement-breakpoint
ALTER TABLE "divisions" ADD CONSTRAINT "divisions_season_id_seasons_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."seasons"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_competitors" ADD CONSTRAINT "game_competitors_game_id_games_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."games"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_competitors" ADD CONSTRAINT "game_competitors_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_player_stats" ADD CONSTRAINT "game_player_stats_game_id_games_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."games"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_player_stats" ADD CONSTRAINT "game_player_stats_player_id_players_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_player_stats" ADD CONSTRAINT "game_player_stats_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_player_stats" ADD CONSTRAINT "game_player_stats_term_id_stat_terms_id_fk" FOREIGN KEY ("term_id") REFERENCES "public"."stat_terms"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_player_stats" ADD CONSTRAINT "game_player_stats_source_record_id_source_records_id_fk" FOREIGN KEY ("source_record_id") REFERENCES "public"."source_records"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_rosters" ADD CONSTRAINT "game_rosters_game_id_games_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."games"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_rosters" ADD CONSTRAINT "game_rosters_player_id_players_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."players"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_rosters" ADD CONSTRAINT "game_rosters_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_team_stats" ADD CONSTRAINT "game_team_stats_game_id_games_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."games"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_team_stats" ADD CONSTRAINT "game_team_stats_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_team_stats" ADD CONSTRAINT "game_team_stats_term_id_stat_terms_id_fk" FOREIGN KEY ("term_id") REFERENCES "public"."stat_terms"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game_team_stats" ADD CONSTRAINT "game_team_stats_source_record_id_source_records_id_fk" FOREIGN KEY ("source_record_id") REFERENCES "public"."source_records"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "games" ADD CONSTRAINT "games_season_id_seasons_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."seasons"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "games" ADD CONSTRAINT "games_division_id_divisions_id_fk" FOREIGN KEY ("division_id") REFERENCES "public"."divisions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "games" ADD CONSTRAINT "games_source_record_id_source_records_id_fk" FOREIGN KEY ("source_record_id") REFERENCES "public"."source_records"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "standings" ADD CONSTRAINT "standings_season_id_seasons_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."seasons"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "standings" ADD CONSTRAINT "standings_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_aliases" ADD CONSTRAINT "team_aliases_team_id_teams_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "game_competitors_order_uq" ON "game_competitors" USING btree ("game_id","competitor_order");--> statement-breakpoint
CREATE INDEX "game_player_stats_player_idx" ON "game_player_stats" USING btree ("player_id");--> statement-breakpoint
CREATE INDEX "game_player_stats_game_idx" ON "game_player_stats" USING btree ("game_id");--> statement-breakpoint
CREATE INDEX "game_team_stats_game_idx" ON "game_team_stats" USING btree ("game_id");--> statement-breakpoint
CREATE INDEX "games_season_idx" ON "games" USING btree ("season_id");--> statement-breakpoint
CREATE INDEX "games_division_date_idx" ON "games" USING btree ("division_id","date");--> statement-breakpoint
CREATE UNIQUE INDEX "team_aliases_team_alias_uq" ON "team_aliases" USING btree ("team_id","alias");