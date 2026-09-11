# GenuineGigs V2 Technical Audit

## Baseline

Audited against the clean repository baseline at Alembic head
`0044_proactive_companion`. GenuineGigs V1 is a working modular monolith: a
Next.js 16/React 19 frontend, FastAPI/SQLAlchemy backend, PostgreSQL canonical
store, Redis/Celery coordination, private object storage, transactional outbox,
and a bounded LangGraph/Groq agent runtime. V2 must extend this baseline rather
than replace it.

## Reuse map

| V2 concern | Existing primitive | Migration decision |
|---|---|---|
| Identity and tenancy | tenants, accounts, memberships, users, plant access | Reuse unchanged |
| Plant | existing `plants` | Extend with areas, lines, assets and shifts |
| Operational work | tasks, commitments, delegation | Link an Operational Action to the existing task; do not create a second inbox |
| Policy and approval | permission checks, policy decisions, approvals, governed execution | Reuse for every important action |
| Events | transactional `event_outbox`, consumers and receipts | Emit canonical V2 event names through the existing outbox |
| Evidence and audit | documents, generated artifacts, audit events | Add polymorphic evidence references; retain append-only audit |
| Integrations | connector SDK, mappings, sync jobs, controlled writes/read-back | Extend with V2 canonical entity mappings and freshness |
| Agents and Gigi | capability registry, bounded tool loop, companion interventions | Add grounded V2 read/prepare tools; preserve mutation budgets |
| Procurement | complete requirement-to-finance lifecycle | Link into material readiness in Phase 3 |
| Deployment | Compose, Helm, API/worker/web services | Preserve; no Phase 1 microservices |

## Frontend

V1 routes render through a large `IndustrialConsole` and a hand-written API
client. Keep these routes operational. V2 receives an independent `/v2` route
group, reusable operational components and a query/cache boundary. The existing
Manrope and Lucide choices are compatible with the V2 UI contract. Server data,
not page-local mock arrays, remains canonical.

## Backend

The existing API entrypoint, database model file and agent dispatcher are large.
V2 logic therefore lives in focused modules and an included `/api/v2` router.
Routers handle HTTP only; deterministic calculations and lifecycle rules live in
services. Existing tenant/plant scoping is repeated at every service boundary.

## Migration dependencies

1. Add plant hierarchy and Phase 1 operational tables after migration 0044.
2. Seed the canonical Pune Plant/Shift B scenario through the backend seed path.
3. Add deterministic production forecasting, deviation detection, action routing
   and value calculation.
4. Expose explicit V2 query/command APIs and SSE without changing V1 contracts.
5. Build V2 pages against those APIs, then add grounded Gigi tools.
6. Link procurement entities to material requirements in Phase 3; never copy
   existing RFQ/PO/receipt/inspection truth.

## Risks and controls

- Preserve V1 regression coverage after every V2 increment.
- Use feature flags and parallel routes for rollout and rollback.
- Keep calculations, severity, money, permissions and state transitions outside
  model prompts.
- Use one active deviation per detector/plant/line/shift/work order and update it
  idempotently.
- Display stale input as degraded data instead of precise forecasts.
- Treat vendor adapters as unverified until customer/UAT evidence exists.
- Defer Kafka, graph databases, time-series migration, microservices and OT writes.

## Phase 0 conclusion

No foundation rewrite is required. The safe seam is an additive V2 domain layer
that reuses V1 identity, tasks, policy, audit, events, integrations and agents.
Phase 1 can begin without breaking the proven procurement lifecycle.
