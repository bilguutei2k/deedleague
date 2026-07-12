#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must contain the web login URL}"
: "${PIPELINE_DATABASE_URL:?PIPELINE_DATABASE_URL must contain the pipeline login URL}"
: "${MIGRATION_DATABASE_URL:?MIGRATION_DATABASE_URL must contain the migrator login URL}"

psql_base=(psql -X --no-psqlrc --set ON_ERROR_STOP=1 --quiet)

expect_allowed() {
  local label=$1
  local url=$2
  local sql=$3
  "${psql_base[@]}" "$url" --command "$sql" >/dev/null
  printf 'PASS allowed: %s\n' "$label"
}

expect_denied() {
  local label=$1
  local url=$2
  local sql=$3
  if "${psql_base[@]}" "$url" --command "$sql" >/dev/null 2>&1; then
    printf 'FAIL unexpectedly allowed: %s\n' "$label" >&2
    return 1
  fi
  printf 'PASS denied: %s\n' "$label"
}

expect_membership() {
  local label=$1
  local url=$2
  local role=$3
  local result
  result=$("${psql_base[@]}" "$url" --tuples-only --no-align \
    --command "SELECT pg_has_role(current_user, '$role', 'member')")
  if [[ $result != "t" ]]; then
    printf 'FAIL missing membership: %s\n' "$label" >&2
    return 1
  fi
  printf 'PASS membership: %s\n' "$label"
}

expect_membership "web -> deedleague_web" "$DATABASE_URL" deedleague_web
expect_allowed "web SELECT" "$DATABASE_URL" "SELECT count(*) FROM public.seasons"
expect_denied "web INSERT" "$DATABASE_URL" \
  "BEGIN; INSERT INTO public.scrape_runs (mode) VALUES ('role-probe'); ROLLBACK"
expect_denied "web DDL" "$DATABASE_URL" \
  "BEGIN; CREATE TABLE public.deedleague_web_role_probe (id integer); ROLLBACK"

expect_membership "pipeline -> deedleague_pipeline" "$PIPELINE_DATABASE_URL" deedleague_pipeline
expect_allowed "pipeline DML" "$PIPELINE_DATABASE_URL" \
  "BEGIN; INSERT INTO public.scrape_runs (mode) VALUES ('role-probe'); ROLLBACK"
expect_denied "pipeline DDL" "$PIPELINE_DATABASE_URL" \
  "BEGIN; CREATE TABLE public.deedleague_pipeline_role_probe (id integer); ROLLBACK"

expect_membership "migrator -> deedleague_migrator" "$MIGRATION_DATABASE_URL" deedleague_migrator
expect_allowed "migrator DDL" "$MIGRATION_DATABASE_URL" \
  "BEGIN; CREATE TABLE public.deedleague_migrator_role_probe (id integer); ROLLBACK"

printf 'All database role checks passed.\n'
