# V1 And Role-Agent Acceptance Criteria

## Workflow Baseline

- Fresh setup starts the web app, API, workers, storage, mail sink, and PostgreSQL through Docker Compose.
- Demo keeps the reference procurement journey; fresh workspaces contain no sample transactional records.
- The non-AI requirement-to-receipt workflow remains usable when agents or providers are unavailable.
- Low-confidence or commercially significant quotation fields require buyer verification.
- Purchase Executive cannot approve awards or POs; Store cannot inspect; Quality cannot record store receipt.
- Important mutations create audit records and external effects are idempotent and reconcilable.
- Procurement V2 is tenant gated and follows Requirement -> RFQ -> quote verification -> comparison -> dual approval -> PO -> Gate -> Store -> Quality.
- RFQ publication is Purchase Executive authority; quotation verification and comparison are Purchase Manager authority.
- The same immutable comparison version requires named Plant Manager and Purchase Executive approvals.
- Final PO creation does not silently email the supplier or post to ERP.
- Draft and final PDF artifacts are visually distinct, checksummed, versioned, and tenant scoped.

## Task And UI

- My Work is every role's landing page and identifies assigned work, delegated work, next action, owner, blocker, due date, and expected result.
- Work-item links navigate without mutation.
- Lifecycle stages pair plain-language and technical labels.
- Long identifiers, structured ERP mappings, agent messages, and citations remain contained at desktop, tablet, and mobile widths.
- Keyboard focus, dialogs, expandable data, streaming announcements, disabled states, and errors are accessible.

## Identity And Workspace

- Accounts can hold multiple isolated memberships and switch workspaces without stale cached context.
- Invitations, verification, password reset, TOTP MFA, backup recovery, active-session listing, and revocation are audited.
- Existing V1 databases migrate forward without deleting operational data and old sessions are safely re-scoped.

## Role Agents

- Each member has private threads and runs, while canonical Tasks carry assignment, delegation, follow-up, blocker, review, and completion state.
- An employee agent cannot read, search, cite, infer, or mutate unrelated employee work or private conversation.
- A manager receives formal descendant status without private messages.
- Forged work-item, entity, delegation, membership, and tool IDs fail closed.
- Peer agents cannot assign work; manager delegation stays inside the reporting hierarchy.
- Controlled actions pause as proposals and require the correct human authority and current record version.
- Context, model calls, tools, denials, delegations, proposals, confirmations, failures, and external effects share audit correlation.
- Bounded runs persist reconnectable events and database checkpoints; proposal confirmation resumes the linked run and records a verified receipt.
- Contextual RFQ and comparison preparation uses the same canonical domain services as the manual workbenches.
- Prompt injection, malformed output, timeout, cancellation, duplicate delivery, provider outage, and handoff limits fail safely.

## Release Scenario

1. A customer creates a fresh workspace and configures the plant and employees.
2. The Plant Manager creates one canonical multi-line purchase requirement.
3. Governed delegation creates named Purchase Executive Task work without an Objective duplicate.
4. The Purchase Executive sees only assigned work and asks the role agent for help.
5. The agent explains missing data, cites approved sources, and prepares the RFQ workflow.
6. Purchase Manager extracts quotations and submits a frozen supplier comparison.
7. Plant Manager and Purchase Executive each approve the same comparison version.
8. Purchase Manager confirms the final PO; supplier email and ERP posting remain separate.
9. Gate, Store, and Quality receive named dependent work in that order.
10. Plant Manager receives cited commitments and blockers without private transcripts.
11. Runs, handoffs, proposals, decisions, and external effects are traceable.
12. The journey remains operable with AGENT_ENABLED false.
