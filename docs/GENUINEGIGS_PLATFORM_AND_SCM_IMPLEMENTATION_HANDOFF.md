# GenuineGigs — Complete Product, Architecture, Runtime, and Operations Guide

**Document date:** 2026-09-07  
**Implementation baseline:** migrations through `0074_domain_case_links` and the unified proactive Gigi companion  
**Repository:** `GenuineGigs`  
**Audience:** Engineers, product leaders, operators, implementers, QA, DevOps, and AI assistants that need a complete working mental model of the current product.  
**Source plans:**

- `MD-files-for-codex/GENUINEGIGS_CORE_PLATFORM_ARCHITECTURE.md`
- `MD-files-for-codex/SCM_PLAN.md`

This document describes what was actually implemented after those plans were provided. It is a handoff, not a new speculative roadmap. When this document conflicts with an old plan, the repository is authoritative.

## 2026-09-07 unification implementation delta

The product now has a shared, versioned `factory-v1` workbook envelope at
`/api/v1/platform/factory-imports`. One preview delegates normalized sheets to
the existing Procurement and SCM processors and to an Operations-owned workbook
adapter. Preview does not write domain records. Commit uses a nested transaction,
reruns domain reference validation, records canonical ingestion receipts, and
rolls back all child writes if any domain cannot commit. The original source
hash, child batch IDs, row results and canonical reconciliation remain in the
existing integration models.

Workbook sheets are domain-prefixed: `PROC_*`, `SCM_*` and `OPS_*`.
`Manifest.schema_version` must equal `factory-v1`. Data & Integrations provides
upload, validation results, commit history and the canonical automotive
template. Development, test and staging also provide an explicit MAT-182 loader.
It imports through the same preview/commit boundary, runs SCM planning, then
opens the shared recovery case. The demo endpoint is unavailable in production.

Browser API traffic defaults to same-origin URLs. Next.js forwards `/api`,
`/auth`, `/scm`, `/integrations` and `/health` to `API_INTERNAL_BASE_URL`.
Containers set it to `http://api:8000`; local development defaults to
`http://127.0.0.1:8000`. `NEXT_PUBLIC_API_BASE_URL` is now only an explicit
override. This avoids cookie, hostname and CORS drift across localhost, WSL and
Docker.

The Command Center does not sum unlike or overlapping exposure metrics. It
shows decisions, ranked cases, recovery monitoring, separately typed exposure,
work and verified outcomes. Request failure appears as unknown/unavailable, not
healthy. The shared decision inbox projects recovery choices, assigned
Procurement approvals, approval work and authorized ActionIntent approvals;
mutations remain owned by their domain services.

Gigi is one shell-level companion with Attention, Brief, Plan, Commitments and
Ask. It preserves acknowledge, snooze and dismiss state, resolves expired
snoozes, closes insights for inactive cases, respects quiet-hour/proactivity
preferences, restores failed chat drafts, supports Enter to send and Shift+Enter
for a newline, and reports context failures explicitly. Model input contains
bounded dialogue history plus deterministic factory context; dialogue is
untrusted, citations are restricted to supplied evidence, and quantities absent
from grounded input cause a deterministic fallback. Gigi neither ranks options
nor executes external actions.

Recovery verification requires distinct identified planning cycles, fresh
observations, a numeric threshold check and any configured duration. A new unsafe
observation reopens a recovered case. Projected exposure is never automatically
converted into business value; attribution requires a separate reconciled actual
and counterfactual calculation.

Completed SCM planning runs now create replay-safe recovery observations for
active material cases. The initial coverage value is intentionally conservative:
it is `1` only when every projection point for the case material has zero
shortage, and stale projection inputs remain stale evidence. One clean run starts
monitoring; only the configured number of distinct fresh cycles verifies recovery.

The supported deployment boundary remains an advisory pilot. Repository tests
cannot prove customer ERP mappings, live data quality, connector reconciliation,
network behavior, backup restoration, security acceptance or operator UAT in a
specific factory. Those gates remain required before production deployment.

---

# 1. Executive summary

GenuineGigs is now organized as a **modular manufacturing application over a shared core platform**.

```text
External files / ERP-like sources / manual observations
                         ↓
             Integration and ingestion boundary
                         ↓
     Canonical identity + provenance + transactional events
                         ↓
         Shared relationships and factory-state projections
                         ↓
         Deterministic planning / domain intelligence
                         ↓
           OperationalCase and recommendations
                         ↓
 ActionIntent → policy → approval → execution → outcome → verification
                         ↓
       Procurement / SCM / Operations user experiences
```

The current deployment remains a **modular monolith**:

- one FastAPI backend;
- one PostgreSQL database;
- one Next.js frontend;
- Redis and Celery for asynchronous work;
- a transactional database outbox for canonical events;
- optional simulation/developer-lab services.

This was intentional. The implementation does not introduce speculative microservices, Neo4j, a lakehouse, Kubernetes, a full digital twin, or autonomous machine control.

The central architecture passed the deterministic connector-to-verification acceptance scenario documented in `CORE_ARCHITECTURE_READINESS.md`. SCM V1 passed its selected planning/core acceptance suite as documented in `SCM_V1_READINESS.md`. The product is structurally ready for design-partner SCM validation, but it is not represented as fully production-proven at thousands-of-material scale.

---

# 2. Product structure today

The three business modules are:

| Module | Responsibility | Canonical frontend root |
|---|---|---|
| Procurement | Requirement-to-order-to-receipt purchasing workflows | `/procurement` |
| SCM | Time-phased supply planning, risk, recommendations, scenarios and planner workflows | `/scm` |
| Operations | Plant production state, deviations and verified recovery | `/operations` |

Shared platform capabilities live under:

| Surface | Location |
|---|---|
| Platform API | `/api/v1/platform/*` |
| Platform frontend | `/platform` |
| Unified authenticated home | `/home` |
| Login | `/login` |

All modules use the same authenticated browser session. The unified frontend shell provides global module switching, local module navigation, workspace and plant context, search, refresh feedback, notifications, assistant entry points, profile and logout.

Important frontend files:

- `apps/web/components/platform/ProductShell.tsx`
- `apps/web/app/product-system.css`
- `apps/web/app/home/page.tsx`
- `apps/web/components/operations/V2AuthGateway.tsx`
- `apps/web/next.config.mjs`

Legacy Procurement root routes and Operations `/v2/*` routes remain as compatibility redirects to canonical module URLs.

---

# 3. Repository map

```text
GenuineGigs/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── platform/       Shared manufacturing platform
│   │   │   ├── scm/            SCM domain and planning engine
│   │   │   ├── operations/     Operations domain and recovery
│   │   │   ├── db/             Shared/legacy ORM models and seeds
│   │   │   ├── eventing.py     Outbox dispatch and consumers
│   │   │   └── main.py         FastAPI router registration
│   │   ├── migrations/         Alembic migrations
│   │   └── tests/              Backend tests
│   └── web/
│       ├── app/                 Next.js routes and CSS layers
│       ├── components/
│       │   ├── platform/       Unified shell and platform console
│       │   ├── scm/            SCM product screens
│       │   ├── operations/     Operations screens and adapters
│       │   └── industrial/     Procurement workspace
│       ├── lib/                 Typed API clients
│       └── e2e/                 Playwright workflows
├── docs/                        Maintained engineering documentation
├── MD-files-for-codex/          Original product/architecture plans
├── services/                    Simulation/developer-lab services
└── docker-compose.yml           Local stack
```

For a file-by-file navigation guide, also read `docs/CODEBASE_MAP.md`.

---

# 4. Central platform implementation

## 4.1 Canonical manufacturing model

The shared canonical records are primarily in:

- `apps/api/app/platform/models.py`
- `apps/api/app/db/models.py`

Implemented platform records include:

### Material and product

- `PlatformMaterial`
- `PlatformMaterialSite`
- `PlatformProduct`
- `PlatformBOM`
- `PlatformBOMItem`

### Inventory

- `PlatformInventoryLocation`
- `PlatformInventoryPosition`

### Cross-module identity and trust

- `ExternalEntityReference`
- `DataProvenance`
- `DataQualityIssue`
- `SourceSystem`

### State and relationships

- `EntityRelationship`
- `PlatformStateSnapshot`
- `MaterialStateProjection`

### Actions and cases

- `ActionIntent`
- `ActionPolicyEvaluation`
- `ActionApproval`
- `ActionExecution`
- `ActionOutcome`
- `OperationalCase`

### Purchasing, production references and simulation

- `PlatformPurchaseOrder`
- `PlatformPurchaseOrderLine`
- `PlatformWorkOrderReference`
- `PlatformScenarioDefinition`
- `PlatformSimulationRun`

Existing shared records in `app/db/models.py` remain authoritative for concepts already shared across modules, including:

- tenant/workspace;
- company/organization;
- plant/site;
- plant area;
- production line/work center;
- plant asset/equipment;
- supplier;
- production work order;
- task, notification and audit records;
- event outbox and consumer receipts.

## 4.2 Canonical status by business entity

