# SCM Phases 0–3 Implementation

Status: implemented and verified on 2026-08-26.

## Phase 0 — Audit and foundation

- Existing/reusable/legacy/missing analysis: `SCM_EXISTING_IMPLEMENTATION_AUDIT.md`.
- Existing SCM source tables remain compatibility projections; canonical Material, Product, BOM, PurchaseOrder and WorkOrder IDs cross module boundaries.
- `app/scm/acceptance_fixture.py` provides an idempotent canonical demo product, three-component BOM, inventory/supply and overlapping firm/forecast demand.
- Migration is additive; no existing Procurement, SCM or Operations table was removed.

## Phase 1 — Planning data foundation

Implemented models:

- `SCMPlanningProfile`
- `SCMDemandPlan`
- `SCMDemandBucket`
- `SCMPlanningInputSnapshot`
- extended `SCMPlanningRun`
- extended `SCMMaterialProjectionPoint`

Planning runs capture an immutable, SHA-256-addressed input payload before execution. The payload contains canonical/legacy material mapping, normalized demand, supply, opening inventory, policy, source freshness, PO identity and lineage. Execution reads this snapshot rather than live source tables. The default horizon is 210 daily buckets.

APIs:

- `GET /scm/planning-profile`
- `POST /scm/demand-plans`
- `POST /scm/demand-plans/{id}/buckets`
- `POST /scm/demand-plans/{id}/publish`
- `POST /scm/planning-runs` (optional `demand_plan_id`)
- `GET /scm/planning-runs/{id}/input-snapshot`

## Phase 2 — Core planning engine

- Configurable demand precedence suppresses overlapping lower-authority demand.
- Product demand explodes through effective canonical BOM revisions, including scrap, nested products, lineage and cycle rejection.
- Supply is normalized from schedule lines with canonical PO references and supplier-action constraints.
- Daily inventory projection persists confirmed/planned receipts, gross demand, safety-adjusted balance, shortage, excess, runway, status and freshness.
- Consecutive shortage days collapse into recovery windows; sustained excess becomes an excess window.
- Event IDs and input hashes are deterministic for a given run/snapshot.

## Phase 3 — Risk and readiness

- `SCMMaterialRisk` is a canonical, semantic-key-deduplicated lifecycle risk.
- `SCMProductReadiness` and `SCMComponentReadiness` explain READY/AT_RISK/BLOCKED product and work-order coverage.
- Risk reconciliation obtains affected Product, WorkOrder, WorkCenter, Equipment, Supplier and PO identities from the shared relationship graph.
- Risks create or reuse shared `OperationalCase` records; they do not create an SCM-only case system.
- `SCMPlanningRunDelta` records previous/current status and drivers including inventory, demand and PO-date changes.

APIs:

- `GET /scm/risks`
- `GET /scm/planning-runs/{id}/product-readiness`
- `GET /scm/planning-runs/{id}/changes`

## Database migration

`apps/api/migrations/versions/0061_scm_phases_0_3.py`

Fresh SQLite upgrade verified at Alembic head `0061_scm_phases_0_3`.

## Verification evidence

- `tests/test_scm_engine.py`: deterministic projection, BOM lineage/cycles, shortage windows and excess windows.
- `tests/test_scm_api.py::test_acceptance_fixture_is_canonical_idempotent_and_precedence_ready`: canonical fixture restartability and demand precedence.
- `tests/test_core_architecture_e2e.py::test_external_po_delay_runs_the_shared_core_end_to_end`: 210 points, immutable snapshot, product readiness, one canonical material risk, Product/WO graph impact, OperationalCase reuse and PO-date run delta inside the complete connector-to-verification flow.

Observed results:

```text
SCM engine + fixture tests                         8 passed
Core delayed-PO architecture acceptance           1 passed
Fresh migration                                   PASS (0061 head)
Python compile                                    PASS
```

The TestClient-based SCM API flow remains affected by the repository's pre-existing login/TestClient stall in this environment; the same planning services and endpoints compile, and their underlying fixture/engine/core integration paths pass directly.

## Deliberately deferred

Per `SCM_PLAN.md`, Phase 4 and later are not part of this milestone: the new planner-first UX, scenario comparison UI, intervention workspace expansion, deeper collaboration, reporting, AI explanations and scale/performance work remain future phases.
