# GenuineGigs Codebase Map

This is the practical “where does the code live and how is it connected?” guide. GenuineGigs is a modular monolith: one FastAPI backend and one Next.js frontend containing Procurement, Operations and SCM modules over a shared platform core.

## Repository structure

```text
GenuineGigs/
├── apps/api/                 FastAPI backend, migrations and backend tests
├── apps/web/                 Next.js frontend and browser tests
├── docs/                     Maintained architecture/product/runbook docs
├── MD-files-for-codex/       Original product and architecture plans
├── infra/                    Local infrastructure configuration
├── packages/shared/          Generated/shared API types
├── scripts/                  Development utilities
├── services/                 Supporting services
└── docker-compose.yml        Local application stack
```

The active migrations are in `apps/api/migrations/versions/`, not a root-level `migrations/` directory.

## Runtime entry points

| Concern | Location |
|---|---|
| API application/router registration | `apps/api/app/main.py` |
| Configuration | `apps/api/app/core/config.py` |
| Authentication and permissions | `apps/api/app/core/security.py`, `core/permissions.py` |
| Database session | `apps/api/app/db/session.py` |
| Shared/legacy ORM models | `apps/api/app/db/models.py` |
| Alembic migrations | `apps/api/migrations/versions/` |
| Background jobs | `apps/api/app/workers.py`, `celery_app.py` |
| Next.js routes | `apps/web/app/` |
| Root frontend layout/styles | `apps/web/app/layout.tsx`, `globals.css` |
| Unified login | `apps/web/app/login/page.tsx`, `components/operations/V2AuthGateway.tsx` |
| Unified product home | `apps/web/app/home/page.tsx` |
| Shared product shell | `apps/web/components/platform/ProductShell.tsx` |
| Product-wide visual system | `apps/web/app/product-system.css` |
| Canonical/legacy route redirects | `apps/web/next.config.mjs` |

`main.py` mounts Procurement, Operations, SCM and platform routers into the same API process. These are logical module boundaries, not unrelated applications.

## Shared core platform

Cross-module primitives live in `apps/api/app/platform/`.

| Capability | Implementation |
|---|---|
| Canonical manufacturing entities/platform persistence | `platform/models.py` |
| Domain/legacy to canonical identity mapping | `platform/catalog.py` |
| Canonical backfill adapters | `platform/backfill.py`, `backfill_cli.py` |
| Source systems, external IDs, receipts and provenance | `platform/integrations.py` |
| Canonical PO ingestion/execution boundary | `platform/purchase_orders.py` |
| Canonical event envelope and outbox writes | `platform/events.py` |
| Event schema/family registry | `platform/event_registry.py` |
| Dispatch, retries and consumer receipts | `apps/api/app/eventing.py` |
| Relationship graph and traversal | `platform/relationships.py` |
| Current/historical factory state | `platform/state.py` |
| Operational cases | `platform/cases.py` |
| ActionIntent, policy, approval, execution and verification | `platform/actions.py` |
| Cross-module work facade | `platform/work.py` |
| Correlation trace assembly | `platform/trace.py` |
| Integrity/data-quality checks | `platform/integrity.py` |
| Shared simulation contract | `platform/simulation.py` |
| Agent platform context | `platform/agent_runtime.py`, `context.py` |
| Platform APIs | `platform/router.py` (`/api/v1/platform/*`) |
| Logged-in product context | `GET /api/v1/platform/app-context` in `platform/router.py` |
| Cross-module home summary | `GET /api/v1/platform/home` in `platform/router.py` |
| Deterministic demo workspaces | `platform/demos.py`, `seed_cli.py` |

```text
External/module mutation
  → integration + provenance boundary
  → canonical entity mutation
  → EventOutbox in the same transaction
  → eventing.py dispatcher
  → schema-validated idempotent consumer
  → EventConsumerReceipt
  → state / plan / case / action update
```

## SCM backend

SCM code is under `apps/api/app/scm/`. The platform owns shared identities, events, actions and provenance; SCM owns supply-chain planning behavior.

