# Current runtime truth

Verified on 2026-07-24 against the checked-in source and executable service
tests. This document distinguishes a live path from a declared interface.

## Assistant request path

The live path is:

`POST /agent/threads/{thread_id}/messages`
→ `agent_service.run_message`
→ membership, plant, profile, thread, attachment, and selected-page
authorization
→ compact scoped context, typed thread state, recent entities, and server-side
catalog candidates
→ Groq tool selection, a direct UI capability action, or deterministic
provider-outage continuation
→ `IntentEnvelope` validation against the role-scoped `CAPABILITY_REGISTRY`
→ grounded argument merge
→ `agent_runtime.run_bounded_tool_loop`
→ registered capability adapter
→ canonical service or controlled proposal
→ persisted action receipt for a mutation
→ grounded-response validation
→ private assistant message, events, checkpoints, metrics, and audit.

The bounded loop is active. It permits several authorized reads/resolutions,
but terminates after one business mutation or one controlled proposal. It
enforces decision, time, read, candidate, total-tool, mutation, and proposal
budgets. The model is never given SQL, shell, arbitrary HTTP, filesystem,
database, storage, or ERP credentials.

Groq interprets language and chooses from the employee's authorized capability
set. Server services resolve exact business numbers and safe “latest”/recent
references, authorize the employee, validate business rules, calculate values,
persist canonical records, and issue receipts. An `agent_runs.provider = groq`
row proves a provider call occurred; it does not, by itself, prove a business
mutation succeeded. That requires the matching persisted record and action
receipt.

Provider failure does not authorize a weaker mutation path. When configured,
deterministic limited mode can continue only an already unambiguous supported
request; manual workbenches remain available. Unknown or unauthorized model
capabilities are rejected or safely reduced to a read-only contextual answer.

## State truth

`AgentThreadStateV2`, `load_thread_state`, and `persist_thread_state` are the
validated request-boundary gateway. State records the active goal/intent,
draft fields with provenance, selected context, current work item, recent
entities, bounded attachments, pending confirmation/proposal, last successful
receipt, blockers, candidate resolution, and timestamps.

Some compatibility dictionary construction remains inside the large
`agent_service.py` dispatcher while extraction into smaller adapter modules is
unfinished. The live message boundary validates and persists that data through
the V2 schema before completing the request. Legacy `AgentTurnDecision`
definitions remain for provider compatibility and old tests; registered live
capabilities execute as `IntentEnvelope` tools.

## Capability truth

`CAPABILITY_REGISTRY` is authoritative for role exposure and validation. Every
declared capability has a registered executable adapter and a concrete branch
to a canonical service or controlled proposal. The current registry covers
work context/tasks, material resolution and requests, requirements, RFQs,
quotation attachments and evidence review, currency evidence, comparison,
approval, negotiation, award/PO actions, acknowledgement/delivery reads,
Gate/Stores/Quality, supplier return/replacement, invoice matching and finance
handoff, Excel exchange, delegation/team reporting, compliance/performance,
policy, risks, readiness, and management summaries.

The registry is not authority by itself. Canonical services repeat tenant,
plant, role/reporting-scope, record-state, idempotency, and version checks.
External, immutable, commercial, inventory, quality, finance, and ERP
consequences use proposals/approvals or explicit business confirmations.

## Manual and assistant convergence

Manual pages and assistant tools call the same procurement services and operate
on the same records. The RFQ workbench presents:

`Request details → Suppliers → Review → Send → Track responses`

and exposes one dominant next consequence per state. Similar state-aware
workbenches exist for quotation evidence, comparison/approval, negotiation,
PO, supplier acknowledgement, inbound, Stores, Quality, exceptions, invoices,
and integrations. Assistant record cards deep-link to those canonical
workbenches.

The main workspace includes attention, prepared work, personal tasks, waiting
on others, authorized team follow-ups, recent activity, and the persistent
role assistant. The final Playwright run exercises the role workspaces and
assistant at desktop, tablet, and mobile sizes, checks page overflow, and
captures the curated client-demo evidence set.

## Spreadsheet integration truth

Excel/CSV is the complete test external system, not a one-time item upload. The
implementation supports XLSX, CSV, and ZIP-of-CSV discovery; multiple sheets;
versioned mapping profiles and allowlisted transforms; dry-run preview;
required-field and business validation; row/cell lineage; row-level error and
reconciliation reports; stable external keys; idempotent re-import;
incremental updates; duplicate/formula protection; stale local-version
conflicts; canonical transaction imports; versioned export; read-after-write
verification; and round-trip reconciliation.

The checked-in fixture package includes organization, reporting, materials,
specifications, suppliers, contacts, capabilities, requirements, open POs,
receipts, Quality, invoices, invoice lines, and payment observations, plus
invalid, duplicate, partial, hostile-formula, and stale variants.

