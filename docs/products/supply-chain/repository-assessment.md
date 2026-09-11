# GenuineGigs SCM Repository Assessment

## Current architecture

GenuineGigs is a modular monolith with a FastAPI/SQLAlchemy/Alembic backend in
`apps/api`, a Next.js 16/React 19 frontend in `apps/web`, PostgreSQL as the
production database, Redis/Celery for background work, and MinIO-compatible
object storage. Docker Compose starts migrations and seed jobs separately from
the API. Tests use pytest (SQLite for service tests, PostgreSQL through the
container workflow) and Playwright for browser coverage.

The current working tree contains substantial in-progress V2 work. SCM changes
must remain additive and must not revert, reformat, or replace those files.

## Reuse decisions

| SCM concern | Existing capability | Decision |
| --- | --- | --- |
| Tenant and organization | `Tenant`, `Company` | Reuse unchanged. Tenant remains the isolation boundary and Company the business organization. |
| Plant and user scope | `Plant`, `WorkspaceMembership`, `OperationalScope`, `UserPlantAccess` | Reuse. Initial SCM access is tenant-feature-flagged and admin-only. |
| Procurement material | plant-scoped `Item` | Preserve for procurement. Add a tenant/company-level SCM material linked to plant Items. |
| Supplier and PO execution | `Supplier`, `PODraft`, `PODraftLine`, acknowledgements, ASNs, receipts | Reuse as source/execution records. Add planning projections and schedule-line semantics without changing procurement behavior. |
| Operational material readiness | `MaterialInventoryPosition`, `ProductionMaterialRequirement`, `ProductionSupplierCommitment`, `MaterialReadinessSnapshot` | Reuse as optional source records. Keep the short-horizon V2 readiness calculation and history intact. |
| Integration | connector registry, `IntegrationConnection`, mapping profiles, import batches/row results, external record state, reconciliation | Extend. Do not build a parallel import framework. |
| Raw files and evidence | `Document` plus private object storage | Reuse for file retention; import rows retain source-cell lineage. |
| Events and jobs | transactional `EventOutbox`, consumer receipts, Celery, Redis | Extend with SCM event consumers and a dedicated `scm` queue. Redis is never authoritative. |
| Audit and observability | `AuditEvent`, correlation middleware, Prometheus metrics, health endpoints | Extend with SCM operations and calculation metrics. |
| Frontend | V2 auth/query/formatting primitives and React Query | Reuse visual and runtime primitives, but expose SCM as a separate `/scm` workspace. |

## Required additions

- Cross-plant SCM material identity, plant policy, UOM conversion, supplier
  planning constraints, customer usage, and effective-dated nested BOMs.
- Immutable inventory, demand, supply schedule, receipt, source freshness, and
  import-lineage records suitable for planning.
- Versioned policy, scenario, adjustment, run, event, projection, peg, risk,
  and recommendation records.
- A pure deterministic engine for BOM explosion, daily projected balance,
  stockout/recovery, coverage, pegging, severity, and generic action candidates.
- `/scm` APIs and four UI surfaces: control tower, exception workbench,
  material detail, and imports/data quality.

## Conflicts and safeguards

- `Item` is plant-scoped, while SCM requires a cross-plant material master.
  Refactoring Item would destabilize procurement, so SCM uses a linked master.
- `ManufacturingBOMLine` lacks revision/effectivity and nested material
  identity. It remains an operational source; SCM receives its own versioned
  BOM projection.
- `MaterialReadinessSnapshot` is work-order focused and short horizon. It is
  not reused as a multi-month planning result.
- `PODraftLine` has no receipt schedule lines. SCM supply orders retain a source
  reference and separate schedule lines.
- Current quantities are mostly floats. New SCM calculations use Decimal and
  NUMERIC columns to keep deterministic arithmetic stable.
- Unvalidated SAP/OData/SFTP/REST adapters remain contract boundaries only.

## Implementation sequence

1. Register the SCM package, feature flag, authorization dependency, ORM
   models, and a single forward Alembic migration after revision 0056.
2. Add pure domain services and golden unit fixtures before API persistence.
3. Extend the existing import/connector contracts for SCM file and mock data.
4. Add planning-run orchestration, event-driven impacted-set recomputation,
   audit, and metrics.
5. Expose typed `/scm` APIs and regenerate the OpenAPI contract.
6. Add the separate SCM frontend workspace and four functional screens.
7. Run migration, focused tests, the full backend suite, frontend typecheck,
   build, and browser smoke coverage.

## Deliberately deferred

Live SAP transport, ERP write-back, customer-specific formulas, alternate-part
optimization, ML forecasting, LLM arithmetic, and production/pilot certification
remain out of scope until design-partner discovery supplies validated contracts.
