# Deed League Index

Deed League Index is a read-only analytics site for Mongolia's Undesnii Deed League.
The Python pipeline is the authoritative writer, PostgreSQL is the canonical store,
`packages/db` owns schema and reads, and the Next.js application is presentation-only.

## Prerequisites

- Node.js 22 or newer
- pnpm 11.5.2 through Corepack
- Python 3.12
- PostgreSQL 15 or newer (the schema uses `NULLS NOT DISTINCT`)

## Install

```sh
corepack enable
pnpm install --frozen-lockfile

python3.12 -m venv pipeline/.venv
pipeline/.venv/bin/python -m pip install --requirement pipeline/requirements.lock
pipeline/.venv/bin/python -m pip install --no-deps --editable pipeline
```

The JavaScript lockfile and `pipeline/requirements.lock` are committed. Regenerate and
review either lock deliberately when changing dependencies.

## Environment

Copy variable names from `.env.example` into ignored local environment files or the
deployment secret store. Never commit values.

| Variable | Consumer | Intended privilege |
|---|---|---|
| `DATABASE_URL` | Next.js | Read-only access to application tables |
| `PIPELINE_DATABASE_URL` | Python pipeline | Select/insert/update/delete for ingestion tables |
| `MIGRATION_DATABASE_URL` | Drizzle Kit | Schema owner or migration administrator |
| `CURRENT_SEASON_ID` | Next.js | Optional configured current season; invalid IDs fall back to latest |
| `LEADER_MIN_GAMES` | Next.js | Positive integer; defaults to `3` recorded appearances |
| `MSPORTS_GRAPHQL_URL` | Pipeline | Optional source endpoint override |
| `SNAPSHOT_DIR` | Pipeline | Durable raw-snapshot destination; local path by default |
| `SNAPSHOT_URI_PREFIX` | Pipeline | Optional durable prefix stored instead of the runner-local path |

`SUPABASE_DB_URL` remains a deprecated pipeline fallback for existing local setups. New
environments should use `PIPELINE_DATABASE_URL`. The Supabase service-role API key is not
used and must not be provisioned for this repository.

Production uses three non-login capability roles. Create separate provider-managed login
identities, then provision membership and object ownership with an administrator URL:

```sh
psql "$ADMIN_DATABASE_URL" \
  -v web_login=deedleague_web_login \
  -v pipeline_login=deedleague_pipeline_login \
  -v migrator_login=deedleague_migrator_login \
  -f packages/db/admin/provision-roles.sql
```

The script transfers only Deed League tables to `deedleague_migrator`, revokes public
schema creation, and grants the web and pipeline roles only their required privileges.
It does not create login roles or passwords. After rotating the three URLs, prove the
effective permissions using the actual credentials:

```sh
DATABASE_URL='postgresql://web-login:...' \
PIPELINE_DATABASE_URL='postgresql://pipeline-login:...' \
MIGRATION_DATABASE_URL='postgresql://migrator-login:...' \
  packages/db/admin/verify-roles.sh
```

Rollback requires the original owner role and intentionally does not restore unsafe
`PUBLIC` schema creation:

```sh
psql "$ADMIN_DATABASE_URL" -v owner_role=postgres \
  -v web_login=deedleague_web_login \
  -v pipeline_login=deedleague_pipeline_login \
  -v migrator_login=deedleague_migrator_login \
  -f packages/db/admin/rollback-roles.sql
```

Preview deployments must never receive production database credentials.

## Database

Run migrations from the database package with an administrator URL:

```sh
MIGRATION_DATABASE_URL='postgresql://...' \
  pnpm --filter @deedleague/db exec drizzle-kit migrate
```

Drizzle configuration fails immediately when neither `MIGRATION_DATABASE_URL` nor
`DATABASE_URL` is present.

## Pipeline

```sh
pipeline/.venv/bin/deedleague-pipeline --backfill
pipeline/.venv/bin/deedleague-pipeline --incremental
pipeline/.venv/bin/deedleague-pipeline --full-resync
pipeline/.venv/bin/deedleague-pipeline --game GAME_ID
```

Invalid invocation exits `2`. A partial run or failed golden validation exits `1`.
Successful execution exits `0`. Run states are:

- `ok`: run completed with no failed games or recorded quality issue.
- `partial`: run completed with a failed game or recoverable quality issue.
- `failed`: discovery, setup, standings, finalization, or another run-level step failed.

Every terminal run attempts to set `finished_at`. Concise structured failure and quality
details are stored in `scrape_runs.notes`. Source records can be `pending`, `loaded`,
`unchanged`, `partial`, or `failed`.

Raw GraphQL payloads are written under `SNAPSHOT_DIR`. When `SNAPSHOT_URI_PREFIX` is set,
that durable prefix plus the unique filename is stored in `source_records` instead of the
runner-local path. GitHub Actions uses this to address the retained artifact by repository,
run, attempt, artifact, and filename.

## Statistics

- Atomic source events are counted once and derived terms are evaluated from source formulas.
- `BKST_FGA` is the source's observed derived FGA identifier, not a local typo.
- A recorded appearance is a player/game with any player-stat event. This excludes
  roster-only records because the source does not reliably distinguish DNP from membership.
- Category values are zero-filled over recorded appearances, so a zero-rebound or
  zero-point appearance remains in the per-game denominator.
- Leader eligibility is centralized through `LEADER_MIN_GAMES`; the active rule is shown
  on the leaders page. The production default is three recorded appearances and remains
  configurable for future policy changes.

## Development and Validation

```sh
pnpm test:ts
pnpm typecheck
pnpm --filter web build
pnpm test:python
```

An isolated PostgreSQL repository test is available:

```sh
TEST_DATABASE_URL='postgresql://.../empty_disposable_database' pnpm test:db
```

The test refuses a database containing public tables. After confirming an empty test
database, it creates the schema and drops/recreates `public` during cleanup. Never point it
at a shared or production database.

Run locally with:

```sh
DATABASE_URL='postgresql://read-only...' pnpm dev
```

## Automation

`.github/workflows/ci.yml` runs locked Python tests, TypeScript tests, workspace
typechecking, and the production web build.

Incremental ingestion runs every four hours at minute 17. Full resync runs Sundays at
02:00 UTC. Both workflows can also be dispatched manually and share a non-cancelling
concurrency group, so two writers never overlap.

Repository configuration requires the least-privilege `PIPELINE_DATABASE_URL` Actions
secret. `MSPORTS_GRAPHQL_URL` is an optional Actions variable. Incremental snapshots and
logs are retained for 30 days; full-resync artifacts are retained for 90 days. The database
reference uses the `github-actions://` scheme and remains resolvable for that retention
window. Recovery after expiry is a full resync.

An incremental failure opens a GitHub issue after two consecutive failed workflow runs.
A full-resync failure opens an issue immediately. The next successful run comments on and
closes the corresponding alert. Pipeline partial states already exit nonzero and therefore
use the same alert path.

Deployment remains intentionally inactive. Activate it only after linking the intended
Vercel project and configuring scoped credentials or Vercel Git integration.

## Known Limitations

- Coverage reports full/partial status for ingested games only. Missing scheduled games
  cannot be computed until schedule identities are persisted independently.
- Roster membership does not prove participation; any-stat presence is the current explicit
  appearance proxy.
- Approved league and season IDs are a deliberate ingestion safety gate and require review
  at season rollover.
- No isolated PostgreSQL test database is provisioned by the repository itself.
