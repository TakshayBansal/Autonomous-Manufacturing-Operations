# SCM Existing Implementation Audit

Recorded before Phase 0–3 implementation.

## Existing

- Daily deterministic material projection with configurable 30–365 day horizon.
- Opening inventory, firm requirements, forecasts, scheduled supply, partial receipts and FIFO pegging.
- Safety stock, runway/stockout date, recovery date and severity calculation.
- Deterministic pull-in/new-buy recommendation generation.
- Multi-level SCM BOM explosion utility with effective dates, scrap and cycle detection.
- Persisted planning policies, scenarios, runs, planning events, daily projection points, pegs, risk summaries and recommendations.
- SCM Excel preview/validation/import with source receipts, provenance and idempotency.
- Event-driven site replanning through the shared transactional outbox.
- Shared canonical Material/Product/BOM/Inventory/PO/WorkOrder identities and mapping adapters.
- Shared relationship traversal, FactoryState, OperationalCase and ActionIntent integration.
- Initial Control Tower, exceptions, materials and material-detail APIs/UI.

## Reusable

- `scm/engine.py`: deterministic inventory projection and recommendation mathematics.
- `scm/bom.py`: recursive BOM explosion and lineage.
- `SCMPlanningPolicySet` and `SCMMaterialPlantPolicy`: global and material/site rules.
- `SCMPlanningRun`, `SCMPlanningEvent`, `SCMMaterialProjectionPoint` and `SCMSupplyDemandPeg`.
- Existing SCM source tables as compatibility/ingestion projections while canonical migration continues.
- Core platform events, provenance, graph, state, cases, actions, approvals, audit and traces.

## Partially reusable

- `SCMDemandForecast` and `SCMMaterialRequirement` store demand, but there is no versioned DemandPlan/DemandBucket contract or configurable source precedence.
- `SCMPlanningRun.input_version_summary` records counts/timestamps, but not an immutable reproducible input snapshot.
- `SCMMaterialRiskSummary` is a per-run summary, not a deduplicated risk lifecycle with shortage windows, canonical IDs and resolution state.
- BOM explosion exists as a unit-level algorithm but is not integrated into planning input assembly from canonical Product/BOM demand.
- Existing projection points contain opening/supply/demand/closing/safety/risk, but not separated supply categories, shortage/excess quantities, runway and canonical material identity.
- Material impact currently uses SCM BOM joins; shared graph impact exists but is not persisted into SCM risks/readiness.
- OperationalCase creation exists for severe risks but deduplicates by planning event, not by the underlying active risk.

## Duplicate / legacy

- `SCMMaterial`, `SCMBOM` and `SCMBOMLine` overlap canonical platform Material/Product/BOM records.
- `SCMInventorySnapshot` overlaps the canonical inventory read model.
- `SCMSupplyOrder` overlaps canonical PurchaseOrder.
- These tables remain compatibility and planning-source projections for now; every cross-module result must also retain canonical IDs.

## Missing

- PlanningProfile and versioned DemandPlan/DemandBucket persistence.
- Immutable PlanningInputSnapshot with hash/version/source freshness.
- Integrated demand precedence and product-demand BOM explosion.
- First-class shortage windows and excess detection.
- MaterialRisk lifecycle with canonical identity, impact, structured root causes, case linkage and deduplication.
- Product/work-order material readiness projections.
- Structured changes/drivers between consecutive planning runs.
- Phase 0–3 canonical acceptance fixture and complete deterministic tests.

## Needs migration

- Add Phase 1–3 tables and additive fields; do not remove existing SCM tables.
- Backfill canonical material IDs onto planning projections/results through `ExternalEntityReference`.
- New demand and planning APIs use canonical Product/Material/WorkOrder identities.
- Existing SCM runs remain readable; new runs persist both legacy planning IDs and canonical IDs during the compatibility period.
- Existing risk-summary APIs remain compatible while new risk/readiness/delta APIs become authoritative for Phase 3 behavior.

## Target after Phase 3

```text
Canonical factory data + versioned DemandPlan
        ↓
immutable SCMPlanningInputSnapshot
        ↓
demand precedence + canonical BOM explosion
        ↓
210-day deterministic daily projection
        ↓
shortage windows + excess + runway
        ↓
deduplicated MaterialRisk
        ↓
graph impact + Product/WorkOrder readiness
        ↓
OperationalCase + run-change explanation
```

