# V2.1 Manufacturing Operational Recovery

This document describes the implemented product path for
`PLAN_V2_1_RECOVERY_INTELLIGENCE.md`. The Developer Lab is intentionally out of
scope.

## Runtime flow

1. ERP, MES, QMS, CMMS, inventory, supplier, and signed machine-event inputs
   enter their existing connector endpoints. Ingestion receipts provide source
   lineage and idempotency.
2. Normalizers persist canonical production, machine, quality, material,
   maintenance, and supplier facts. Raw machine values remain facts; the
   simulator never declares a GenuineGigs diagnosis or recovery outcome.
3. Detector rules create an `OperationalDeviation`. Eligible deviations open
   exactly one `RecoveryCase` and capture an immutable baseline
   `OperationalStateSnapshot`.
4. Deterministic playbooks generate up to four feasible `RecoveryStrategy`
   records. The ranking service scores value, speed, historical effectiveness,
   success probability, quality, safety, disruption, and uncertainty. Safety
   can veto an option. Gigi explains this evidence but does not invent the
   score.
5. An authorized person selects a strategy. Selecting a non-recommended option
   requires an override reason. The strategy expands into sequenced Tasks and
   Operational Actions with finish-to-start dependencies.
6. Product actions applied to the Northstar simulation are sent to the
   simulator API. The simulator responds with source-system facts such as CMMS
   completion, healthy machine samples, inventory release, supplier commitment,
   or quality measurements. The normal ingestion path processes those facts.
7. Completing tasks starts monitoring; it does not prove recovery. The recovery
   verifier compares a new canonical snapshot with the baseline and target.
8. Verified outcomes store recovered units, time, before/after evidence, side
   effects, attribution, direct cost, and net verified value. The action-outcome
   fingerprint becomes local historical evidence for later rankings.
9. Three comparable recovery occurrences automatically create a suggested
   `ImprovementInvestigation`, separating immediate recovery from permanent
   root-cause elimination.
10. Outbox events are published through the existing SSE channel. Targeted web
    queries refresh Recovery Options, Command Center, Line Workspace, My Work,
    value, quality, maintenance, and material state without a page refresh.

## State semantics

Line state is not represented by one overloaded status. Every snapshot carries
separate execution, performance, machine, material, quality, and recovery
dimensions. In particular, a material risk does not make a physically running
line `BLOCKED_PHYSICALLY`; stale inputs are represented explicitly and prevent
freshness-sensitive strategies from being selected.

## Primary interfaces

- `GET /api/v2/recovery-cases`
- `GET /api/v2/recovery-cases/{case_id}`
- `GET /api/v2/deviations/{deviation_id}/recovery`
- `POST /api/v2/recovery-cases/{case_id}/refresh-options`
- `POST /api/v2/recovery-cases/{case_id}/select`
- `POST /api/v2/recovery-cases/{case_id}/start`
- `POST /api/v2/recovery-cases/{case_id}/verify`
- `POST /api/v2/recovery-cases/{case_id}/abandon`
- `GET /api/v2/recovery-cases/{case_id}/outcome`
- `GET /api/v2/recovery-cases/{case_id}/value`
- `GET /api/v2/recovery-effectiveness`
- `POST /api/v2/improvement-investigations`

All reads and mutations enforce tenant, plant, line, and asset scope in the API.
Financial projections are redacted for roles without financial visibility.

## Background processing and observability

The worker refreshes operational snapshots and observed-outcome verification
every minute. It logs bounded production forecasts every five minutes and later
settles their absolute and percentage error. Recovery case, strategy,
selection, success, failure, override, latency, verified-value, and Gigi
recommendation metrics are exposed with the existing service metrics.

## Verification

The implementation is covered by recovery-domain, state-semantics, API,
authorization, operational flow, plan-contract, performance-budget, simulator,
and migration tests. A clean migration was verified from revision `0001` to
`0056_v2_1_recovery_intelligence` on SQLite. Docker and browser E2E were not run
while implementing this change, in accordance with the workspace owner's
instruction to leave Docker startup under their control.
