# Agent Operations Runbook

## Safe Defaults

Production begins with:

    AGENT_ENABLED=false
    AGENT_ALLOW_DETERMINISTIC_FALLBACK=false
    AGENT_TRACE_EXPORT_ENABLED=false
    ERP_WRITE_MODE=simulation
    ERP_LIVE_ENABLED=false

Agent activation requires deployment enablement, tenant enablement, an enabled member profile, an allowed provider/model, and a valid budget. Workflow access does not depend on activation.

## Required Secrets

Store values in a secret manager or Kubernetes Secret, never tenant JSON or source control:

- DATABASE_URL
- REDIS_URL
- SESSION_SECRET
- GROQ_API_KEY when Groq is active
- Object-storage endpoint credentials
- SMTP and ERP credentials when live integrations are enabled

Rotate session secrets through a planned global logout. Rotate provider keys without changing policies or model allowlists.

## Tenant Rollout

1. Apply Alembic migrations and verify health/ready reports the expected revision.
2. Create or select a fresh workspace and complete plant, reporting-line, and master-data setup.
3. Configure role profiles, budgets, provider/model allowlists, retention, and escalation owners.
4. Upload role playbooks and SOPs; approve only reviewed knowledge versions.
5. Run isolation and mocked-model suites.
6. Run the restricted live-provider evaluation set with no live ERP writes.
7. Enable the tenant and a small profile cohort.
8. Monitor latency, token use, denials, proposal rejection, citation quality, and failed runs.
9. Promote prompt/policy/model versions only after evaluation gates pass.

## Emergency Stop

For one tenant, use the Admin emergency-stop endpoint. For all tenants, set AGENT_ENABLED=false and restart API/agent workers. Do not disable API, PostgreSQL, Redis, or normal workflow workers.

After stopping:

1. Cancel queued/running agent runs.
2. Preserve AgentRun, AgentToolCall, AgentDelegation, AgentProposal, and AuditEvent records.
3. Expire pending proposals if their context or record version may be stale.
4. Identify the shared correlation IDs and affected memberships.
5. Restore only after policy, provider, and evaluation checks pass.

## Provider Outage

- Return a clear unavailable/degraded state; never fabricate a model result.
- Keep queue, records, forms, approvals, and integrations available.
- Retry only bounded transient failures; do not retry invalid output or denied tools.
- Use deterministic fallback only in environments where it is explicitly accepted.
- Circuit-break a failing provider and prevent delegation storms.

## Suspected Scope Leak

1. Activate tenant emergency stop.
2. Revoke affected sessions and cancel runs.
3. Preserve audit and context hashes; restrict trace access.
4. Compare membership, envelope entity allowlist, tool authorization, citations, and returned payload.
5. Treat cross-tenant or private-message exposure as a security incident.
6. Delete leaked private output only after preserving legally required audit hashes and incident evidence.
7. Add the failure to the isolation regression dataset before re-enabling.

## Proposal And Tool Incidents

- A controlled mutation without a confirmed proposal is a release blocker.
- A stale proposal must fail version checks and be regenerated.
- Duplicate confirmation must be absorbed by idempotency.
- Unknown tools and malformed arguments fail closed.
- A model-suggested ID is untrusted until ownership and entity scope are re-authorized.

## Data Retention

- Private agent messages default to 365 days.
- Expired personal memory and retired knowledge chunks are removed by retention jobs.
- Business decisions, proposal confirmations, citations, integration effects, and audit hashes follow the longer compliance policy.
- Account deletion removes eligible private content while retaining legally required audit evidence.
- Trace export remains off unless a redacted self-hosted destination has been approved.

## Backup And Recovery

- Enable PostgreSQL point-in-time recovery and test restore procedures.
- Version and retain approved knowledge source objects in S3-compatible storage.
- Back up encryption key references separately from encrypted data.
- Restore PostgreSQL, object storage, Redis queues, then reconcile outbox and agent run states.
- Never replay completed controlled effects solely from an agent message; use idempotency and outbox state.

## Health Signals

Alert on:

- API readiness or migration mismatch.
- Agent queue age and failed/cancelled run rate.
- Provider timeout, circuit-open, and malformed-output rates.
- Tool denials, proposal expiry/rejection, and authorization anomalies.
- Token/cost budget exhaustion.
- Delegation depth/loop limit events and overdue handoffs.
- Embedding/knowledge ingestion failure.
- Outbox retry age and ERP reconciliation mismatch.

## Helm Release

The chart is in deploy/helm/genuinegigs. Create the configured Kubernetes Secret before install. The web image must be built for the public API URL used by browsers.

    helm lint deploy/helm/genuinegigs
    helm upgrade --install genuinegigs deploy/helm/genuinegigs -f production-values.yaml

Keep agents disabled for the first production release, verify migration/readiness and ordinary workflows, then enable an evaluated tenant cohort.