| Entity | Current status | Compatibility dependency |
|---|---|---|
| Organization/Tenant | Canonical | Existing `Tenant` and `Company` are shared records. |
| Site/Plant | Canonical | Existing `Plant` is authoritative. |
| Area | Canonical | Existing `PlantArea` is authoritative. |
| Work center/line | Canonical | Existing `ProductionLine` is the work-center identity. |
| Equipment | Canonical | Existing `PlantAsset` is authoritative. |
| Supplier | Canonical | Existing shared `Supplier` is used directly. |
| Material | Canonical, partially migrated | Legacy `Item` and domain `SCMMaterial` map to `PlatformMaterial`. |
| Product | Canonical, partially migrated | Operations product tables remain behavior-level records and are mapped. |
| BOM | Canonical, partially migrated | Domain/import BOM records remain supported. |
| Inventory | Canonical read model, partially migrated | SCM snapshots and Operations positions remain optimized source projections. |
| Purchase order | Canonical, partially migrated | Procurement PO records remain transaction/behavior owners. |
| Work order | Canonical shared identity, partially migrated | Operations work orders are bridged through `PlatformWorkOrderReference`. |

No flag-day deletion of legacy tables was performed. New shared behavior should use canonical IDs or explicit mapping adapters instead of introducing another identity.

## 4.3 Identity mapping and backfill

Main files:

- `platform/catalog.py`
- `platform/backfill.py`
- `platform/backfill_cli.py`

Implemented behavior:

- maps existing module records to canonical entities;
- uses `ExternalEntityReference` to retain the source-system/external ID relationship;
- prevents silent remapping of an already mapped source identity;
- creates canonical material provenance during mapping;
- backfills existing tenants incrementally;
- retains legacy tables for compatibility.

The rule is:

```text
(tenant, source system, entity type, external ID)
                       ↓
             one canonical entity ID
```

## 4.4 Integration and provenance boundary

Main files:

- `platform/integrations.py`
- `platform/purchase_orders.py`
- `scm/imports.py`
- `scm/manual_entries.py`

Implemented records and behavior include:

- source-system registry;
- ingestion receipts;
- source record IDs and payload hashes;
- mapping versions;
- accepted/rejected ingestion state;
- canonical identity resolution;
- `DataProvenance` linked to canonical mutations;
- correlation IDs carried into events and downstream processing;
- duplicate source-record protection;
- connector health summaries.

`platform/purchase_orders.py` provides the hardened reference flow for externally sourced PO delivery changes. It resolves canonical site, supplier, material and PO identities, records provenance, changes the canonical PO representation and creates a transactional event.

## 4.5 Canonical event backbone

Main files:

- `platform/events.py`
- `platform/event_registry.py`
- `apps/api/app/eventing.py`
- event ORM records in `apps/api/app/db/models.py`

Every canonical event uses a structured envelope carrying:

- event ID and event type;
- schema/event version;
- tenant and plant scope;
- source system;
- actor membership;
- subject type and ID;
- occurred and recorded timestamps;
- correlation and causation IDs;
- validated payload.

Events are written to `EventOutbox` in the same database transaction as the business mutation. Dispatching provides:

- registered consumers;
- per-consumer receipts;
- idempotent replay;
- retry counts and next-attempt time;
- retained error detail;
- dead-letter state after the retry limit.

The event catalog contains the required Procurement, SCM, Operations and platform action families. Important implemented examples include:

```text
requirement.created
rfq.created
supplier.quote_received
purchase_order.created
purchase_order.updated
purchase_order.rescheduled
goods_receipt.recorded

forecast.updated
inventory.updated
supplier.commitment.updated
scm.planning.completed
material.shortage.predicted
material.excess.predicted
scm.intervention.recommended
scm.manual_data.recorded
scm.manual_data.voided

work_order.released
work_order.started
work_order.completed
production.recorded
production.deviation.detected
downtime.started
downtime.ended
recovery.case.created
recovery.action.executed
recovery.verified

platform.action.proposed
platform.action.approved
platform.action.rejected
platform.action.executed
platform.action.execution_failed
platform.action.outcome_verified
```

Older event aliases remain recognized where required for migration compatibility.

## 4.6 Relationship graph

Main file: `platform/relationships.py`

PostgreSQL remains the graph store. No Neo4j dependency was introduced.

`EntityRelationship` supports:

- tenant and optional plant scope;
- source and target canonical identity;
- relationship type;
- source system;
- provenance ID;
- confidence;
- validity interval;
- metadata.

Implemented graph capabilities:

- `connect`;
- neighbor lookup;
- bounded upstream/downstream traversal;
- path search;
- dependencies;
- dependents;
- downstream impact;
- idempotent tenant graph synchronization.

Graph synchronization covers relationships derived from BOMs, inventory, suppliers, purchase orders, work orders, production lines and equipment. The accepted cross-module path is:

```text
PurchaseOrder → Material → Product → WorkOrder → WorkCenter
```

## 4.7 Factory state

Main file: `platform/state.py`

`FactoryStateService` provides the shared contract over domain-optimized projections rather than forcing every state into one table.

Implemented paths:

- current state;
- state at a timestamp where snapshots exist;
- state history;
- canonical material state;
- work-order state;
- broader factory context.

Material state can include:

- observed inventory;
- reserved/available values;
- incoming supply;
- derived runway;
- predicted risk and stockout timing;
- source freshness;
- provenance;
- related risks and graph relationships;
- calculated timestamp and algorithm version.

`scm.planning.completed` refreshes canonical material projections and writes historical `PlatformStateSnapshot` records.

## 4.8 Operational cases

Main files:

- `platform/cases.py`
- `OperationalCase` in `platform/models.py`

A case is the shared representation of a risk or deviation requiring coordinated handling. It retains:

- tenant/plant scope;
- case type and severity;
- canonical entity reference;
- source event;
- correlation ID;
- structured context/evidence;
- status and resolution evidence.

SCM material shortages reconcile into reusable cases instead of creating a new case on every planning run.

## 4.9 Governed action lifecycle

Main file: `platform/actions.py`

The implemented lifecycle is:

```text
Recommendation
    ↓
ActionIntent
    ↓
Policy evaluation
    ↓
Approval or rejection
    ↓
Simulated/external/internal execution
    ↓
Execution receipt
    ↓
Observed outcome
    ↓
Independent state-based verification
    ↓
Audit and case resolution
```

An `ActionIntent` can retain actor/membership, target, action type, parameters, reason, evidence, correlation ID, originating case, expected impact, confidence and risk level.

Implemented action services include:

- idempotent proposal;
- deterministic policy evaluation;
- approval/rejection;
- safe simulated execution;
- external executor boundary;
- internal governed execution;
- execution error retention;
- outcome recording;
- explicit recovery verification.

Critical invariant: **successful connector execution does not automatically mean operational recovery**. Recovery is verified from new post-action state.

SCM therefore proposes PO rescheduling, purchasing or transfer actions; it does not directly update Procurement-owned external records.

## 4.10 Correlation trace

Main file: `platform/trace.py`

API:

```text
GET /api/v1/platform/traces/{correlation_id}
```

The trace service assembles existing records chronologically instead of copying them into another trace database. Depending on the flow, it includes:

- ingestion and source receipt;
- provenance/mapping;
- canonical mutation;
- outbox event;
- consumer receipts;
- state projection/snapshot;
- planning run;
- SCM risk and case;
- recommendation;
- ActionIntent;
- policy and approval;
- execution and external receipt;
- outcome and verification;
- audit records.

## 4.11 Simulation contract

Main file: `platform/simulation.py`

The shared contract standardizes scenario/run metadata while allowing SCM and Operations to use different algorithms. It covers:

- scenario identity and domain;
- baseline state;
- overrides/actions;
- time horizon;
- algorithm and version;
- execution status;
- outputs and predicted metrics;
- provenance/timestamps;
- optional actual-outcome comparison.

This is not a full digital twin or whole-factory discrete-event simulator.

## 4.12 Integrity checks

Main file: `platform/integrity.py`

Checks cover:

- duplicate canonical materials;
- orphan SCM/module materials;
- invalid supplier mappings;
- missing site ownership;
- broken BOM references;
- broken purchase-order references;
- broken work-order references.

API:

```text
GET /api/v1/platform/integrity
```

---

# 5. Shared platform APIs

The platform router is `apps/api/app/platform/router.py`.

## Product/session context

```text
GET /api/v1/platform/app-context
GET /api/v1/platform/home
```

These power the unified product shell and home. Module access is derived from the authenticated workspace membership, role, permissions, capabilities and feature flags.

## Canonical catalog

```text
GET /api/v1/platform/organizations
GET /api/v1/platform/sites
GET /api/v1/platform/manufacturing-hierarchy
GET /api/v1/platform/materials
GET /api/v1/platform/suppliers
GET /api/v1/platform/products
GET /api/v1/platform/products/{product_id}/boms
```

## State, graph and trace

```text
GET /api/v1/platform/materials/{material_id}/state
GET /api/v1/platform/work-orders/{work_order_id}/state
GET /api/v1/platform/factory-context
GET /api/v1/platform/state/{entity_type}/{entity_id}
GET /api/v1/platform/state/{entity_type}/{entity_id}/history
GET /api/v1/platform/relationships/{entity_type}/{entity_id}
GET /api/v1/platform/impact/{entity_type}/{entity_id}
GET /api/v1/platform/traces/{correlation_id}
```

