# Production Pilot, Recovery, and Rollback Runbook

This runbook is an operating checklist, not a certification claim. Customer production write access is prohibited until the customer approves the connection, field mapping, service-account scope, acceptance evidence, and rollback owner.

Use [customer-pilot-acceptance.md](customer-pilot-acceptance.md) as the
customer-specific data-flow, permission, connector, mapping, drill, security,
support, and sign-off record. This runbook describes operation; the acceptance
pack records evidence and authority.

## Release modes

Promote one connection at a time: `disconnected` → `read_only` → `simulation` → `shadow` → customer UAT → `limited_write`. Keep `ERP_LIVE_ENABLED=false` until limited-write acceptance is signed. A connector capability manifest is evidence of implemented behavior, not proof that a customer endpoint supports it.

Before promotion, export the secret-free workspace configuration and connector conformance report; record application image digest, migration head, mapping version, connector adapter version, provider/model/policy version, and approvers. Run the golden Excel scenario and reconcile every import/export count.

## Backup and restore drill

Production PostgreSQL must use encrypted managed backups plus point-in-time recovery. Object versions must be retained for private document buckets. Redis is recoverable queue/cache state, not the source of business truth.

1. Record database backup/PITR identifier, object-store versioning state, migration head, application image digest, RPO target, and drill owner.
2. Restore into an isolated network and new database/buckets. Never overwrite production during a drill.
3. Start with all agent, email, and integration writes disabled.
4. Run `alembic current`, `/health/ready`, tenant/plant isolation tests, business-count reconciliation, document hash sampling, and integration outbox reconciliation.
5. Verify completed outbox events and controlled receipts are not replayed. Retry only pending events through their canonical idempotency keys.
6. Execute the Excel golden demo in dry-run/read-only mode and compare its reconciliation report with the source workbook.
7. Record observed RPO/RTO, mismatches, corrective action owner, and evidence links. A restore is not accepted without read-after-restore business reconciliation.

## Disable and manual continuity drill

Set the affected connection's emergency write disable first; for a global stop set `ERP_LIVE_ENABLED=false`. Set `AGENT_ENABLED=false` for provider/agent incidents. Keep canonical forms, approvals, tasks, private documents, and audit available. Export pending work and assign owners. Do not mark an ERP action successful without external acknowledgement and reconciliation.

For ambiguous network failure, inspect the outbox attempt and external system by semantic idempotency key before retrying. If state cannot be proven, leave it in exception/manual-review status.

## Retention and legal hold

Admin first calls `GET /workspace/retention/preview`. A purge requires CSRF, a new idempotency key, and the literal `ENFORCE_RETENTION`. Place a thread hold through `/workspace/retention/holds` before an investigation or legal preservation event. Enforcement redacts expired private messages, context, tool arguments, events, and checkpoints, and removes expired personal memory. It preserves business records, proposals, mutation receipts, and audit evidence.

Customer policy must define retention periods and hold release authority. The API does not silently infer a legal policy.

## Incident evidence

Preserve correlation IDs, tenant/plant, affected business references, external semantic key, connector/mapping versions, action receipts, outbox attempts, acknowledgement, reconciliation result, and operator timeline. Never copy credentials, raw provider payloads, supplier tokens, or unrestricted document content into tickets.

Critical events include cross-scope disclosure, unauthorized mutation, uncontrolled supplier communication, false external success, duplicate external write, credential exposure, or loss of audit evidence. Disable the narrowest affected capability immediately, notify the customer-designated owner, and add a regression before re-enabling.

## Rollback

Application rollback uses the last accepted immutable image. Database migrations are forward-fix by default; never destructively downgrade production business data. Keep the integration kill switch active during rollback, confirm readiness and migration compatibility, reconcile outbox states, then re-enable read paths before approved writes.

## Pilot acceptance evidence

- Excel-only: golden scenario, idempotent re-import, stale/conflict protection, versioned write-back, read-after-write reconciliation.
- ERP read-only: scoped records, pagination/cursor behavior, mapping, latency, rate limits, deletion semantics, no write credential.
- Shadow/UAT: prepared payload comparison, customer approval, idempotency, timeout-after-commit recovery, acknowledgement, reconciliation.
- Limited write: exactly one approved workflow/capability, least-privilege write identity, emergency disable drill, customer observer, rollback owner.
- Live model: curated evaluation with every external write disabled; record model and policy versions and zero false-success/unauthorized-action results.

Vendor-specific adapters remain unverified until customer-environment contract tests and acceptance evidence are attached. Do not market a manifest stub as production ERP support.
