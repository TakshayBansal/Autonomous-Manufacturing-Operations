# GenuineGigs Manufacturing Agent OS

GenuineGigs is a full-stack manufacturing operations platform built as a portfolio project. It brings procurement, shop-floor operations, recovery, quality, and supply-chain planning into one role-aware workspace, with governed AI assistance and simulated enterprise integrations.

The project is designed around a practical premise: the ERP remains the system of record; GenuineGigs is the execution, evidence, exception, and agent layer that helps teams act on operational change.

![GenuineGigs product interface](assets/full.png)

## What it demonstrates

- **End-to-end procurement:** material needs, RFQs, quotation comparison, negotiation, PO drafts, receipts, inspection, invoice matching, and exception closure.
- **Factory operations and recovery:** production visibility, deviations, quality, maintenance, dependencies, recovery plans, and role-owned work.
- **Supply-chain control tower:** material projections, shortages, pegging, scenarios, imports, and recommended actions.
- **AI with operational guardrails:** role-scoped agents, proposals and approvals, auditable actions, deterministic local fallback, and an emergency stop.
- **Production-minded platform work:** FastAPI, Next.js, PostgreSQL/pgvector, Redis/Celery, MinIO, Open Policy Agent, Alembic migrations, OpenAPI contracts, Docker Compose, Playwright, and Helm.

## Architecture at a glance

```text
Next.js web app ─────┐
                    ├── FastAPI API ── PostgreSQL / pgvector
Role-aware agents ──┤       │
                    │       ├── Redis + Celery workers
                    │       ├── MinIO evidence storage
                    │       └── OPA policy checks
                    │
Factory / ERP simulators ── connector and event workflows
```

| Area | Location |
| --- | --- |
| Next.js frontend | `apps/web` |
| FastAPI API, migrations, and tests | `apps/api` |
| Shared TypeScript contracts | `packages/shared` |
| Factory, OT, edge, and developer-lab services | `services` |
| Docker, OPA, and deployment infrastructure | `docker-compose.yml`, `infra`, `deploy/helm` |
| Product, architecture, and operating documentation | `docs` |

## Quick start

### Prerequisites

- Docker Compose v2 for the complete local stack
- Node.js 22+ and npm 10+ for frontend checks and browser tests
- Python 3.12+ when running the API or its tests outside Docker

Start the default local environment:

```bash
docker compose up --build
```

Then open:

| Service | URL |
| --- | --- |
| Product UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Mailpit inbox | http://localhost:8025 |
| MinIO console | http://localhost:9001 |
| OPA | http://localhost:8181 |

The default stack runs PostgreSQL, Redis, MinIO, Mailpit, OPA, migrations and seed jobs, the API, Celery worker/beat, and the production Next.js application. It uses safe local defaults: ERP and SMTP writes are simulated and AI workflows fall back deterministically when no provider key is configured.

Stop the environment with `docker compose down`. This preserves local volumes; use `docker compose down -v` only when you intentionally want to remove local database, cache, and object-store data.

## Simulation and developer lab

The optional profiles expose the project’s factory-integration and recovery workflows.

```bash
# Closed-loop Northstar factory simulation
docker compose --profile simulation up --build

# Simulation plus MQTT, OT simulator, edge bridge, Jaeger, and developer lab
docker compose --profile developer-lab up --build
```

The developer lab is available at http://localhost:3100 and Jaeger at http://localhost:16686. See the [Northstar simulation runbook](docs/runbooks/northstar-live-simulation.md) and [developer-lab guide](docs/runbooks/developer-lab-v2.md) for scenarios, accounts, and reset procedures.

## Development commands

Install JavaScript dependencies once before using the npm-based checks:

```bash
npm ci
```

| Command | Purpose |
| --- | --- |
| `npm run dev:web` | Start the Next.js development server. |
| `npm run dev:api` | Start FastAPI on port 8000 using `apps/api/.venv`. |
| `npm run typecheck` | Type-check the web application. |
| `npm run build:web` | Create a production web build. |
| `npm run check:v2-performance` | Check V2 client JavaScript and CSS budgets. |
| `npm run test:api` | Run the API test suite using `apps/api/.venv`. |
| `npm run test:e2e` | Run the Playwright and accessibility suite. |
| `npm run test:v2-simulation` | Run the Northstar simulation acceptance checks. |
| `npm run generate:api` | Generate TypeScript API types from a running API, then stamp the contract. |
| `npm run check:api-contract` | Verify the checked-in OpenAPI contract. |
| `npm run seed:platform-demos` | Seed platform demonstration data. |
| `npm run backfill:platform` | Run the platform data backfill utility. |

For local Python development, create the repository-expected virtual environment:

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cd ../..
```

`npm run test:e2e` starts the API, web app, and factory simulator when they are not already running. Install the Playwright browser dependencies if your machine has not run the suite before.

## Verification sequence

Run the checks most relevant to a change before sharing it:

```bash
npm run typecheck
npm run build:web
npm run check:api-contract
npm run test:api
npm run test:e2e
```

For the complete factory acceptance path:

```bash
npm run test:v2-simulation
# optionally include its desktop browser scenario
RUN_BROWSER_E2E=1 npm run test:v2-simulation
```

## Documentation

Start with the [documentation map](docs/README.md). The most useful entry points are:

- [Complete product and implementation handoff](docs/GENUINEGIGS_PLATFORM_AND_SCM_IMPLEMENTATION_HANDOFF.md)
- [Current runtime architecture](docs/architecture/current-runtime-truth.md)
- [Procurement product documentation](docs/products/procurement/README.md)
- [Operations product documentation](docs/products/operations/README.md)
- [Supply-chain product documentation](docs/products/supply-chain/README.md)
- [Deployment and local infrastructure notes](infra/README.md)

## Safety notes

This is a demonstration environment. Its default Compose configuration keeps `ERP_WRITE_MODE=simulation`, `ERP_LIVE_ENABLED=false`, and `SMTP_MODE=simulation`. Do not enable live integrations or introduce real production credentials without separately configuring appropriate approval, policy, and secret-management controls.
