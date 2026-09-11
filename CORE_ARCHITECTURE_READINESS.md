# GenuineGigs Core Architecture Readiness

Assessment date: 2026-08-26

Scope: final shared-core hardening required before deep SCM development. This report deliberately excludes speculative Manufacturing-OS infrastructure.

## A. Changes made

### Files

- `apps/api/app/platform/models.py`
- `apps/api/app/db/models.py`
- `apps/api/app/platform/integrations.py`
- `apps/api/app/platform/purchase_orders.py`
- `apps/api/app/platform/relationships.py`
- `apps/api/app/platform/integrity.py`
- `apps/api/app/platform/state.py`
- `apps/api/app/platform/actions.py`
- `apps/api/app/platform/trace.py`
- `apps/api/app/platform/simulation.py`
- `apps/api/app/platform/backfill.py`
- `apps/api/app/platform/event_registry.py`
- `apps/api/app/platform/router.py`
- `apps/api/app/eventing.py`
- `apps/api/app/scm/service.py`
- `apps/api/app/scm/imports.py`
- `apps/api/migrations/versions/0060_scm_readiness_core_hardening.py`
- `apps/api/tests/test_core_architecture_e2e.py`
- `docs/architecture/core-hardening-implementation-audit.md`
- `CORE_ARCHITECTURE_READINESS.md`

### Models

Added:

- `PlatformPurchaseOrder`
- `PlatformPurchaseOrderLine`
- `PlatformWorkOrderReference`
- `PlatformScenarioDefinition`
- `PlatformSimulationRun`

Extended:

- `EntityRelationship`: source system, provenance ID and confidence.
- `PlatformStateSnapshot`: correlation ID.
- `DataProvenance`: correlation ID.
- `ActionIntent`: originating case, reason code, evidence, expected impact, confidence and risk level.
- `ActionExecution`: external reference and retained error.
- `OperationalCase`: correlation ID, canonical entity reference and resolution evidence.
- `EventOutbox`: next-attempt and dead-letter timestamps.

### Migration

- `0060_scm_readiness_core_hardening`: additive tables and columns only; no destructive legacy-table removal.
- Verified on a fresh SQLite database from migration `0001` through `0060`.

### Services

- Canonical PO delivery-update ingestion with source receipt, mapping validation, provenance, deduplication, snapshot and transactional event.
- Safe simulated canonical PO reschedule executor used only behind approved `ActionIntent`.
- Canonical graph `connect`, neighbor lookup, bounded traversal, path search, dependencies, dependents and impact.
- Idempotent graph synchronization from BOMs, POs, inventory, work orders, material requirements, work centers and equipment.
- Canonical integrity checks for duplicate materials, orphan module masters, invalid suppliers/sites, broken BOM/PO/work-order references.
- `FactoryStateService.now`, `.at` and `.history` over domain-optimized projections.
- Unified chronological `correlation_trace` assembled from existing provenance, outbox, consumer receipt, state, SCM, case, action and audit records.
- Generic scenario definition and domain simulation-run envelope.
- SCM conservative PO-date intervention when a detected shortage has no algorithm-generated candidate.
- External action execution and explicit evidence-based outcome verification.

### APIs

- `GET /api/v1/platform/state/{entity_type}/{entity_id}`
- `GET /api/v1/platform/state/{entity_type}/{entity_id}/history`
- `GET /api/v1/platform/relationships/{entity_type}/{entity_id}`
- `GET /api/v1/platform/impact/{entity_type}/{entity_id}`
- `GET /api/v1/platform/traces/{correlation_id}`
- `GET /api/v1/platform/integrity`

### Events

The versioned catalog now includes the required Procurement, SCM and Operations families. The acceptance flow uses:

- `purchase_order.rescheduled`
- `scm.planning.completed`
- `platform.action.proposed`
- `platform.action.approved` / `platform.action.rejected`
- `platform.action.executed` / `platform.action.execution_failed`
- `platform.action.outcome_verified`

The canonical envelope retains event/schema version, tenant, plant, actor, source, subject, occurrence/recording timestamps, correlation and causation. Outbox dispatch now persists failed-consumer receipts, exponential retry eligibility and dead-letter time.

### Tests

`apps/api/tests/test_core_architecture_e2e.py`:

- `test_external_po_delay_runs_the_shared_core_end_to_end`
- `test_duplicate_external_update_is_idempotent`
- `test_invalid_mapping_retains_rejected_receipt_and_provenance`
- `test_policy_and_approval_rejection_block_execution`
- `test_execution_failure_and_false_recovery_are_distinct`
- `test_outbox_and_consumer_failures_are_retryable_and_idempotent`
- `test_external_identity_cannot_be_silently_remapped`

Architecture suite result: **7 passed**.

Regression selection covering existing platform foundations, SCM engine/imports, PO amendments and Operations recovery: **19 passed**.

A bounded full-suite run progressed through the first approximately 180 tests with no failure, then reached the repository's known long-running section and was stopped at the 240-second verification limit. It is not represented as a complete full-suite pass.

## B. Canonical-model status

| Entity | Status | Remaining dependency |
|---|---|---|
| Material | Canonical; partially migrated | `Item` and `SCMMaterial` remain as compatibility/domain records and must resolve through `ExternalEntityReference`. |
| Supplier | Canonical | Shared `Supplier` is authoritative; SCM references it directly. |
| Site | Canonical | Shared `Plant` is authoritative. |
| Product | Canonical; partially migrated | Operations `ManufacturingProduct` remains and is backfilled/mapped. |
| BOM | Canonical; partially migrated | SCM and Operations BOM tables remain as domain/import compatibility records. |
| Inventory | Canonical read model; partially migrated | SCM snapshots and Operations positions remain source projections. |
| PurchaseOrder | Canonical; partially migrated | Procurement `PODraft` remains behavior/transaction owner; SCM consumes `PlatformPurchaseOrder` and mapping, not Procurement storage. |
| WorkOrder | Canonical shared identity; partially migrated | Operations `ProductionWorkOrder` remains behavior owner and is bridged by `PlatformWorkOrderReference`. |
| WorkCenter | Canonical | Shared `ProductionLine` is the current work-center identity. |
| Equipment | Canonical | Shared `PlantAsset` is the current equipment identity. |