## Quality, sources, cases and work

```text
GET /api/v1/platform/integrity
GET /api/v1/platform/data-quality
GET /api/v1/platform/provenance
GET /api/v1/platform/cases
GET /api/v1/platform/work
GET /api/v1/platform/sources
GET /api/v1/platform/agent-context
```

## Governed actions

```text
GET  /api/v1/platform/actions
POST /api/v1/platform/actions
GET  /api/v1/platform/actions/{action_id}
POST /api/v1/platform/actions/{action_id}/decision
POST /api/v1/platform/actions/{action_id}/execute
```

Mutations require authentication, CSRF protection and the appropriate role/capability boundary.

---

# 6. SCM implementation

SCM business code is in `apps/api/app/scm/`. SCM owns planning behavior; the platform owns shared identities, provenance, graph, cases, actions, policy and audit.

## 6.1 SCM data model

`apps/api/app/scm/models.py` contains:

### Master and plant planning data

- `SCMMaterial`
- `SCMMaterialPlant`
- `SCMStorageLocation`
- `SCMMaterialPlantPolicy`
- `SCMUOMConversion`
- `SCMMaterialSupplier`
- `SCMCustomer`
- `SCMMaterialCustomerUsage`
- `SCMBOM`
- `SCMBOMLine`

These are SCM behavior/import models. `SCMMaterial` is not intended to become another universal material identity; it maps to `PlatformMaterial`.

### Planning inputs

- `SCMInventorySnapshot`
- `SCMDemandForecast`
- `SCMMaterialRequirement`
- `SCMSupplyOrder`
- `SCMSupplyScheduleLine`
- `SCMGoodsReceipt`
- `SCMDataSourceState`
- `SCMPlanningPolicySet`
- `SCMPlanningProfile`
- `SCMDemandPlan`
- `SCMDemandBucket`

### Scenarios and overrides

- `SCMPlanningScenario`
- `SCMScenarioOverride`
- `SCMPlanningAdjustment`
- `SCMManualDataEntry`

### Planning outputs/read models

- `SCMPlanningRun`
- `SCMPlanningInputSnapshot`
- `SCMPlanningEvent`
- `SCMMaterialProjectionPoint`
- `SCMSupplyDemandPeg`
- `SCMMaterialRiskSummary`
- `SCMShortageWindow`
- `SCMMaterialRisk`
- `SCMProductReadiness`
- `SCMComponentReadiness`
- `SCMPlanningRunDelta`
- `SCMRecommendation`
- `SCMRecommendationSimulation`
- `SCMSavedView`
- `SCMPlannerNote`

## 6.2 Planning pipeline

Main files:

- `scm/planning.py`
- `scm/bom.py`
- `scm/engine.py`
- `scm/service.py`
- `scm/risks.py`
- `scm/recommendations.py`

The pipeline is:

```text
Canonical masters + SCM plant policy + inventory + demand + supply
                              ↓
       Immutable planning input snapshot with a payload hash
                              ↓
       Demand normalization using configured precedence
                              ↓
      Effective-dated, nested BOM explosion with lineage
                              ↓
        Dated inventory projection across the horizon
                              ↓
         FIFO supply/demand pegging and runway
                              ↓
       Shortage/excess windows and severity scoring
                              ↓
       Product/work-order component readiness
                              ↓
       Change drivers compared with the previous run
                              ↓
        Ranked and explainable recommendations
                              ↓
 Persisted projections/read models + canonical completion event
```

The frontend reads persisted results. It does not calculate BOM demand, inventory balances or risk states.

## 6.3 Deterministic planning capabilities

Implemented behavior includes:

- 30, 90, 210 and 365-day horizons;
- daily planning points with optional aggregation;
- opening/on-hand/available inventory;
- dated demand and supply events;
- configurable same-day event ordering;
- demand-source precedence to prevent double counting;
- nested BOM explosion;
- effective-date BOM selection;
- scrap-factor handling;
- BOM-cycle detection;
- FIFO pegging;
- projected closing balance;
- safety-stock breach and stockout dates;
- runway calculation;
- consecutive shortage windows and recovery dates;
- sustained excess windows;
- material severity and priority factors;
- product/work-order readiness;
- previous-run change explanations;
- immutable input snapshots for reproducibility.

## 6.4 Risks and product readiness

`scm/risks.py`:

- reconciles material risks semantically across runs;
- links risks to canonical material IDs;
- creates/updates shared `OperationalCase` records;
- records structured root causes and affected entities;
- builds product readiness and component evidence;
- stores run-to-run drivers such as PO date, demand and inventory changes.

Readiness states include ready, at risk and blocked. A missing or unsafe component can block the associated product/work order.

## 6.5 Recommendations

`scm/engine.py` and `scm/recommendations.py` implement deterministic candidate generation, ranking and simulation.

Supported recommendation families include:

- pull in a purchase-order/supply receipt;
- push out a receipt when excess exists;
- cancel or reduce eligible supply;
- create a new purchase requirement/order candidate;
- initial interplant transfer candidate;
- conservative PO-date intervention fallback for an uncovered shortage.

Recommendations retain:

- material and source entity;
- quantity and proposed date;
- reason and evidence;
- expected impact;
- score dimensions and rank;
- feasibility/contractual constraints;
- decision status.

A recommendation is simulated before conversion into an external action. The acceptance path requires the simulation to demonstrate risk improvement/resolution before an ActionIntent is created.

## 6.6 Scenario Lab

Scenarios provide:

- immutable baseline planning-run reference;
- isolated overrides;
- inventory, demand, safety-stock, supply-date and supply-quantity changes;
- save and duplicate;
- execute a separate scenario run;
- compare scenario output with baseline;
- no mutation of the operational baseline.

The SCM scenario model also fits inside the shared platform simulation envelope.

## 6.7 Event-driven replanning

`apps/api/app/eventing.py` contains the SCM recomputation consumer.

Relevant inventory, forecast, requirement, PO, supplier commitment, receipt, BOM, policy and integration events can trigger a new SCM planning run. A trigger event ID is retained as the run trigger key, preventing duplicate runs for the same event.

After planning:

1. `scm.planning.completed` is written;
2. canonical material state is refreshed;
3. shared state snapshots are recorded;
4. shortage cases/recommendations are reconciled;
5. pending post-action outcomes can be verified against the new state.

## 6.8 Excel ingestion

Main file: `scm/imports.py`

Implemented flow:

```text
Workbook upload
   ↓
Preview and parse sheets
   ↓
Apply supplied/saved field mapping
   ↓
Validate values, identities, UOMs and dates
   ↓
Show row-level warnings/errors
   ↓
Commit accepted records
   ↓
Create source receipt/provenance/events
   ↓
Detect overlap with active manual observations
   ↓
Run a fresh plan
```

Capabilities include:

- preview before commit;
- field mapping;
- mapping-profile storage/versioning;
- row-level validation and rejection;
- material, supplier, customer and UOM lookup;
- import batch history;
- conflict detection;
- source freshness/data-health state;
- material CSV export.

This supports initial migration from customer spreadsheets without making Excel the permanent edit interface.

## 6.9 In-product manual data ingestion

Main files:

- `scm/manual_entries.py`
- `components/scm/SCMDataEntryCenter.tsx`
- migration `0064_scm_manual_data_entries.py`

Supported entry types:

```text
EXPECTED_DELIVERY_CREATED
SUPPLY_SCHEDULE_CHANGED
SUPPLY_QUANTITY_CHANGED
GOODS_RECEIPT_RECORDED
INVENTORY_CORRECTION_RECORDED
DEMAND_CREATED
DEMAND_CHANGED
```

Manual observations are governed and append-only rather than silently overwriting source records. Each entry retains:

- tenant, plant and material;
- canonical material mapping;
- target source entity where relevant;
- supplier;
- new and previous values;
- reason and evidence;
- effective/expiry timestamps;
- creator and membership;
- idempotency key;
- correlation ID;
- provenance;
- resulting planning-run ID and status.

Newer entries can supersede older active entries. Entries can be voided with audit/provenance retained. When a later import overlaps an active manual value, a data-quality conflict is raised for explicit resolution.

This enables a planner to add an emergency delivery, change a quantity/date, record a receipt or update demand inside GenuineGigs and immediately obtain a recalculated plan.

## 6.10 SCM action integration

The SCM recommendation-to-action path maps domain recommendations to shared actions such as:

```text
RESCHEDULE_PURCHASE_ORDER
EXPEDITE_PURCHASE_ORDER
TRANSFER_INVENTORY
CANCEL_PURCHASE_ORDER
CREATE_PURCHASE_ORDER
```

The actual external change is executed by the shared platform action/executor layer after policy and any required approval. SCM never treats recommendation acceptance as external execution.

---

# 7. SCM APIs

SCM routes live in `apps/api/app/scm/router.py` under `/scm`.

## Context and schema

```text
GET /scm/context
GET /scm/schema
```

