# GenuineGigs Manufacturing Agent OS

GenuineGigs is one universal manufacturing operating system with three
complementary product domains—not three replacement versions:

- **Procurement:** requirement-to-receipt execution and supplier coordination.
- **Operations and recovery:** production visibility, deviations, quality,
  maintenance, recovery, and continuous improvement.
- **Supply-chain planning:** material projections, shortages, pegging, scenarios,
  and recommended actions.

Start with the [documentation map](docs/README.md). Product plans and handoffs
are grouped under `docs/products/`; shared architecture and operating guidance
remain under `docs/architecture/`, `docs/platform/`, and `docs/runbooks/`.

The monorepo is organized by deployable application and then product domain:

```text
apps/
  api/app/
    operations/     # factory operations + recovery intelligence
    scm/            # supply-chain control tower
    core/, db/       # shared platform foundations
  web/
    app/v2/         # operations routes (compatibility URL)
    components/operations/
    app/scm/        # supply-chain routes
docs/
  products/
    procurement/
    operations/
    supply-chain/
  platform/
```

First production slice of a role-based Manufacturing Agent OS, starting with a procurement agent module for purchase-side RFQ, quotation comparison, negotiation, PO draft, inbound receipt, inspection, and exception tracking.

The current role-agent slice includes private membership-scoped conversations, work-item context, governed proposals, structured manager delegation, formal team status, demo/fresh workspaces, invitations, MFA/session contracts, and deterministic degraded operation.

## Product Direction

- ERP remains the system of record.
- GenuineGigs acts as the execution, agent, task, evidence, and exception layer above ERP.
- V1 uses simulated Oracle/SAP-style imports and posting logs.
- The interface is an industrial operations console, not a generic AI SaaS app.

## Workspace

- `apps/web`: Next.js frontend.
- `apps/api`: FastAPI backend.
- `packages/shared`: shared product contracts and baseline data.
- `infra`: local development and deployment support.

## V1 Module

Procurement Agent Module:

```text
material need -> RFQ -> quotations -> comparison -> negotiation -> PO draft
-> supplier acknowledgement -> gate/store/inspection -> exception closure
```

## Run locally

```bash
docker compose up --build
```

Compose runs PostgreSQL, Redis, private MinIO buckets, Mailpit, a one-shot Alembic migration job, a one-shot idempotent seed job, the API, Celery worker/beat, and the production Next.js server. The API process never creates or migrates schema.

Open the Compose UI at `http://localhost:3000` or `http://127.0.0.1:3000`. During loopback development the web client automatically uses the same hostname for port 8000, preventing `localhost` and `127.0.0.1` from creating separate authentication-cookie scopes.

### Login troubleshooting

- A Docker API traceback uses Linux paths and PostgreSQL. A traceback with Windows paths and `sqlite3` is from a separately running local Uvicorn process, not the Compose API.
- Check the active stack with `docker compose ps` and `docker compose logs api migrate`.
- If a disposable local SQLite database reports a missing column, preserve the old file by renaming `apps/api/genuinegigs_dev.db`, then run `alembic upgrade head` and `python -m app.db.seed_cli` from `apps/api`.
- Do not remove the Compose PostgreSQL volume for a local SQLite error.

External effects default to `ERP_WRITE_MODE=simulation`, `ERP_LIVE_ENABLED=false`, and `SMTP_MODE=simulation`. Oracle cannot receive a write unless the PO and integration event are separately approved and both live controls are enabled.

Copy `.env.example` to `.env` and set `GROQ_API_KEY` to use Groq. With no key, local Compose keeps workflows and the governed demo usable through deterministic fallback. Set `AGENT_ENABLED=false` for a deployment-wide emergency stop.

The seeded Apex workspace remains the product demo. An administrator can create
a clean customer workspace and its first plant from `/workspace/setup`. The
creator becomes that workspace's Admin owner; fresh workspaces contain no Apex
users or sample transactional records. From `/admin`, the Admin creates employee
login accounts, assigns each account one governed business role, plant access,
department, and reporting manager, and the server provisions the matching
role-specific agent. Those employees can then sign in with their own email and
temporary password. Add the six operational roles to reach an import-ready
workspace, then configure the Excel/CSV external-system connection from
`/integrations`.

Architecture and operations:

- `docs/architecture/industrial-v1.md`: complete procurement/runtime guide.
- `docs/architecture/role-agent-os.md`: context isolation, authority, communication, and fresh workspaces.
- `docs/runbooks/agent-operations.md`: rollout, emergency stop, incident, retention, and recovery.
- `deploy/helm/genuinegigs`: portable production Helm chart.

## Development checks

```bash
npm run typecheck
npm run build:web
npm run check:api-contract
npm run test:api
npm run test:e2e
```

Schema changes must be made through Alembic. Application startup never calls `create_all`; tests create disposable SQLite metadata in `tests/conftest.py` while integration tests run against PostgreSQL.

## Excel external-system golden demonstration

The checked-in workbook package under
`apps/api/tests/fixtures/excel_erp/` is the first complete external-system
simulator. It contains organization, reporting, material, supplier, capability,
requirement, PO, receipt, quality, invoice, and payment data plus invalid,
duplicate, hostile-formula, partial, and stale/conflicting variants.

Regenerate the deterministic fixture package:

```bash
cd apps/api
.venv/bin/python tests/fixtures/excel_erp/generate_fixtures.py
```

Run the end-to-end scenario without ERP credentials or manual database edits:

```bash
cd apps/api
.venv/bin/pytest -q tests/test_golden_procurement_demo.py
```

That executable scenario creates a clean workspace, imports the workbook,
sources and verifies a quotation, compares and approves it, creates and
dispatches a simulated PO, records acknowledgement and inbound events, handles
rejection/replacement/reinspection, matches the invoice, prepares (but does not
release) the finance handoff, closes the lifecycle only after read-only payment
evidence, exports a versioned workbook, verifies reconciliation, re-imports it
without duplicates, and proves a stale workbook cannot overwrite newer
operational state.

Run the full spreadsheet and connector safety matrix:

```bash
cd apps/api
.venv/bin/pytest -q tests/test_excel_connector.py tests/test_connector_conformance.py
```

Vendor adapters are contract boundaries until validated with customer
credentials. Excel/CSV and the provider-neutral conformance harness are the
tested integration paths; do not describe Oracle, SAP, Dynamics, or Odoo as
customer-verified from these tests.