No dangerous flag-day table removal was performed.

## C. End-to-end flow result

| Step | Result | Evidence |
|---|---|---|
| Connector | PASS | `test_external_po_delay_runs_the_shared_core_end_to_end` enters through `ingest_delivery_update`. |
| Canonical mapping | PASS | Same test resolves source PO, Supplier, Material and Site without duplicate masters. |
| Provenance | PASS | Same test asserts correlated PO provenance and material-state provenance. |
| Outbox | PASS | Same test asserts pending transactional `EventOutbox` record and complete envelope. |
| Event | PASS | Same test processes `purchase_order.rescheduled`. |
| Idempotency | PASS | Same test dispatches the event twice; duplicate test re-ingests the same external record. |
| Factory state | PASS | Same test asserts runway 8–10 days, supply gap at least two days, freshness and provenance. |
| Graph traversal | PASS | Same test traverses PO → Material → Product → WorkOrder → WorkCenter and path-searches PO to WO. |
| SCM risk | PASS | Existing deterministic SCM planner changes baseline GREEN to shortage risk after day-12 supply. |
| Operational case | PASS | Same test asserts one correlated material-shortage case. |
| ActionIntent | PASS | Same test asserts a case-linked, evidenced PO reschedule intent. |
| Policy | PASS | Same test asserts approval-required policy; rejection test blocks prohibited action. |
| Approval | PASS | Same test uses manager membership; rejection test retains rejection. |
| Execution | PASS | Same test uses a fake SAP executor and retains external receipt. |
| Outcome | PASS | Connector execution creates a pending outcome rather than claiming recovery. |
| State recomputation | PASS | Outcome PO event triggers a second real SCM planning run. |
| Verification | PASS | Post-action safe SCM state resolves the case; false-recovery test proves execution success alone is insufficient. |
| Trace | PASS | Same test asserts provenance, event, consumer, state, plan, case, recommendation, action, policy, approval, execution, verification and audit steps. |

Tenant scope is applied to ingestion, canonical lookup, graph, event, state, case, action and trace queries.

## D. Failure-path results

| Failure path | Result | Evidence |
|---|---|---|
| Duplicate external event | PASS | `test_duplicate_external_update_is_idempotent` |
| Outbox delivery/publisher interruption | PASS | `test_outbox_and_consumer_failures_are_retryable_and_idempotent` proves committed pending event remains dispatchable. |
| Consumer failure | PASS | Same test proves failed receipt, retained error, retry and eventual single completion. |
| Invalid canonical mapping | PASS | `test_invalid_mapping_retains_rejected_receipt_and_provenance` |
| Policy rejection | PASS | `test_policy_and_approval_rejection_block_execution` |
| Approval rejection | PASS | `test_policy_and_approval_rejection_block_execution` |
| Execution failure | PASS | `test_execution_failure_and_false_recovery_are_distinct` |
| False recovery | PASS | Same test records successful execution but failed verification and keeps case open. |

Permanent invariants are exercised by those tests: external identities cannot be remapped silently; consumers are idempotent; consequential connector actions require approved intents; external mutations retain provenance; intents retain correlation/audit; execution and recovery are distinct; SCM proposes rather than directly mutating Procurement records; and graph edges use canonical IDs.

## E. Remaining architecture debt

### BLOCKS SCM DEVELOPMENT

None found after the acceptance flow and failure tests passed.

### SHOULD FIX WHILE DEVELOPING SCM

- Migrate each newly touched SCM query from `SCMMaterial`/`SCMBOM` IDs toward canonical IDs or an explicit canonical mapping adapter; do not add new unbridged identities.
- Add graph synchronization hooks to new SCM write services as they are introduced. Existing imports/backfill and the canonical PO ingestion flow are covered.
- Extend canonical PO line/status/receipt fields only when deep SCM planning requires them; keep Procurement as behavior owner.
- Add PostgreSQL CI coverage for recursive/bounded traversal and concurrent outbox claiming. Current acceptance uses SQLite and the production design remains PostgreSQL-compatible.
- Add explicit uniqueness/index tuning from production query telemetry if graph/state volume warrants it.
- Continue replacing older event aliases with cataloged canonical names when their owning module code is changed.

### SAFE TO DEFER

- Neo4j or another dedicated graph database.
- Graph visualization and 3D factory UI.
- Full digital twin or whole-factory discrete-event simulator.
- Lakehouse, Iceberg, Spark, dbt, warehouse or ClickHouse migration.
- Feature store, model registry, general ML/drift platform.
- Production OPC-UA/MQTT edge stack.
- Kubernetes, service mesh or microservice decomposition.
- L4/L5 autonomous execution, autonomous machine control or self-modifying policy.

## F. Recommendation

> Is the GenuineGigs core now sufficiently stable for primary development effort to move to the deep SCM module?

**YES**

The required cross-layer architecture is demonstrated by a deterministic integration test, including failure recovery, tenant scope, canonical identity protection, idempotency, governance, auditability and post-action verification. There are no structural core blockers to deep SCM development.

The remaining core work should be opportunistic and demand-driven: preserve canonical mappings in every new SCM feature, attach graph/state hooks to new writes, and add PostgreSQL concurrency/index verification as SCM load characteristics become concrete. Generic core-platform expansion should stop here.
