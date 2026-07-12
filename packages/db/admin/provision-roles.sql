\set ON_ERROR_STOP on

BEGIN;

DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'deedleague_web') THEN
    CREATE ROLE deedleague_web NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'deedleague_pipeline') THEN
    CREATE ROLE deedleague_pipeline NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'deedleague_migrator') THEN
    CREATE ROLE deedleague_migrator NOLOGIN;
  END IF;
END
$roles$;

ALTER ROLE deedleague_web NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE deedleague_pipeline NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE deedleague_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

SELECT format(
  'GRANT CONNECT ON DATABASE %I TO deedleague_web, deedleague_pipeline, deedleague_migrator',
  current_database()
) \gexec
SELECT format('GRANT CREATE ON DATABASE %I TO deedleague_migrator', current_database()) \gexec

GRANT USAGE ON SCHEMA public TO deedleague_web, deedleague_pipeline;
GRANT USAGE, CREATE ON SCHEMA public TO deedleague_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

REVOKE ALL PRIVILEGES ON TABLE
  public.divisions,
  public.game_competitors,
  public.game_player_stats,
  public.game_rosters,
  public.game_team_stats,
  public.games,
  public.players,
  public.scrape_runs,
  public.seasons,
  public.source_records,
  public.standings,
  public.stat_terms,
  public.team_aliases,
  public.teams
FROM PUBLIC, deedleague_web, deedleague_pipeline;

ALTER TABLE public.divisions OWNER TO deedleague_migrator;
ALTER TABLE public.game_competitors OWNER TO deedleague_migrator;
ALTER TABLE public.game_player_stats OWNER TO deedleague_migrator;
ALTER TABLE public.game_rosters OWNER TO deedleague_migrator;
ALTER TABLE public.game_team_stats OWNER TO deedleague_migrator;
ALTER TABLE public.games OWNER TO deedleague_migrator;
ALTER TABLE public.players OWNER TO deedleague_migrator;
ALTER TABLE public.scrape_runs OWNER TO deedleague_migrator;
ALTER TABLE public.seasons OWNER TO deedleague_migrator;
ALTER TABLE public.source_records OWNER TO deedleague_migrator;
ALTER TABLE public.standings OWNER TO deedleague_migrator;
ALTER TABLE public.stat_terms OWNER TO deedleague_migrator;
ALTER TABLE public.team_aliases OWNER TO deedleague_migrator;
ALTER TABLE public.teams OWNER TO deedleague_migrator;

GRANT SELECT ON TABLE
  public.divisions,
  public.game_competitors,
  public.game_player_stats,
  public.game_rosters,
  public.game_team_stats,
  public.games,
  public.players,
  public.scrape_runs,
  public.seasons,
  public.source_records,
  public.standings,
  public.stat_terms,
  public.team_aliases,
  public.teams
TO deedleague_web;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.divisions,
  public.game_competitors,
  public.game_player_stats,
  public.game_rosters,
  public.game_team_stats,
  public.games,
  public.players,
  public.scrape_runs,
  public.seasons,
  public.source_records,
  public.standings,
  public.stat_terms,
  public.team_aliases,
  public.teams
TO deedleague_pipeline;

ALTER DEFAULT PRIVILEGES FOR ROLE deedleague_migrator IN SCHEMA public
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE deedleague_migrator IN SCHEMA public
  GRANT SELECT ON TABLES TO deedleague_web;
ALTER DEFAULT PRIVILEGES FOR ROLE deedleague_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO deedleague_pipeline;
ALTER DEFAULT PRIVILEGES FOR ROLE deedleague_migrator IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO deedleague_pipeline;

\if :{?web_login}
SELECT format('GRANT deedleague_web TO %I', :'web_login') \gexec
\endif
\if :{?pipeline_login}
SELECT format('GRANT deedleague_pipeline TO %I', :'pipeline_login') \gexec
\endif
\if :{?migrator_login}
SELECT format('GRANT deedleague_migrator TO %I', :'migrator_login') \gexec
\endif

COMMIT;
