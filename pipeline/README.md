# Deed League Pipeline

The pipeline discovers the approved men's seasons, snapshots msports GraphQL responses,
normalizes event counts and as-of-date rosters, transactionally replaces changed game
facts, and recomputes standings.

From the repository root:

```sh
python3.12 -m venv pipeline/.venv
pipeline/.venv/bin/python -m pip install --requirement pipeline/requirements.lock
pipeline/.venv/bin/python -m pip install --no-deps --editable pipeline

PIPELINE_DATABASE_URL='postgresql://...' \
  pipeline/.venv/bin/deedleague-pipeline --incremental
```

Set `SNAPSHOT_URI_PREFIX` when an external process will publish `SNAPSHOT_DIR`. The pipeline
then stores a durable reference while retaining the local file for that publisher. GitHub
Actions uses run-addressable artifacts with 30-day incremental and 90-day full-resync
retention.

See the root README for modes, exit codes, run states, role provisioning and verification,
automation recovery, tests, and production credential scopes.