`tests/test_golden_procurement_demo.py` creates a clean workspace from the
fixture and executes sourcing through finance handoff and closure without
manual database inserts or ERP credentials. It proves idempotent round-trip
import and protection of newer operational state from a stale workbook.

## Connector and ERP truth

The provider-neutral connector contract implements connection tests,
capability manifests, secret references, pull cursors, prepare/validate/approve
write, payload hashing, idempotency, dispatch, error classification,
ambiguous-commit recovery, read-after-write verification, reconciliation,
health, capability reporting, modes, and an emergency write disable.

Contract-tested reference adapters exist for Excel/CSV, generic REST/OpenAPI,
generic OData, SFTP/file exchange, generic SOAP, middleware/iPaaS, and a private
network bridge. Oracle Fusion, SAP S/4HANA, Dynamics 365, and Odoo expose honest
unverified capability boundaries. They are not customer-verified production
connectors without customer credentials, mappings, sandbox/UAT evidence, and
acceptance.

ERP writes never update ERP database tables. The controlled path is:

authorized workflow action
→ validation
→ approval where required
→ integration outbox with idempotency key and payload hash
→ connector attempt
→ external acknowledgement/reference
→ read-after-write verification
→ reconciliation
→ audit and notification.

“Posted to ERP” is not a valid user-facing success state until acknowledgement
and required reconciliation evidence exist.

## Supplier-channel truth

The tokenized supplier portal supports RFQ and PO contexts. Suppliers can
submit partial/multi-line quotation revisions, no-bid responses,
clarifications, PO acknowledgements/change requests/rejections, ASN/delivery
details, immutable schedule updates, evidence/certificates, and invoices.
Inbound email converges on the same canonical quotation, invoice,
acknowledgement, ASN, and document-linking services. Delivery, bounce, failure,
and approved-pending-send states are persisted.

A production mailbox/email provider remains environment-specific. The checked
in implementation and tests prove canonical ingestion and simulation, not a
specific customer's DNS, mailbox, or deliverability configuration.

## Verification truth and remaining environment gates

Final verification on 2026-07-24 produced:

- complete API suite: 331 passed, with one upstream LangGraph deprecation
  warning;
- deterministic natural-language evaluation: 151 passed;
- Playwright desktop/tablet/mobile suite: 43 passed and two intentionally
  skipped duplicate screenshot-project cases;
- TypeScript typecheck: passed;
- optimized Next.js production build: passed with 27 routes;
- OpenAPI contract: current at `19529b40f71b`;
- fresh SQLite migration from an empty database: passed through
  `0035_scoped_public_ids`;
- incremental migration from revision 0031: passed through the same head.

The WSL image did not contain Chromium's NSS/NSPR shared libraries. For local
verification only, the Debian packages were downloaded and extracted under
`/tmp`, and Playwright was run with that private library directory in
`LD_LIBRARY_PATH`. No system package or repository dependency was changed.

Docker Desktop was reachable through its Windows CLI even though the `docker`
shim was not integrated into WSL. The complete Compose stack was built and
started. PostgreSQL, Redis, MinIO, Mailpit, API, and web health checks passed;
the migration and seed jobs exited successfully; the worker and scheduler
started without errors; API readiness reported database, migration, object
storage, Redis, and provider checks healthy.

The first PostgreSQL migration run exposed Alembic's historical 32-character
`version_num` limit at revision `0017_external_owned_purchase_orders`.
Revision 0017 now widens that Alembic control column before Alembic records the
long revision ID. The real persisted database then upgraded through
`0035_scoped_public_ids`.

An isolated PostgreSQL backup/restore drill also passed: source and restored
databases both reconciled to 10 users, 27 requirements, and migration
`0035_scoped_public_ids`. A second empty PostgreSQL database migrated from
revision 0001 through head successfully.

Compose now creates the documents, quarantine, and evidence buckets explicitly,
keeps all three private, and enables object versioning on each. The recovery
drill wrote two versions of one document, copied the current version into the
evidence recovery location, read it back byte-for-byte, and listed both source
version IDs.

The curated live-provider scorecard was run after the final LangChain/Groq
upgrade with external writes disabled. Groq selected the expected authorized
capability in 18 of 20 scenarios (90%), meeting the 85% pilot threshold. One
scenario was safely handled by deterministic fallback after a provider 429;
that scenario was counted as a failure rather than silently credited.

Production dependency audits are also current: `npm audit --omit=dev` reports
zero vulnerabilities, `pip-audit` reports no known third-party vulnerabilities,
and `pip check` reports no broken Python requirements. The local editable
`genuinegigs-api` distribution is correctly excluded from the public PyPI
advisory lookup.
