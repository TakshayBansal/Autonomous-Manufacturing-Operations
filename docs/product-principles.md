# Product Principles

## Product Identity

GenuineGigs is a Manufacturing Role-Agent Operating System. Procurement is the first complete lifecycle, while platform boundaries must also support store, quality, production, maintenance, dispatch, finance, and plant management.

## Task-First Work

- Every role starts with the clearest answer to: What do I need to do next?
- A work item explains why it matters, required evidence, expected result, named owner, due date, blocker, and safe destination.
- Opening work is navigation only. It never approves, publishes, posts, dispatches, updates inventory, or closes a case.
- Consequential actions remain in focused workflow panels and require explicit authorized human confirmation.
- Navigation separates My work from Process records; empty states identify the role or event being awaited.

## Industrial Language And UI

- Pair plain language with the official term at decision points, such as Ask suppliers for prices (RFQ).
- Preserve exact identifiers, statuses, integration fields, and technical names in details, audit, and exports.
- Every record answers: What is this? Why is it here? What happens next? Who owns the next step?
- Use dense, restrained workbenches, ledgers, timelines, approval views, and exception registers.
- Avoid decorative AI visuals, hero pages, gradients, floating global chatbots, and vague automation copy.
- Tables, forms, status text, citations, and action rows must remain contained at desktop, tablet, and mobile widths.

## Role-Agent Standard

- Every agent belongs to one workspace membership and inherits no authority from its model provider.
- Threads are personal, work-item, objective, or team-follow-up scoped.
- Agents may explain, summarize, extract, compare, draft, prefill, request updates, and create governed low-risk work.
- Agents cannot approve, publish, post to ERP, update inventory, alter master data or permissions, impersonate people, or close exceptions.
- Controlled actions are expiring proposals reviewed by the human who already owns the required authority.
- Results identify sources, work prepared, missing information, expected effect, and required human decision.
- Prompt text never replaces deterministic workflow, permission, idempotency, concurrency, or audit rules.

## Context And Privacy

- A work item is the shared context boundary between a person and an agent.
- Context is assembled by the server from tenant, plant, membership, role, ownership, reporting scope, and explicit entity links.
- Employee agents see assigned work, linked records, approved shared knowledge, private memory, and addressed delegations only.
- Manager agents see formal reporting-line status and cited work records, never private employee-agent transcripts.
- Knowledge is ACL-filtered before semantic ranking; similarity cannot grant access.
- Documents are untrusted content and cannot modify system policy or tool permissions.

## Agent Coordination

- Manager agents may delegate down validated reporting lines.
- Peer agents may send typed collaboration requests but cannot assign work or mutate another employee's task.
- Delegations carry only objective, outcome, references, constraints, due date, and response schema.
- Private history and unrelated records are never forwarded.
- Handoff depth, delegation depth, budgets, retries, loops, cancellation, and escalation are bounded and audited.

## Workspace And Identity

- Account identity is separate from workspace membership.
- One account may join isolated demo, fresh, multi-plant, or customer workspaces.
- Demo contains reference data; fresh contains no transactional examples. There is no destructive mode toggle.
- Invitations, verified email, password recovery, TOTP MFA, backup recovery, workspace switching, and session revocation are security-sensitive audited flows.

## ERP And External Effects

- ERP remains the system of record.
- Connectors implement provider adapters without changing workflow authority.
- External writes require approval, idempotency, payload hashes, bounded retries, audit, and reconciliation.
- Agent shutdown and provider outage never block the non-AI workflow.
- Simulation and live-write controls remain independent from agent feature flags.

## Procurement V2 Authority

- Plant Manager and Purchase Executive may create a quantified material requirement.
- Purchase Executive owns RFQ preparation, preview, publication, and supplier dispatch.
- Purchase Manager owns quotation intake, extraction review, comparison, optional negotiation, and final PO confirmation.
- Plant Manager and the named Purchase Executive independently approve the same immutable comparison version.
- Either rejection invalidates the other pending decision and returns a versioned revision task to Purchase Manager.
- Gate Operator records vehicle and challan arrival against an issued PO; Store records quantity receipt; Quality records disposition.
- Draft PDF previews never publish or send. Final RFQ, comparison, and PO PDFs are immutable, versioned, checksummed, and tenant scoped.
- PO creation, supplier email preparation, email dispatch, ERP approval, and ERP dispatch are separate audited actions.
- Material and supplier master data require authorized humans. Agents may prepare requests but never approve master data.

## Market-Readiness

- Agent availability requires deployment, tenant, and profile enablement, with an emergency stop.
- Model/provider selection never changes tool permissions.
- Prompts, policies, model profiles, budgets, and entitlements are versioned and tenant-gated.
- Product audit is authoritative; external trace export is optional and redacted.
- Private conversations expire by policy while approvals, citations, business decisions, and audit hashes follow longer retention.
- Release gates require isolation, refusal, citation, workflow, accessibility, visual, migration, outage, and load tests.
