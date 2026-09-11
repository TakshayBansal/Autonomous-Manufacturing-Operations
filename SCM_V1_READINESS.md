# GenuineGigs SCM V1 Readiness

Assessment date: 2026-08-26

This report covers `SCM_PLAN.md` Phases 0–9 and the deliberately scoped initial Phase 10/V1.5 capabilities. It does not claim production scale or design-partner validation before real customer data is exercised.

## Product areas

| Area | Result | Evidence |
|---|---|---|
| Control Tower | PASS | `/scm`, persisted run/risk/source KPIs |
| Material Explorer | PASS | `/scm/materials`, search, dense table, CSV export |
| Material 360 | PASS | `/scm/materials/{id}`, projection, events, pegs, impact, recommendations |
| Supply Horizon | PASS | `/scm/horizon`, 30/90/210/365-day view, risk filter, receipt markers, virtualized rows |
| Product Readiness | PASS | `/scm/readiness`, READY/AT_RISK/BLOCKED and component evidence |
| Risks & Exceptions | PASS | `/scm/exceptions`, lifecycle risk queue and status API |
| Recommendation Engine | PASS | pull-in, push-out, cancel/reduce, new buy, transfer candidate, deterministic ranking/simulation |
| Scenario Lab | PASS | immutable baseline, overrides, save/duplicate/run/compare |
| Action Integration | PASS | simulation → ActionIntent → policy/approval/execution/outcome/verification |
| Data Health | PASS | `/scm/imports`, source freshness, rejected/conflict rows and import history |
| Excel/ERP ingestion | PASS | preview, validation, commit, source receipts, saved mapping-profile API, export |

## Planning correctness

| Capability | Result | Evidence |
|---|---|---|
| BOM explosion | PASS | effective canonical BOM, nested lineage, scrap and cycle tests |
| Inventory projection | PASS | immutable snapshot produces persisted daily buckets |
| Runway | PASS | deterministic engine and core delayed-PO acceptance |
| Shortage windows | PASS | consecutive stockout window/recovery test |
| Excess detection | PASS | sustained excess window test |
| Pull-in | PASS | late movable receipt candidate and simulation |
| Push-out | PASS | excess receipt adjustment candidate |
| Cancellation | PASS | contractual cancellation flag and excess candidate |
| Readiness | PASS | missing component blocks canonical product/work order |
| Run delta/change explanation | PASS | PO date, demand and inventory drivers |

## Platform integration

| Capability | Result | Evidence |
|---|---|---|
| Canonical IDs | PASS | legacy SCM compatibility IDs map to platform entities |
| Events | PASS | transactional outbox and event-driven replan |
| Provenance | PASS | ingestion receipts and snapshot lineage |
| Graph impact | PASS | Material → Product → WorkOrder → WorkCenter traversal |
| OperationalCase | PASS | semantic risk reuses one shared case |
| ActionIntent | PASS | SCM proposes; it does not directly mutate Procurement records |
| Policy/Approval | PASS | shared platform authority boundary |
| Execution | PASS | safe simulated connector execution |
| Verification | PASS | post-action state proves recovery independently of execution success |
| Trace | PASS | shared correlation trace contains planning through verification |

## Delivered by remaining phase

### Phase 4–5

- Planner-first navigation and explicit loading/error/empty states.
- Control Tower, Material Explorer, Material 360, risk queue, product readiness and performant Supply Horizon.
- Persisted read models; the frontend does not perform BOM/planning calculations.

### Phase 6

- Existing pull-in/push-out/cancel/new-buy logic hardened with explainable score dimensions and ranks.
- Persisted deterministic recommendation simulations compare before/after risk metrics.
- Candidate actions cannot be created through the SCM API unless simulation resolves the risk.

### Phase 7

- Scenarios reference an immutable baseline planning snapshot.
- Inventory, demand, safety-stock, supply-date and supply-quantity overrides are isolated.
- Save, duplicate, run and baseline comparison APIs/UI.

### Phase 8

- Recommendation-to-ActionIntent path uses shared policy, approval, execution, outcome and verification.
- Existing complete connector-to-recovery architecture test remains green.

### Phase 9

- Import preview/validation/commit, source quality, mapping-profile version APIs, export, saved views, planner notes and audited operational overrides.
- Operational overrides are visible in immutable snapshots and never overwrite source records.

### Phase 10 / initial V1.5

- Explainable interplant transfer candidate using fresh canonical inventory at another site.
- Supplier Control Center aggregates supplied materials, open POs, confirmations and delays.
- Existing product cockpit/readiness and shared action outcomes supply the initial action analytics foundation.

## Verification

```text
Fresh Alembic migration to 0062                 PASS
Python compile                                  PASS
Ruff changed SCM backend                        PASS
SCM/core selected backend acceptance            10 passed
Next.js production compile + TypeScript         PASS
```

Important tests:

- `tests/test_scm_engine.py`
- `tests/test_scm_api.py::test_acceptance_fixture_is_canonical_idempotent_and_precedence_ready`
- `tests/test_core_architecture_e2e.py::test_external_po_delay_runs_the_shared_core_end_to_end`
- `tests/test_core_architecture_e2e.py::test_scenario_runs_from_immutable_baseline_without_mutating_operational_data`

## Remaining gaps

### BLOCKS DESIGN-PARTNER USE

- None identified structurally. A real design-partner dataset must still pass import mapping and reconciliation before operational rollout.

### SHOULD FIX DURING PILOT

- Validate planning performance and UI row density using the customer's actual 3,800+ material dataset.
- Tune recommendation cost/feasibility weights using real supplier and commercial terms.
- Add customer-specific workbook templates and surface saved mapping selection directly in the import form.
- Expand multi-plant transfer buffers from the initial positive-origin-balance rule to full origin-site projected demand/safety calculations.
- Add digest notifications after planner transition thresholds are agreed with users.
- Resolve the repository's existing TestClient login stall so all HTTP tests can run reliably in this environment.

### SAFE TO DEFER

- Advanced supplier reliability modelling and action analytics based on months of observed outcomes.
- AI prose explanations; structured explanations remain authoritative.
- Incremental sub-site replanning optimization beyond correct site-level recomputation.
- Dedicated graph database, lakehouse, generic ML infrastructure, 3D twin and autonomous execution.

## Recommendation

**YES — SCM V1 is structurally ready for design-partner data onboarding and workflow validation.**

The next work should be driven by real planner usage and data reconciliation, not additional speculative platform expansion.
