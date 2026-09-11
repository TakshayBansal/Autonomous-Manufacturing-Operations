# Core platform phase completion matrix

## Phase 0 — Architecture audit

Complete. The current-to-target model, endpoint, worker, agent, integration,
authorization, recovery, and compatibility decisions are recorded in
`docs/architecture/current-to-target-map.md`.

## Phase 1 — Platform foundation

Complete for the current three modules. Company/Plant/Supplier/Area/Line/Asset
and Task are reused as canonical records. Material, Product, BOM, inventory
location/position, source identity, relationships, and provenance are platform
owned. Backfill is deterministic, restartable, tenant-scoped, and reports
ambiguous identities.

## Phase 2 — Events

Complete for critical current flows. Versioned contracts, registry validation,
outbox delivery, retries, consumer receipts, correlation/causation, PO delivery
rescheduling, inventory updates, SCM planning, Recovery lifecycle, actions, and
work events are implemented. The product is deliberately not event sourced.

## Phase 3 — Factory state

Complete foundation. Material inventory/risk and Operations work-order state
are queryable through one API with provenance and freshness. Late observations
cannot roll a current inventory projection backwards.

## Phase 4 — Actions, policy, approval

Complete foundation. SCM interventions and recovery strategy selection use the
shared intent/policy/approval/execution/outcome ledger. External execution is
simulation-only unless an existing governed connector path is explicitly used.

## Phase 5 — Operational cases

Complete. Procurement cases, Operations recovery cases, and SCM shortage cases
are indexed through one API while domain detail and verification remain intact.

## Phase 6 — Shared work/workflow

Complete for the modular monolith. Existing Task is the canonical work item and
is exposed through the platform work queue. Domain workflows remain in-process;
Temporal is intentionally dormant pending the documented operational triggers.

## Phase 7 — Agent runtime

Complete boundary. Agents receive typed tenant/site factory context and a
restricted tool contract. Consequential changes can only be proposed through
ActionIntent. Existing agent engines remain compatible while migrating role by
role.

## Phase 8 — Integration hardening

Complete foundation. Existing connector contracts are retained and ingestion
now writes SourceSystem health, external identity, provenance, mapping versions,
and checkpoints/receipts. Excel, ERP, REST/OData/SFTP/SOAP/iPaaS and simulator
adapters remain registered through the shared connector SDK.

## Phase 9 — Temporal/Kafka

Correctly deferred. The architecture explicitly says to deploy these only when
long-running workflow recovery, throughput, replay, or service separation
justifies their operational cost. Current adapter boundaries allow adoption
without changing domain semantics.

## Phase 10 — Plant edge

Read-only skeleton already exists through EdgeGateway, EdgeSourceMapping,
EdgeSourceHealth, EdgeIngestReceipt, simulator connectors, TLS/outbound-only
configuration, buffering, and heartbeat concepts. Real OPC UA/MQTT connectivity
and physical commands are correctly deferred until a customer machine use case.
No LLM or application endpoint can command a PLC.
