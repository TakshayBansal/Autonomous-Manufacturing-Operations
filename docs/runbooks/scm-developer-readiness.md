# SCM developer-readiness runbook

## Local start

Run `docker compose up --build`. The migration job upgrades through
`0057_scm_control_tower_scaffold`; the worker consumes the dedicated `scm`
queue. Sign in as a workspace administrator and open `/scm`.

For a deterministic demonstration, select **Load mock ERP**, then **Run
planning**. The expected fixture includes a connector-housing shortage, a late
PO schedule, finished-good/OEM lineage, and a pull-in recommendation.

## File exchange

Use `/scm/imports` for XLSX, CSV, or ZIP-of-CSV preview. XLSX sheet names and
required columns are returned by `GET /scm/schema`. A CSV represents one entity
and requires its canonical entity selection. Preview never changes canonical
records; commit applies valid rows and retains rejected rows, file hash, source
cells, mapping version, and canonical IDs.

## Verification

```bash
cd apps/api
.venv/bin/pytest -q tests/test_scm_engine.py tests/test_scm_imports.py tests/test_scm_api.py
.venv/bin/alembic heads
.venv/bin/python scripts/check_openapi_contract.py
cd ../web
npm run lint
npm run build
```

## Staging path

Use the existing API, web, migration, worker, Redis, PostgreSQL, and object
storage topology. Promote one immutable image version to staging, run the
migration job before API/worker rollout, load only synthetic or sanitized SCM
data, run a planning fixture, verify `/health/ready`, `/metrics`, import
lineage, data freshness, and a recommendation acknowledgement, then promote the
same image digest manually. ERP writes remain disabled.

## Operational boundaries

- Completed planning runs and imported facts are immutable.
- Accepted recommendations are acknowledgements, not ERP writes.
- Stale or missing explicit available inventory produces `UNKNOWN` and no
  action candidate.
- SAP, REST, OData, and SFTP entries are unverified adapter contracts.
- Customer-specific availability, forecast-consumption, thresholds, and
  action constraints require discovery and new policy versions.