## Imports and data quality

```text
POST /scm/imports/preview
GET  /scm/imports
GET  /scm/imports/{batch_id}
POST /scm/imports/{batch_id}/commit
GET  /scm/data-quality
GET  /scm/mapping-profiles
POST /scm/mapping-profiles
GET  /scm/exports/materials.csv
```

## Planning

```text
GET  /scm/planning-profile
POST /scm/demand-plans
POST /scm/demand-plans/{plan_id}/buckets
POST /scm/demand-plans/{plan_id}/publish
POST /scm/planning-runs
GET  /scm/planning-runs
GET  /scm/planning-runs/{run_id}
GET  /scm/planning-runs/{run_id}/input-snapshot
GET  /scm/planning-runs/{run_id}/changes
GET  /scm/policies
POST /scm/policies
```

## Product read models

```text
GET /scm/control-tower
GET /scm/materials
GET /scm/materials/{material_id}
GET /scm/supply-horizon
GET /scm/readiness
GET /scm/risks
GET /scm/exceptions
GET /scm/exceptions/{risk_id}
GET /scm/suppliers
```

## Recommendations, actions and cases

```text
GET  /scm/recommendations
POST /scm/recommendations/{id}/decision
POST /scm/recommendations/{id}/simulate
POST /scm/recommendations/{id}/create-action
GET  /scm/actions
POST /scm/risks/{risk_id}/status
```

## Scenarios, saved views and notes

```text
POST /scm/scenarios
POST /scm/scenarios/{id}/overrides
GET  /scm/scenarios
POST /scm/scenarios/{id}/run
POST /scm/scenarios/{id}/duplicate
GET  /scm/scenarios/{id}/comparison
GET  /scm/saved-views
POST /scm/saved-views
GET  /scm/notes/{entity_type}/{entity_id}
POST /scm/notes/{entity_type}/{entity_id}
POST /scm/overrides
```

## Manual entries and conflicts

```text
GET  /scm/data-entry/options
POST /scm/data-entries
GET  /scm/data-entries
GET  /scm/data-entries/{entry_id}
POST /scm/data-entries/{entry_id}/void
GET  /scm/data-conflicts
POST /scm/data-conflicts/{issue_id}/resolve
```

---

# 8. SCM frontend

SCM route files under `apps/web/app/scm/` are intentionally thin. Product code is in `apps/web/components/scm/`, and API types/calls are centralized in `apps/web/lib/scm-api.ts`.

| URL | Component | Purpose |
|---|---|---|
| `/scm` | `SCMControlTower.tsx` | Planning KPIs, major risks and current plan context |
| `/scm/materials` | `SCMMaterialExplorer.tsx` | Searchable/filterable material planning list |
| `/scm/materials/[materialId]` | `SCMMaterialDetail.tsx` | Material 360, projection, events, impact and recommendations |
| `/scm/horizon` | `SCMSupplyHorizon.tsx` | Multi-material time-phased risk/receipt horizon |
| `/scm/readiness` | `SCMRemainingWorkspace.tsx` | Product/work-order readiness |
| `/scm/exceptions` | `SCMExceptions.tsx` | Risk and exception lifecycle |
| `/scm/actions` | `SCMRemainingWorkspace.tsx` | Recommendations/actions |
| `/scm/scenarios` | `SCMRemainingWorkspace.tsx` | Scenario Lab |
| `/scm/suppliers` | `SCMRemainingWorkspace.tsx` | Supplier planning context |
| `/scm/data-entries` | `SCMDataEntryCenter.tsx` | In-product supply/inventory/demand changes |
| `/scm/imports` | `SCMImports.tsx` | Excel import, mappings and data health |

`SCMShell.tsx` adapts SCM local navigation and query refresh into the unified `ProductShell.tsx`.

## Supply Horizon

The Supply Horizon is backed by persisted planning output:

```text
SCMSupplyHorizon.tsx
        ↓
getSCMHorizon() in lib/scm-api.ts
        ↓
GET /scm/supply-horizon
        ↓
SCMPlanningRun + ProjectionPoint + PlanningEvent + Risk/Recommendation rows
```

The backend read model groups daily projection points into contiguous semantic segments:

- healthy;
- watch;
- critical;
- excess;
- unknown.

It also returns dated receipt, intervention and decision/deadline events. The frontend uses one proportional date coordinate system for segments, event markers, axis ticks and the today line. Rows use `@tanstack/react-virtual` so only the visible subset is rendered.

The Supply Horizon frontend must not invent transitions or calculate balances. Any incorrect color or transition should be debugged from the persisted planning run/read model first.

## Frontend styling layers

- `app/product-system.css`: shared product shell and unified design tokens;
- `app/scm-product.css`: current SCM product treatment;
- `app/scm-v1.css`: SCM structural/compatibility layout;
- `app/scm.css`: older SCM compatibility rules;
- `app/operations.css`: Operations domain styling;
- `app/globals.css`: older Procurement/shared styles.

New global shell decisions should go into `product-system.css`. New SCM-specific visual behavior should go into `scm-product.css`, while avoiding further global CSS growth where component/module scoping is possible.

---

# 9. Unified application experience added after the domain plans

The original modules had separate-feeling shells and legacy URLs. A later consolidation introduced:

- one `/login` experience;
- one session and selected workspace/plant context;
- `/home` as the post-login destination;
- a global module rail;
- consistent local module navigation;
- shared search (`Ctrl+K`);
- shared refresh state and visible animation;
- notifications and user menu;
- canonical `/procurement/*`, `/scm/*`, `/operations/*` URLs;
- redirects from old Procurement and `/v2/*` routes;
- unified module access derived by the backend;
- cross-module home summaries and attention queue.

Relevant backend endpoints:

```text
GET /api/v1/platform/app-context
GET /api/v1/platform/home
```

Relevant tests:

- `apps/api/tests/test_unified_product_context.py`
- `apps/web/e2e/unified-product-shell.spec.ts`

---

# 10. Database migrations introduced for the platform and SCM

| Migration | Purpose |
|---|---|
| `0057_scm_control_tower_scaffold.py` | Initial SCM tables and scaffold |
| `0058_core_platform_foundation.py` | Canonical platform foundation |
| `0059_core_platform_completion.py` | Additional platform phases and shared primitives |
| `0060_scm_readiness_core_hardening.py` | Canonical PO/work-order/simulation hardening and trace/action extensions |
| `0061_scm_phases_0_3.py` | SCM planning foundations, engine output, risk/readiness |
| `0062_scm_v1_remaining_phases.py` | SCM UI/read-model, recommendations, scenarios and remaining V1 phases |
| `0063_repair_tenant_business_number_indexes.py` | Tenant-scoped business-number index repair |
| `0064_scm_manual_data_entries.py` | Governed in-product SCM entries and conflict handling |

Applied migrations should never be edited to change production behavior. Add a new forward migration.

---

# 11. End-to-end architecture proof

The central acceptance test is:

```text
apps/api/tests/test_core_architecture_e2e.py
```

Its core deterministic scenario is:

1. A tenant/site has a supplier, material, product, BOM, line, equipment, work order, inventory and purchase order.
2. Baseline material runway is about nine days; PO arrival is day eight, so no shortage exists.
3. An external source changes PO arrival from day eight to day twelve through the connector/ingestion boundary.
4. Existing source identities resolve to the canonical supplier, material, PO and site without duplication.
5. Provenance and a transactional `purchase_order.rescheduled` event are recorded.
6. Duplicate processing remains idempotent.
7. SCM replans from shared/canonical state and detects the approximate three-day shortage exposure.
8. Graph traversal identifies affected product, work order and line.
9. A shared OperationalCase and deterministic intervention are created.
10. The intervention becomes an ActionIntent rather than directly changing the PO.
11. Policy requires manager approval.
12. A manager approves through the real approval service.
13. A fake connector safely simulates the external PO reschedule.
14. An outcome event causes another plan/state recomputation.
15. Recovery is verified from the safe post-action state.
16. The correlation trace returns the complete chronological chain.

Failure tests additionally prove:

- duplicate external update does not duplicate state/case/action;
- outbox publisher interruption does not lose the event;
- consumer failure is retryable and idempotent;
- invalid canonical mapping is surfaced with provenance retained;
- policy rejection blocks execution;
- approval rejection blocks execution;
- connector execution failure remains visible;
- successful execution with unsafe state is **not** marked recovered;
- an external identity cannot be silently remapped.

The readiness report records **7 architecture tests passed** and **19 selected regression tests passed** at the hardening checkpoint.

---

# 12. Test inventory and current verification status

Important backend suites:

| Area | Test file |
|---|---|
| Core connector-to-verification proof | `tests/test_core_architecture_e2e.py` |
| Platform foundation | `tests/test_platform_foundation.py` |
| Platform phases | `tests/test_core_platform_phases.py` |
| SCM planning math | `tests/test_scm_engine.py` |
| SCM APIs/read models/manual entries | `tests/test_scm_api.py` |
| Excel ingestion | `tests/test_scm_imports.py` |
| Operations | `tests/test_operational_v2.py`, `test_operational_v2_api.py` |
| Recovery | `tests/test_recovery_v21.py` |
| Unified application context | `tests/test_unified_product_context.py` |