| SCM concern | Main files |
|---|---|
| ORM/read models | `scm/models.py` |
| Time-phased planning mathematics | `scm/engine.py` |
| Canonical input snapshot and BOM explosion | `scm/planning.py`, `scm/bom.py` |
| Run orchestration and persisted projections | `scm/service.py` |
| Risk reconciliation and product readiness | `scm/risks.py` |
| Recommendation ranking and simulation | `scm/recommendations.py` |
| Excel preview/mapping/validation/commit | `scm/imports.py` |
| In-product changes and import conflicts | `scm/manual_entries.py` |
| APIs and visualization DTOs | `scm/router.py` (`/scm/*`) |
| Demo patterns | `scm/mock_data.py` |
| Acceptance fixture | `scm/acceptance_fixture.py` |

### Planning pipeline

```text
Canonical masters + inventory + demand + POs + policies
  → planning.py builds an immutable input snapshot
  → service.py creates and executes the planning run
  → engine.py calculates dated balances, pegging and windows
  → persisted projection points/windows/summaries
  → risks.py reconciles risks and product readiness
  → recommendations.py ranks/simulates interventions
  → SCM read APIs and shared ActionIntent boundary
```

SCM proposes consequential changes. It must not directly mutate an ERP/Procurement purchase order; `platform/actions.py` and an approved connector executor own that operation.

### Data ingestion paths

**Excel/file load**

```text
POST /scm/imports/preview
  → imports.py parses, maps and validates sheets
  → import batch + row results
POST /scm/imports/{batch_id}/commit
  → records + provenance + conflict detection
  → fresh planning run
```

**Small changes inside GenuineGigs**

```text
SCM Data Entries UI
  → POST /scm/data-entries
  → manual_entries.py validation and ledger record
  → event/provenance and planning refresh
  → updated projections, risks and Supply Horizon
```

Manual APIs also expose options, entry history, voiding, conflict listing and resolution. Their schema is in `apps/api/migrations/versions/0064_scm_manual_data_entries.py`.

### SCM API groups

`scm/router.py` contains context/schema, import and quality, demand-plan, planning-run, risk/exception, product-readiness, material/supplier, recommendation/action, scenario, Supply Horizon, saved-view/note, manual-entry and conflict endpoints. The Supply Horizon read model is `GET /scm/supply-horizon`.

## SCM frontend

Route files under `apps/web/app/scm/` are thin wrappers. Feature components live under `apps/web/components/scm/`; all SCM HTTP calls and DTO types are centralized in `apps/web/lib/scm-api.ts`.

| URL | Main component |
|---|---|
| `/scm` | `SCMControlTower.tsx` |
| `/scm/materials` | `SCMMaterialExplorer.tsx` |
| `/scm/materials/[materialId]` | `SCMMaterialDetail.tsx` |
| `/scm/horizon` | `SCMSupplyHorizon.tsx` |
| `/scm/readiness` | `SCMRemainingWorkspace.tsx` |
| `/scm/exceptions` | `SCMExceptions.tsx` |
| `/scm/actions` | `SCMRemainingWorkspace.tsx` |
| `/scm/scenarios` | `SCMRemainingWorkspace.tsx` |
| `/scm/suppliers` | `SCMRemainingWorkspace.tsx` |
| `/scm/data-entries` | `SCMDataEntryCenter.tsx` |
| `/scm/imports` | `SCMImports.tsx` |

`SCMShell.tsx` owns SCM context loading, local navigation definitions and SCM query refresh behavior. It renders the shared `ProductShell.tsx`, which owns the global product rail, workspace/plant context, search, notifications, refresh, profile and module switching. The authoritative SCM feature treatment is `apps/web/app/scm-product.css`; shared shell decisions belong in `product-system.css`. Earlier structural/compatibility rules remain in `scm-v1.css` and `scm.css`.

### Supply Horizon connection

