# Agentic procurement operating system

## Runtime ownership

Canonical domain services remain the only writers of procurement records.
Agents and specialists may read scoped records, create private prepared work,
or submit a confirmation-bound proposal. The governed execution sequence is:

```text
membership and plant scope
→ capability metadata
→ OPA decision
→ server-side obligations
→ entity and version re-resolution
→ confirmation when required
→ canonical service
→ receipt, audit, and transactional event
```

OPA augments rather than replaces database authorization. In `shadow` mode its
decisions are persisted but do not change existing outcomes. In `enforce` mode
an unavailable OPA denies agent mutations while read-only operations retain the
existing server authorization fallback.

## Durable procurement cycles

`procurement_cycle_objectives` are rooted in a purchase requirement or line.
Fourteen normalized stage records preserve requirement, specification, RFQ,
supplier response, quotation review, comparison, approval, negotiation, PO,
fulfilment, receipt, quality, invoice, and closure history. The evaluator uses
canonical records and deterministic calculations only. A smaller presentation
mapping drives My Day without discarding backend history.

Evaluation is serialized by row locks in the event consumer and is idempotent
by objective root, stage key, risk/dependency semantic key, aggregate version,
and event consumer receipt. Lazy API backfill is a rollout bridge; the scheduled
worker performs ongoing evaluation.

## Events and workers

SQLAlchemy session hooks append standard outbox envelopes for canonical changes
in the same database transaction. Celery dispatches pending events. Consumer
receipts prevent duplicate completed effects; retry count and dead-letter state
are administrator visible, and replay does not repeat completed consumers.

Long specialist work persists an `AgentRunAttempt`, public progress events,
checkpoints, cancellation state, and prepared-work output. Hidden model reasoning
is never emitted. Short read-only questions continue through the bounded
synchronous runtime.

## Specialists and models

Eight bounded specialist names cover requirement/specification, supplier/RFQ,
quotation normalization, comparison/award, fulfilment, receipt/quality, invoice,
and cycle risk. Every finding has evidence and confidence. Deterministic code
owns costs, dates, scores, allocation, and stage evaluation. The model gateway
is limited to structured classification, extraction repair, explanation, and
scenario narration with task profiles, validation, retry, timeout, token/cost
limits, prompt versions, and deterministic fallback.

## Sandboxes

`SandboxProtocol` defines create, upload, fixed-operation execute, declared-output
download, and terminate. Local development uses an ephemeral private directory.
Production uses the internal hardened runner boundary. Neither interface exposes
an arbitrary shell. Inputs and outputs are path-, MIME-, size-, checksum-, and
malware-signature validated. Each run has a TTL and persisted lifecycle record.
Deep Agents integrations receive only the narrow adapter.

The production runner is deployed independently with non-root execution,
read-only root filesystem, a quota-limited workspace, dropped capabilities,
seccomp/AppArmor, no host mounts, no container socket, blocked metadata access,
and default-denied network. It receives no database, Redis, object-storage,
cloud, or model-provider credentials.

## Temporal boundary

The first procurement workflow contract is present but disabled by default.
Its state and signals are deterministic and replay-safe. Enable
`temporal_procurement_workflow` only after outbox/evaluator acceptance in the
target tenant and install the optional Temporal SDK/worker deployment. Workflow
activities must invoke canonical services; human and external changes arrive as
signals.

## Proactive companion

The authenticated shell mounts a persistent GenuineGigs Companion. It is driven
by persisted `companion_interventions`, not transient chat output. The event
consumer resolves the affected membership, classifies severity deterministically,
coalesces older versions, respects quiet hours and an hourly interruption budget,
and may start a Tier 1 specialist when background preparation is enabled. The
model never decides urgency, recipients, authority, or workflow state.

The default actions are `Do manually`, `Prepare with AI`, and `Why now?`.
Redis pub/sub wakes the browser SSE connection while the database remains the
recovery source of truth. Manual routes remain usable when the companion, Redis,
a worker, a model, or OPA is unavailable.

## Rollout flags

The rollout keys are `agentic_procurement_cycles`, `prepared_work`,
`opa_governance`, `sandbox_execution`, `async_specialists`, `manager_cockpit`,
`autonomy_centre`, `proactive_companion`, `temporal_procurement_workflow`, `tier2_automation`, and
`tier3_automation`. Temporal and Tier 2/3 automation default off. Existing
manual workflows and `/workspace/home` remain available for rollback.