Frontend suites live in `apps/web/e2e/`, including the unified product shell, Operations workflows, role workflows and simulation flows.

Recorded verification checkpoints:

- central architecture suite: 7 passed;
- selected core/SCM/Operations regression suite: 19 passed;
- SCM V1 selected acceptance: 10 passed;
- fresh migration through `0062`: passed at the SCM readiness checkpoint;
- subsequent migrations `0063` and `0064` exist for index repair/manual entries;
- latest frontend TypeScript check: passed;
- latest Next.js production build: passed;
- latest Python source compilation: passed;
- latest local host could not execute pytest because its host Python environment lacked FastAPI/pytest; Docker remains the intended full runtime.

Known frontend performance-budget result at the latest check:

- total JavaScript was approximately 3.13 MB against a 3.0 MB budget;
- global CSS was approximately 390 KB against a 300 KB budget;
- largest individual JavaScript asset remained within its budget.

Do not weaken the budget simply to make the check green. The correct follow-up is route-level CSS ownership and legacy CSS consolidation.

---

# 13. What is complete versus partial

## Implemented and structurally proven

- shared tenant/plant-scoped platform;
- canonical identity and external identity mapping;
- canonical Material/Product/BOM/Inventory/PO/work-order references;
- provenance and data-quality records;
- transactional outbox and consumer idempotency;
- required current-module event families;
- PostgreSQL-backed relationship graph and traversal;
- current/historical factory-state service;
- shared OperationalCase;
- ActionIntent/policy/approval/execution/outcome/verification;
- correlation trace API;
- minimal shared simulation contract;
- deterministic SCM planning engine;
- immutable planning snapshots;
- risk, shortage, excess and readiness projections;
- deterministic recommendations and simulations;
- Scenario Lab backend/UI;
- Excel preview/mapping/validation/commit;
- in-product manual SCM changes with replan;
- conflict detection between source imports and manual values;
- SCM Control Tower, Material Explorer, Material 360, Horizon, Readiness, Exceptions, Actions, Scenarios, Suppliers, Entries and Imports surfaces;
- unified login/home/product shell and canonical routes.

## Partially migrated by design

- SCM material/BOM/import tables still exist as domain compatibility records;
- Procurement PO behavior remains in Procurement models while canonical PO records expose shared identity/state;
- Operations work-order/product tables remain domain behavior owners;
- inventory remains a service/read-model composition over optimized projections;
- some legacy event names and URLs remain supported;
- styling still includes older CSS layers loaded alongside the newer product system.

These are not necessarily blockers. New work must avoid increasing these dependencies.

## Not production-proven yet

- customer-specific mapping against the real design-partner workbook;
- planning/UI performance with the customer's actual 3,800+ materials;
- recommendation cost weights calibrated to commercial terms;
- prolonged observation of supplier reliability and recommendation outcomes;
- production connector validation against a real SAP/ERP tenant;
- PostgreSQL concurrent outbox claiming and graph-query load at target scale;
- complete browser regression in every supported viewport after each UI change.

## Explicitly deferred

- Neo4j/dedicated graph database;
- 3D factory visualization;
- full digital twin;
- whole-factory discrete-event simulator;
- data lakehouse/Iceberg/Spark/dbt/ClickHouse migration;
- generic feature store/model registry/drift platform;
- production OPC-UA/MQTT edge runtime;
- Kubernetes/service mesh/microservice decomposition;
- autonomous machine control or L4/L5 factory autonomy.

---

# 14. Remaining work, prioritized honestly

## Blocks current code from existing

None structurally identified. The product can run, seed demo workspaces and exercise the implemented SCM workflows.

## Blocks a real customer pilot from being considered validated

1. Import and reconcile the customer's real workbook.
2. Confirm source-of-truth ownership for each field and sheet.
3. Run parallel planning against the customer's existing Excel process.
4. Reconcile inventory, supply, demand, BOM and projection differences.
5. Confirm planner permissions, approval thresholds and external-action rules.
6. Load-test the actual material/BOM/PO volume.
7. Tune recommendation feasibility and commercial weights.
8. Validate the visual Supply Horizon with planners using real exceptions.

## Should be fixed during SCM development/pilot

- migrate every newly touched SCM query toward canonical IDs or an explicit adapter;
- attach graph/state/event synchronization to each new write path;
- add PostgreSQL concurrency tests for outbox claiming and simultaneous planning runs;
- tune indexes using real query telemetry;
- surface saved Excel mappings directly in the customer import flow;
- expand interplant-transfer logic to account for projected origin demand and safety stock;
- remove remaining direct legacy links as their owning components are changed;
- split route-specific styles and reduce global CSS/JS bundle weight;
- replace hard-coded/demo-only UI badges or status values where still present;
- run full Playwright regression against the Docker stack.

## Safe to defer

All items in the explicitly deferred list above, plus advanced ML-based forecasting until deterministic planning has real design-partner baselines and outcome data.

---

# 15. Non-negotiable engineering rules for future work

An AI assistant or engineer continuing this product should follow these rules:

1. **Do not create a second shared identity.** Use canonical IDs or `ExternalEntityReference`.
2. **Do not let SCM mutate external Procurement/ERP records directly.** Create a recommendation and ActionIntent.
3. **Do not bypass policy or approval for consequential actions.**
4. **Do not infer recovery from execution success.** Verify from post-action state.
5. **Do not calculate authoritative SCM balances in React.** Use persisted planning read models.
6. **Every externally sourced mutation requires provenance.**
7. **Every canonical event consumer must be idempotent.**
8. **Carry tenant and plant scope through every query and write.**
9. **Carry correlation IDs through ingestion, events, planning, cases and actions.**
10. **Preserve legacy compatibility incrementally; avoid risky rewrites.**
11. **Keep platform primitives generic and domain algorithms inside their module.**
12. **Add core infrastructure only for a real Procurement, SCM or Operations requirement.**
13. **Use a new forward migration; never rewrite an applied migration.**
14. **Treat AI explanations as assistance, not source-of-truth calculations.**
15. **Do not add another login, global sidebar or independent module shell.** Use `ProductShell`.

---

# 16. Recommended reading order for a new ChatGPT session

To understand the implementation efficiently:

1. This file.
2. `docs/CODEBASE_MAP.md`.
3. `CORE_ARCHITECTURE_READINESS.md`.
4. `SCM_V1_READINESS.md`.
5. `apps/api/tests/test_core_architecture_e2e.py`.
6. `apps/api/app/platform/models.py`.
7. `apps/api/app/platform/purchase_orders.py`.
8. `apps/api/app/eventing.py`.
9. `apps/api/app/platform/actions.py`.
10. `apps/api/app/platform/state.py` and `relationships.py`.
11. `apps/api/app/scm/engine.py`.
12. `apps/api/app/scm/planning.py` and `service.py`.
13. `apps/api/app/scm/risks.py` and `recommendations.py`.
14. `apps/api/app/scm/router.py`.
15. `apps/web/lib/scm-api.ts`.
16. `apps/web/components/scm/SCMSupplyHorizon.tsx`.
17. `apps/web/components/platform/ProductShell.tsx`.

---

# 17. Prompt context for another ChatGPT

The following summary can be pasted at the top of a future request:

> GenuineGigs is a case-driven manufacturing disruption-prevention and recovery product with SCM, Procurement and Operations domains on a shared FastAPI/PostgreSQL platform and Next.js product shell. The platform owns canonical identity, provenance/freshness, graph/context, the shared Operational Case envelope, exposure, decisions, recovery verification, value attribution, work, commitments, ActionIntent governance, events, trace and simulation contracts. Domains retain their authoritative detections and workflows, then link them into one shared case. SCM owns deterministic planning, BOM explosion, pegging, material risk and recovery strategies; Procurement owns commercial and supplier execution; Operations owns production state, deviations and operational strategies. Gigi is a proactive, case-aware companion built over authorized deterministic tools: it may investigate, explain, plan, create work/commitments and propose ActionIntents, but it may not invent operational truth, approve itself or directly execute consequential changes. The browser never calculates authoritative operational state. Existing domain tables remain compatibility/behavior records mapped to canonical IDs; do not create duplicate identities or perform a flag-day rewrite. Use the unified `ProductShell` and command-center, case, work, decision and domain routes. Migrations currently run through `0074_domain_case_links`. Read this document, especially the authoritative supplement beginning at section 19, plus `docs/CODEBASE_MAP.md` before changing architecture.

---

# 18. Final assessment

## Is the central architecture implemented as planned?

**Yes, for the deliberately bounded shared-core milestone.** The repository contains and tests the essential canonical identity, provenance, event, graph, state, case, action, simulation and trace capabilities required for Procurement, SCM and Operations to cooperate without creating a new SCM silo.

This does not mean the ultimate Manufacturing OS, digital twin, lakehouse or autonomous factory has been built. Those were explicitly deferred.

## Is SCM implemented as planned?