```text
app/scm/horizon/page.tsx
  → components/scm/SCMSupplyHorizon.tsx
  → getSCMHorizon() in lib/scm-api.ts
  → GET /scm/supply-horizon in scm/router.py
  → latest persisted planning run/projection
  → time-phased segments + dated PO/intervention/deadline events
```

`SCMSupplyHorizon.tsx` owns proportional date positioning, month/tick axis, virtualized rows, segment/event rendering, tooltips, filters, selection and the detail drawer. It must not invent SCM balances. Semantic segments and events come from the persisted backend read model. Structural `.supply-horizon-page`/`.sh-*` rules begin in `scm-v1.css`; their authoritative product treatment is in `scm-product.css`. Virtualization uses `@tanstack/react-virtual`.

## Procurement

Procurement predates the module folders, so much of it remains directly under `apps/api/app/`.

| Concern | Main files |
|---|---|
| Workflow/domain services | `domains/workflows.py`, `domains/state_machine.py` |
| Newer procurement/PO amendments | `procurement_v2.py` |
| Excel and ERP exchange | `excel_connector.py`, `erp.py` |
| Connectors | `integrations.py`, `connector_sdk.py` |
| Policies/governed execution | `procurement_policy.py`, `policy_decision.py`, `governed_execution.py` |
| Agent runtime | `agent_service.py`, `agent_runtime.py`, `routers/agents.py` |
| Main APIs | `routers/backend_plan.py` |

Canonical Procurement pages live under `apps/web/app/procurement/` (`requirements`, `rfqs`, `quotations`, `orders`, `inbound`, `quality`, etc.). `components/industrial/IndustrialConsole.tsx` remains the domain workspace and now renders inside `ProductShell.tsx`. Former root URLs such as `/control-centre`, `/rfq-builder` and `/po-drafts` redirect to canonical `/procurement/*` routes in `next.config.mjs`.

## Operations

| Concern | Main files |
|---|---|
| APIs and services | `operations/router.py`, `operations/service.py` |
| Live state | `operations/state.py` |
| Normalization/ingestion | `operations/normalization.py`, `operations/integrations.py` |
| Operations agents | `operations/agents.py` |
| Recovery execution/verification | `operations/recovery/service.py`, `verification.py` |
| Recovery ranking/effectiveness | `operations/recovery/ranking.py`, `effectiveness.py` |

Operations ORM records remain mainly in `apps/api/app/db/models.py`. Canonical frontend routes are under `apps/web/app/operations/`, reusable screens under `apps/web/components/operations/`, and domain styling in `apps/web/app/operations.css`. `V2AppShell.tsx` adapts Operations navigation and Gigi into the shared `ProductShell.tsx`. The old `/v2/*` URLs remain compatibility entry points and redirect to `/operations/*`.

## Unified frontend structure

```text
/login
  → one authenticated workspace session
  → /home cross-module attention and module summary
  → ProductShell global rail
       ├── /procurement/*  Procurement local navigation + IndustrialConsole
       ├── /scm/*          SCM local navigation + SCM feature screens
       ├── /operations/*   Operations local navigation + Operations screens
       └── /platform       Shared-core administration/observability
```

`ProductShell.tsx` is the single owner of global navigation, workspace/plant identity, command search, refresh feedback, notifications, module switching and profile/sign-out. Module shells provide only local navigation and module-specific assistant/refresh adapters. Do not add another module-level login, global sidebar or duplicate workspace header.

Frontend API types for the shell and home live in `apps/web/lib/api.ts` (`PlatformAppContext`, `PlatformHome`). Their authenticated backend read models live in `apps/api/app/platform/router.py`. Access is computed from the selected workspace membership, role, capabilities and feature flags; it is not hard-coded in the browser.

## Recent architecture and SCM migrations

| Migration | Purpose |
|---|---|
| `0057_scm_control_tower_scaffold.py` | Initial SCM scaffold |
| `0058_core_platform_foundation.py` | Shared platform foundation |
| `0059_core_platform_completion.py` | Additional core phases |
| `0060_scm_readiness_core_hardening.py` | Core readiness hardening |
| `0061_scm_phases_0_3.py` | SCM phases 0–3 |
| `0062_scm_v1_remaining_phases.py` | Remaining SCM v1 phases |
| `0063_repair_tenant_business_number_indexes.py` | Tenant index repair |
| `0064_scm_manual_data_entries.py` | Manual entries/conflicts |

