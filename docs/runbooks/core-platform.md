# Core platform developer runbook

## Docker path

```bash
docker compose up -d postgres redis minio
docker compose run --rm migrate
docker compose --profile simulation run --rm seed-platform-demos
docker compose up -d api worker beat web
```

If Docker cannot resolve `registry-1.docker.io`, the failure occurs before any
GenuineGigs code runs. Restore Docker Desktop DNS/proxy access or use the host
Python path below; repeatedly rebuilding cannot fix an unavailable registry.

## Host fallback (no Docker image pull)

With PostgreSQL already reachable through `DATABASE_URL`:

```bash
cd apps/api
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.platform.seed_cli
.venv/bin/python -m app.platform.backfill_cli
.venv/bin/uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
npm run dev:web
```

Open `http://localhost:3000/login`, sign in as
`demo.admin@genuinegigs.local` / `Password@123`, choose the relevant isolated
workspace, then use `/platform`, `/control-centre`, `/v2/home`, or `/scm`.

## Workspace behavior

- Procurement Demo isolates procurement fixtures.
- Operations Demo isolates plant-execution fixtures.
- SCM Demo isolates deterministic planning fixtures.
- Core Integration Demo is the cross-module event/action scenario.

Selecting a Procurement-only workspace and opening `/scm` will correctly show
that SCM is unavailable. Choose SCM Demo or Core Integration Demo from login.