**Yes, structurally for SCM V1 and the initial V1.5 scope described in the readiness report.** It includes persisted deterministic planning, risk/readiness, explainable recommendations, scenarios, Excel migration, in-product data changes, governed external actions and the principal planner screens.

The remaining risk is now primarily **design-partner validation, customer data reconciliation, scale/performance tuning and workflow refinement**, not the absence of a core architecture or SCM foundation.

---

# 19. September 2026 authoritative current-state supplement

Sections 1–18 preserve the implementation history of the shared platform and
SCM. This supplement reconciles that history with the code now present through
migration `0074`, the shared Operational Case vertical slice, Operations,
Procurement, and the current Gigi intelligence and companion experience.

When any older statement conflicts with this supplement or the running code,
the order of authority is:

1. database migrations and executable invariants;
2. service and router code;
3. automated tests;
4. this document;
5. historical plans.

The product is best understood as a **case-driven manufacturing recovery
system**, not as a collection of dashboards and not as a generic AI chat
application.

```text
Operational change
    → domain detection
    → shared Operational Case
    → production/customer impact
    → feasible recovery options
    → accountable decision
    → governed actions and work
    → fresh operational observations
    → stable verified recovery
    → conservative value attribution
    → recurrence and preventive learning
```

The commercial proposition is:

> Prevent manufacturing disruptions before they affect production or customer
> delivery, and coordinate the best feasible recovery when plans change.

Terms such as manufacturing OS, knowledge graph, digital twin and agentic AI
describe internal capabilities. They are not the primary customer promise.

---

# 20. Complete runtime topology

## 20.1 Deployable processes

The default local and pilot topology is a modular monolith with supporting
infrastructure:

| Process | Technology | Responsibility |
| --- | --- | --- |
| `web` | Next.js 16 / React / TypeScript | Unified product shell and all operator workspaces |
| `api` | FastAPI / SQLAlchemy / Pydantic | Authenticated APIs, domain services and synchronous orchestration |
| `worker` | Celery | Asynchronous events, planning, integrations, AI work and monitoring |
| `beat` | Celery Beat | Durable periodic scheduling |
| `postgres` | PostgreSQL 16 + pgvector | Authoritative transactional and analytical application state |
| `redis` | Redis 7 | Celery broker/backend and transient coordination |
| `minio` | MinIO | Private documents, quarantine and evidence objects |
| `mailpit` | Mailpit | Local SMTP capture |
| `opa` | Open Policy Agent | Policy evaluation/shadow-policy support |

Optional `simulation` and `developer-lab` profiles add factory simulation,
MQTT, an OT simulator, an edge bridge, Jaeger, and the developer observatory.
These are not production dependencies of deterministic business flows.

## 20.2 Request path

```text
Browser
  → Next.js route and ProductShell
  → typed API client with session cookie, CSRF and idempotency key
  → FastAPI middleware
  → authenticated tenant/plant scope
  → domain or platform service
  → PostgreSQL transaction
  → transactional outbox
  → Celery consumer
  → projected state / notification / case / trace update
```

The API application registers health, identity, role-agent, legacy companion,
Operations, recovery, developer tooling, SCM, platform, Gigi, and case routers.
Compatibility APIs coexist with `/api/v1/platform`, `/api/v1/gigi`, `/api/v1/cases`
and `/api/v2`; they must not become new sources of canonical identity.

## 20.3 Storage rules

- PostgreSQL is authoritative for business state.
- Redis is not an authoritative record store.
- Documents and evidence objects are private by default.
- Object metadata and authorization live in PostgreSQL.
- External side effects require persisted intent, policy result, approval and
  execution receipt.
- Demo and synthetic observations must be labelled and must not influence
  production learning.

---

# 21. Canonical ownership and domain boundaries

## 21.1 Platform ownership

The shared platform owns:

- tenant, account, workspace membership and plant scope;
- canonical organizations, sites, materials, products, BOM identities,
  suppliers, work centers, equipment, customer orders and work-order mappings;
- external IDs, source systems, ingestion receipts and mapping versions;
- provenance, freshness and data-quality issues;
- effective-dated relationships and impact traversal;
- state projections and decision snapshots;
- the shared Operational Case envelope;
- business exposure, decisions, action plans, recovery targets and attribution;
- work, commitments, escalation and audit;
- ActionIntent, policy evaluation, approvals, execution, outcomes and trace;
- Gigi authorization, context, evidence, runs, tools, insights and evaluations.

## 21.2 Domain ownership

Procurement owns commercial sourcing and supplier transaction behavior:
requirements, RFQs, quotes, comparison, negotiation, purchase-order drafts,
supplier acknowledgement, inbound/gate/store/inspection, invoice exceptions and
commercial follow-up.

SCM owns planning truth and supply strategies: time-phased supply and demand,
BOM explosion, pegging, coverage, shortage/excess risk, material readiness,
planning scenarios, pull-in/push-out/cancel/transfer/resequence evaluation and
supplier planning reliability.

Operations owns observed production behavior: shifts, production state,
deviations, downtime, machine signals, material readiness at execution,
quality holds/CAPA, maintenance work, recovery execution and operational
effectiveness.

Domain detections remain domain-owned. They link to one shared Operational Case
instead of becoming competing user-facing case systems.

## 21.3 Progressive migration

Legacy `Item`, SCM material, Operations product/BOM/inventory, Procurement case,
and Operations recovery tables remain where they carry domain behavior. They
are connected through canonical IDs and explicit adapters. No destructive
flag-day migration is authorized.

---

# 22. Shared Operational Case vNext

The shared case is the user-facing envelope for understanding, deciding,
coordinating and verifying recovery. The core records live in
`app/platform/models.py` and `app/platform/case_models.py`.

## 22.1 Case envelope

`OperationalCase` carries title, summary, type, severity, status, priority,
confidence, detection time, first possible detection time, decision deadline,
expected impact time, responsible team, recovery state, current strategy,
aggregation key, correlation ID and last evaluation time.

`CaseEntityLink` connects a case to primary, causal and impacted entities such
as materials, suppliers, purchase orders, production orders, work centers,
products and customer commitments.

`CaseEvidence` preserves every source event with observed/recorded time,
freshness, confidence and payload. Replay is idempotent by case and source
event; evidence is never silently discarded.

`CaseCause` separates asserted or confirmed causes from raw evidence. Cause
confidence is explicit and does not turn correlation into proof.

## 22.2 Aggregation behavior

Active cases aggregate by tenant, plant and a domain-computed aggregation key.
The key includes the materially relevant combination of material, risk window,
affected commitment, causal supplier/PO and plant. Replayed source events update
the same case. Materially unrelated risks remain separate. Closed cases do not
absorb unrelated future disruptions.

Procurement `Case` and Operations `RecoveryCase` carry `operational_case_id` as
of migration `0074`. Reconciliation creates or updates the shared envelope while
preserving the domain record and its native lifecycle evidence.

## 22.3 Exposure

`BusinessExposure` stores baseline, projected value, delta, unit/currency,
time horizon, methodology, confidence, input snapshot and calculation version.
Supported initial concepts include production units/hours at risk, customer
units at risk, revenue where authorized source data exists, premium freight,
inventory cash and downtime. Unknown values remain null and must not be replaced
with invented zeroes.

---

# 23. Feasibility, decisions and governed execution

## 23.1 Constraints and feasibility

`NetworkConstraint` represents the effective-dated facts needed by the first
recovery slice: transfer lanes, lead time/cost, qualification, sourcing rules,
MOQ/lot size, reschedule/cancellation windows, routing and work-center
capability. Every constraint has source, provenance, validity and freshness.

`FeasibilityEvaluation` and `ConstraintResult` use four states:

```text
SATISFIED | VIOLATED | UNKNOWN | NOT_APPLICABLE
```

A blocking violation makes an alternative unavailable. A blocking unknown
requires explicit confirmation. Stale origin inventory therefore cannot support
a high-confidence plant-transfer recommendation.

## 23.2 Decisions

`DecisionRecord` binds alternatives to a baseline snapshot/planning run,
deadline, deterministic recommendation, selected alternative, actor, approver,
reason, override reason, policy version and AI-assistance flag.

`DecisionAlternative` stores strategy parameters, expected impact, cost, time
to effect, probability, side effects, feasibility, score dimensions, ranking,
evidence and simulation reference. Alternatives become immutable when the
decision is finalized.

Selecting a non-recommended option requires an override reason. Selection is
rejected when the option belongs to another decision, has blocking violations,
or contains critical unknowns without confirmation.

## 23.3 Action plan and ActionIntent

Decision selection creates an `ActionPlan` and ordered `ActionPlanStep` records.
Each consequential step proposes an `ActionIntent`; domains and Gigi do not
write directly to ERP, suppliers, inventory or production schedules.

```text
proposal
 → policy evaluation
 → required human approval
 → connector/manual execution
 → immutable receipt
 → outcome reconciliation
 → fresh operational observation
```

Execution success moves a case into monitoring. It never proves recovery.
External execution defaults to simulation/manual confirmation. Live execution
requires both deployment controls and per-action authorization.

---

# 24. Recovery verification and value attribution