Do not modify an already-applied migration to change behavior; add a forward migration.

## Tests and reading order

| Behavior | Tests |
|---|---|
| Connector-to-verification core proof | `apps/api/tests/test_core_architecture_e2e.py` |
| Platform foundation/phases | `test_platform_foundation.py`, `test_core_platform_phases.py` |
| SCM mathematics | `test_scm_engine.py` |
| SCM API/read models | `test_scm_api.py` |
| SCM Excel ingestion | `test_scm_imports.py` |
| Operations/recovery | `test_operational_v2.py`, `test_recovery_v21.py` |
| Procurement amendments | `test_po_amendments.py` |
| Browser workflows | `apps/web/e2e/` |
| Unified product context/home | `apps/api/tests/test_unified_product_context.py` |

Start with `test_core_architecture_e2e.py` for the shared architecture. For SCM, read `test_scm_engine.py` → `scm/planning.py` → `scm/service.py` → `scm/router.py` → `apps/web/lib/scm-api.ts`.

## Where to make common changes

| Desired change | Start here |
|---|---|
| Planning calculation | `scm/engine.py` |
| Planning inputs/BOM explosion | `scm/planning.py` |
| Run persistence/orchestration | `scm/service.py` |
| Risk semantics | `scm/risks.py` |
| Recommendation ranking/simulation | `scm/recommendations.py` |
| Excel mapping/entity | `scm/imports.py` |
| Manual data-entry type | `scm/manual_entries.py`, `scm/router.py`, `SCMDataEntryCenter.tsx` |
| Supply Horizon DTO | `scm/router.py`, `apps/web/lib/scm-api.ts` |
| Supply Horizon component | `SCMSupplyHorizon.tsx` |
| SCM product design system | `apps/web/app/scm-product.css` |
| Global shell/navigation/login/home | `ProductShell.tsx`, `product-system.css`, `V2AuthGateway.tsx`, `app/home/page.tsx` |
| Module availability/home counts | `platform/router.py` (`/app-context`, `/home`) |
| Canonical route or legacy redirect | `apps/web/app/{procurement,scm,operations}/`, `apps/web/next.config.mjs` |
| Older SCM structural/compatibility styling | `apps/web/app/scm-v1.css`, `apps/web/app/scm.css` |
| Canonical entity/relationship/state | `apps/api/app/platform/` |
| Consequential external action | `platform/actions.py` plus connector executor |
| New router | router file plus `apps/api/app/main.py` |
| Schema change | new `apps/api/migrations/versions/*` migration plus ORM update |

## Documentation

- Complete platform + SCM handoff: `docs/GENUINEGIGS_PLATFORM_AND_SCM_IMPLEMENTATION_HANDOFF.md`
- Core goal: `MD-files-for-codex/GENUINEGIGS_CORE_PLATFORM_ARCHITECTURE.md`
- SCM plan: `MD-files-for-codex/SCM_PLAN.md`
- Current-to-target map: `docs/architecture/current-to-target-map.md`
- Hardening audit: `docs/architecture/core-hardening-implementation-audit.md`
- Readiness report: `CORE_ARCHITECTURE_READINESS.md`
- Event catalog: `docs/platform/event-catalog.md`
- Core runbook: `docs/runbooks/core-platform.md`
- SCM readiness: `docs/runbooks/scm-developer-readiness.md`
- Documentation index: `docs/README.md`

## Architectural rule of thumb

Use the platform for shared identity, provenance, events, relationships, state, actions, policy, approval, audit and simulation contracts. Keep planning algorithms in SCM, purchasing workflows in Procurement, and production/recovery logic in Operations. A module may extend the core, but it should not create a parallel shared identity or bypass the shared action boundary.