`RecoveryTarget` defines a metric, operator, threshold, required duration,
required observation count and freshness rule. `RecoveryObservation` records
fresh operational evidence. `RecoveryVerification` distinguishes pending,
monitoring, recovered, partially recovered, not recovered and indeterminate
outcomes.

For the MAT-182 slice, coverage must remain at or above threshold across two
fresh successful planning observations while the production/customer
requirement remains protected. A completed task, approved action or successful
connector call is insufficient.

`ValueAttribution` records baseline, counterfactual, actual, attributed value,
methodology, assumptions and confidence:

```text
DIRECT
STRONGLY_ATTRIBUTABLE
PARTIALLY_ATTRIBUTABLE
CORRELATIONAL
UNKNOWN
```

The product may report verified protected units or other value only when input
evidence, methodology and confidence are present. Financial value remains
restricted or null when the source or role does not support it.

---

# 25. SCM end-to-end operation

## 25.1 Deterministic flow

```text
Excel / API / manual / ERP-compatible input
 → source receipt and canonical mapping
 → inventory, supply, demand, BOM and policy facts
 → immutable planning input snapshot
 → time-phased planning run
 → projections, pegging and readiness
 → material risk
 → shared-case aggregation and impact
 → feasible recovery alternatives
 → DecisionRecord and ranking
 → ActionPlan / ActionIntent
 → execution evidence
 → replanning
 → stability verification
 → value attribution
```

Planning is deterministic. The LLM does not calculate projections, shortage
quantity, feasibility, score or rank.

## 25.2 Engine capabilities

The engine handles dated supply and demand, safety stock, uneven demand,
effective BOM revisions, multi-level explosion with cycle/depth protection,
pegging lineage, shortage/excess windows, runway, pull-in, push-out,
cancellation/reduction and action timing. Planning outputs are persisted read
models; the browser does not reproduce authoritative calculations.

## 25.3 Scenario isolation

Scenario definitions retain baseline run/snapshot, assumptions, overrides,
engine/policy version, generated time, output projection and comparison deltas.
Scenario execution cannot mutate operational facts or send external actions.
The UI compares baseline and scenario instead of presenting a context-free
single result.

## 25.4 MAT-182 commercial slice

The canonical fixture is:

```text
Plant A / Plant B / Supplier X
MAT-182 → Honda ECU-A → Honda order H421 → WO-981 → Line 3
PO-812 ETA +4 days and customer demand +11%
```

It creates one idempotent critical case, an approximately four-day gap, 440
projected units at risk, a decision deadline and three ranked alternatives:

1. interplant transfer;
2. supplier pull-in;
3. production resequence.

The transfer evaluator accounts for Plant B future demand and rejects a transfer
that harms Plant B. Stale inventory changes availability to confirmation
required. Recovery needs two fresh coverage observations.

## 25.5 SCM UI

Canonical routes are `/scm`, `/scm/horizon`, `/scm/materials`,
`/scm/materials/{id}`, `/scm/exceptions`, `/scm/readiness`, `/scm/scenarios`,
`/scm/suppliers`, `/scm/imports`, `/scm/data-entries` and `/scm/actions`.

The command center leads with material risks, exposure, action demand and
readiness. Supply Horizon presents persisted timelines and dated intervention
markers. Material detail exposes projection, source events, impact/pegging,
freshness and recommendation candidates. Imports support preview/commit and
mapping; manual entries trigger governed reconciliation and replanning.

---

# 26. Procurement and Operations integration

## 26.1 Procurement

The Procurement product covers requirement intake, RFQ creation, quotations,
document extraction/review, comparison, negotiation, PO drafting and approval,
supplier acknowledgement, inbound delivery, gate/store/quality, invoice and
exception closure. Supplier and PO events can cause SCM replanning and shared
case updates. Supplier follow-up created by a recovery plan remains Procurement
work even though its outcome is visible on the shared case.

## 26.2 Operations

Operations exposes role-aware command centers for production, materials,
quality, maintenance, improvement, knowledge, briefings, admin, integrations,
setup and corporate views. It detects behind-plan output, downtime, machine
signals, material readiness and quality deviations. Recovery strategies,
actions and verification remain evidence based.

Recurring failures and improvement opportunities use verified historical
outcomes, sample sizes and context. Repetition is not presented as physical
root-cause proof.

## 26.3 Cross-domain examples

```text
Supplier delay
 → SCM material risk/shared case
 → Procurement confirmation or expedite work
 → Operations schedule/customer impact
 → fresh plan and production observations
 → shared recovery verification
```

```text
Production underperformance
 → Operations deviation/recovery record
 → shared Operational Case
 → material/customer implications
 → coordinated work and verification
```

---

# 27. Gigi intelligence architecture

Gigi is a proactive manufacturing companion, not a chatbot with factory-themed
prompts. Conversation is a secondary follow-up surface.

## 27.1 Trust boundary

Gigi can explain, investigate, call authorized deterministic read tools,
compare calculated alternatives, propose work, create durable commitments,
propose ActionIntent records, monitor deadlines and explain verification.

Gigi cannot calculate operational truth, invent exposure, suppress freshness
warnings, approve its own proposal, receive an external-executor tool, infer
recovery from task completion or write unverified conversation into factory
learning.

## 27.2 Runtime pipeline

```text
authenticated user + membership + current plant
 → validated page/entity context
 → bounded FactoryContextPacket
 → role profile and authorities
 → authorized typed read tools
 → evidence references and freshness
 → model gateway with strict structured schema
 → validated GigiResponse
 → persisted run, messages, tool calls and events
```

`ContextEngine` resolves tenant and plant server-side and rejects forged entity
scope. Factory context contains plant metadata, active case attention, the two
most recent completed SCM planning runs, entity state when selected and semantic
guardrails. It is deterministically compressed when it exceeds the configured
budget.

The tool registry exposes factory entity state, relationships and downstream
impact. Registration of an `EXTERNAL_ACTION` tool is rejected. Tool calls retain
arguments, authorization decision, version, result digest, evidence references,
latency and correlation ID.

## 27.3 Model gateway

The new intelligence layer uses one provider gateway with FAST, REASONING,
EXTRACTION and EMBEDDING classes. The configured Groq adapter maps those classes
to deployment model names and requires JSON matching the Pydantic response
schema. Timeout, malformed output or unavailable provider falls back to a
deterministic grounded answer.

The model receives factory context and tool observations. It must not claim that
only conversation/schema exists when authorized operational facts are present.
For “what changed since the last plan,” the runtime compares the two supplied
completed planning runs or explicitly says that a second run is unavailable.

Provider secrets are runtime environment variables. `GROQ_API_KEY`,
`GEMINI_API_KEY` and similar values must never be exposed through `NEXT_PUBLIC_*`.

## 27.4 Durable AI records

The intelligence plane stores role profiles, threads, messages, runs, run
events, typed tool calls, feedback, investigation state, briefings, verified
memories/experiences, insights and commitments. Unverified conversation cannot
become factory-pattern memory.

## 27.5 Proactive insight runtime

Case insights are deterministic projections with a deduplication signature,
delivery state, next evaluation time, acknowledgement, snooze, dismissal and
escalation state.

- critical case, near decision deadline or failed recovery: popup;
- high/medium: toast or attention feed;
- low: feed/briefing;
- equivalent repeated trigger: update existing insight;
- snoozed/dismissed/acknowledged state remains durable.

Celery evaluates case insights every 60 seconds, durable commitments every 60
seconds, and case stability every 300 seconds.

## 27.6 Companion UX

The global ProductShell renders one Gigi companion across every module. The
ambient control communicates stable, watching or urgent state. The companion
opens into five structured views:

1. **Attention** — interventions, evidence, next evaluation, acknowledge/snooze;
2. **Brief** — role-aware cases, decisions, approvals and outcomes;
3. **Plan** — case problem, deterministic recommendation, alternatives,
   feasibility, time, probability and guardrails;
4. **Commitments** — persisted promises, owner/dependency, due time and evidence;
5. **Ask** — conversational follow-up.

Case workspaces include a contextual “Gigi is working this case” card that opens
the structured plan. `/gigi` is a companion command workspace, not an empty chat
launcher. Enter sends a message; Shift+Enter inserts a newline. Message POSTs
reuse an idempotency key on network retry so a saved response is not duplicated.

The obsolete separate Procurement companion and Operations Plant Guardian panel
are not mounted in the unified shell.

---

# 28. Product shell and route architecture

The global navigation is Command Center, Cases, My Work, Decisions, Procurement,
SCM, Operations and Platform. Role adaptation changes priority and available
depth, not underlying facts.

Top-level module switches use full-document navigation deliberately. This avoids
stale React Server Component/chunk skew when a local or pilot deployment replaces
the Next.js container while a browser still holds the previous bundle. Internal
workspace links use Next navigation where appropriate.

The shell provides workspace/plant identity, module navigation, search, refresh,
notifications, Gigi state, profile and logout. `/cases` is the canonical shared
case route; it must never redirect to the legacy Procurement exception route.

Route and global error boundaries present a recovery action and perform one safe
reload for transient chunk/import/network failures. GET requests receive one
short network retry. Mutations rely on idempotency rather than unsafe blind
repetition.

---

# 29. Public API map

## 29.1 Shared cases and decisions

```text
GET  /api/v1/cases
GET  /api/v1/cases/{id}
GET  /api/v1/cases/{id}/evidence
GET  /api/v1/cases/{id}/timeline
GET  /api/v1/cases/{id}/impact
GET  /api/v1/cases/{id}/strategies
POST /api/v1/cases/{id}/scenarios
POST /api/v1/cases/{id}/decisions
GET  /api/v1/decisions/{id}
GET  /api/v1/recoveries/{case_id}
POST /api/v1/recoveries/{case_id}/verify
GET  /api/v1/cases/{id}/value
```

## 29.2 Factory context/platform

```text
GET  /api/v1/platform/app-context
GET  /api/v1/platform/home
GET  /api/v1/platform/context
POST /api/v1/platform/operational-context
GET  /api/v1/platform/state/{type}/{id}
GET  /api/v1/platform/state/{type}/{id}/history
GET  /api/v1/platform/relationships/{type}/{id}
GET  /api/v1/platform/impact/{type}/{id}
GET  /api/v1/platform/traces/{correlation_id}
GET  /api/v1/platform/data-quality
GET  /api/v1/platform/provenance
GET/POST /api/v1/platform/actions
POST /api/v1/platform/actions/{id}/decision
POST /api/v1/platform/actions/{id}/execute
```

## 29.3 Gigi

```text
GET  /api/v1/gigi/insights
POST /api/v1/gigi/insights/{id}/{acknowledge|snooze|dismiss}
GET  /api/v1/gigi/brief
GET/POST /api/v1/gigi/commitments
POST /api/v1/gigi/cases/{id}/investigate
POST /api/v1/gigi/cases/{id}/plan
GET/POST /api/v1/gigi/conversations
GET/POST /api/v1/gigi/conversations/{id}/messages
GET  /api/v1/gigi/runs/{id}
GET  /api/v1/gigi/runs/{id}/events
GET  /api/v1/gigi/runs/{id}/stream
POST /api/v1/gigi/runs/{id}/actions
POST /api/v1/gigi/runs/{id}/feedback
GET  /api/v1/gigi/investigations
GET/POST /api/v1/gigi/briefings
GET  /api/v1/gigi/experiences
```

SCM continues to expose `/scm/*`; Operations uses `/api/v2/*`; existing
Procurement routes remain compatibility contracts. Consult generated OpenAPI for
the exhaustive field-level contract rather than duplicating every legacy route
here.

---

# 30. Events, consumers and background work

Canonical events are factual, versioned envelopes registered in
`platform/event_registry.py`. Major families include master mapping, inventory,
forecast, supplier commitment, purchasing, receipts, SCM planning and risk,
work-order/production/downtime/quality, operational deviation/recovery,
ActionIntent lifecycle, shared case/decision/action-plan/recovery/value and
commitment due/overdue.

The transactional outbox is written in the same transaction as business state.
Consumers use durable receipts for idempotency, carry tenant/plant and
correlation scope, and support retries/dead-letter behavior. Replaying an event
must not duplicate cases, actions, work or evidence.

Scheduled work currently includes outbox draining, queued-job recovery,
retention, active-cycle evaluation, action SLA checks, line reconciliation,
material-readiness recomputation, factory-simulator synchronization, operational
state/recovery reconciliation, forecast evaluation, queued SCM planning, Gigi
insight evaluation, commitment evaluation and case stability verification.

Workers are routed to documents, integrations, email, sync, events,
specialists/agents and SCM queues. Tasks must remain tenant scoped, idempotent,
observable, retryable and safe after restart.

---

# 31. Security, authorization and safety invariants

- The server derives tenant, membership and plant scope from the authenticated
  session; client-supplied scope is not trusted.
- Cross-tenant and unauthorized-plant entities return unavailable/not found.
- State-changing browser requests require CSRF and an idempotency key.
- Role/permission checks protect domain and financial visibility.
- Action approval cannot be issued by the proposing AI.
- Gigi cannot register or call an external-execution tool.
- Documents retain ACL/classification and quarantine behavior.
- Connector scopes and live-write switches constrain external systems.
- Security headers, request logging and rate limiting run as middleware.
- API keys are backend runtime secrets, never browser build variables.
- Recovery and value claims require evidence rather than workflow status.

Default local safety controls keep ERP and SMTP behavior simulated. Production
enablement requires tenant-specific UAT, policy testing, rollback/kill-switch
validation and source reconciliation.

---

# 32. Database migration ledger after the original handoff

| Revision | Purpose |
| --- | --- |
| `0065_gigi_intelligence_plane` | Gigi profiles, conversations, runs, tools, evidence and intelligence state |
| `0066_operational_case_vnext` | Extended case envelope, entity links, evidence and causes |
| `0067_case_exposure` | Quantified business exposure with methodology |
| `0068_network_constraints` | Customer commitments and effective-dated feasibility constraints |
| `0069_case_decisions` | Feasibility, constraint results, decision records and alternatives |
| `0070_recovery_verification` | Targets, observations and stability verification |
| `0071_value_attribution` | Conservative outcome/value attribution |
| `0072_gigi_companion_state` | Insights, delivery state, preferences/subscriptions and commitments |
| `0073_case_execution_core` | Shared action-plan execution linkage |
| `0074_domain_case_links` | Procurement/Operations records linked to shared cases |

All are additive. Existing Procurement, SCM, Operations and platform data is not
destructively rewritten.

---

# 33. Local development, build and deployment

## 33.1 Standard local stack

```bash
cp .env.example .env
docker compose up --build
```

The application is at `http://localhost:3000`; API docs are at
`http://localhost:8000/docs`. Seeded Apex credentials are
`admin@genuinegigs.local` / `Password@123`. Groq is optional; deterministic
fallback keeps governed flows usable without a provider.

Use `docker compose up` after the initial build. Changing runtime secrets only
requires container recreation, not image rebuild. `NEXT_PUBLIC_*` values are
browser build inputs and require a web rebuild.

## 33.2 Fast development loop

Run PostgreSQL, Redis, MinIO, Mailpit and OPA in Docker and run Next/Uvicorn on
the host for hot reload. Production images should be built once in CI, tagged by
commit SHA, pushed to a registry and pulled by deployment. Production servers
must not run `pip install` during rollout.

The API image should be shared by API, migrate, seed, worker and beat processes.
Dependency manifests/lock files must be copied and installed before application
source so source edits do not invalidate expensive dependency layers.

## 33.3 Optional profiles

```bash
docker compose --profile simulation up --build
docker compose --profile developer-lab up --build
```

Simulation provides richer Northstar/demo data and factory signals.
Developer-lab adds OT/MQTT/trace observability. It does not change the production
authority model.

---

# 34. Verification and test strategy

Backend suites cover deterministic projection/BOM/pegging, cases and replay,
decisions/constraints, ActionIntent invariants, recovery/value, imports/manual
entries, connector conformance, tenant isolation, Gigi authorization and
grounding, Operations recovery, simulation and performance budgets.

Frontend checks include TypeScript, production build and Playwright flows for
unified navigation, role workflows, simulation, product shell and screenshots.
The current Next production build generates 93 application routes.

Critical invariants are:

- repeated source events update one active case;
- alternative valid supply suppresses false risk;
- unsafe transfer is blocked;
- stale inputs require confirmation;
- override requires a reason;
- decisions and finalized alternatives are immutable;
- execution success does not imply recovery;
- recovery requires configured fresh observations;
- unknown and partial outcomes remain representable;
- AI/provider outage leaves deterministic workflows usable;
- cross-tenant and forged page context are rejected;
- unverified chat never becomes factory learning.

Performance validation must measure planning runtime, aggregation and graph
latency, scenario comparison, thousands-of-material horizon rendering,
concurrent Gigi investigations, job backlog and outbox replay.

---

# 35. Honest completion status and known limits

Structurally implemented:

- shared canonical platform and cross-domain mappings;
- deterministic SCM planning and recovery core;
- shared cases, exposure, decisions, action plans, verification and value;
- Procurement and Operations domain linkage;
- unified operator shell and case workspace;
- proactive Gigi insights, briefings, structured planning, commitments and chat;
- simulation/developer-lab topology;
- security and evidence boundaries needed for an advisory pilot.

Not yet proven merely by repository implementation:

- production performance at every target customer scale;
- SAP/customer-specific connector semantics without real access;
- completeness and quality of a design partner's mappings and master data;
- statistically strong strategy-effectiveness learning from real outcomes;
- customer willingness to pay or quantified savings;
- safe live write-back before tenant-specific UAT and rollback validation;
- operational reliability under a completed production observability setup.

The first release should be called commercially complete only when a real or
accepted pilot dataset runs the supplier-delay/material-shortage flow from
ingestion through two-cycle stable recovery and produces a traceable,
conservatively attributed outcome. Synthetic fixture success demonstrates the
architecture; it does not prove customer value.

This file is now the canonical comprehensive architecture and working guide.
Keep it updated in the same change that adds a major model, API, event, job,
authority boundary, module workflow or user-facing product surface.
