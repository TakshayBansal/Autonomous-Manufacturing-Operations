# PLAN_LATEST completion audit

Audit date: 2026-07-24

This document maps the implementation contract to current executable evidence.
“Implemented” means the checked-in runtime and broad tests prove the behavior.
“External gate” means the repository boundary exists but the required
environment or customer acceptance has not been executed. It is not a product
success claim.

## Phase status

| Phase | Status | Authoritative evidence |
| --- | --- | --- |
| 0 — factual baseline | Implemented | `current-runtime-truth.md`, literal transcript regressions, runtime trace, and screenshots. |
| 1 — typed state and resolution | Implemented | `agent_state.py`, `agent_resolution.py`, and cross-turn/topic/entity tests. |
| 2 — typed adapters | Implemented | Registry completeness and authorization tests; every enabled capability resolves to an executable adapter. |
| 3 — bounded runtime | Implemented | Live `run_message` calls `run_bounded_tool_loop`; budget and failure tests pass. |
| 4 — procurement agent skills | Implemented | Requirement through invoice/quality capabilities, proposals, receipts, API, and browser coverage. |
| 5 — manual workbenches | Implemented | State-driven requirement, RFQ, quote, comparison, approval, PO, inbound, Quality, exception, and invoice screens. |
| 6 — assistant-first shell | Implemented | Role shell, responsive assistant, badges, business cards, axe critical checks, and five viewport captures. |
| 7 — coordination | Implemented | Semantic task idempotency, scoped follow-ups, alerts, briefs, manager metrics, and citations. |
| 8 — Excel/CSV external system | Implemented | Spreadsheet contracts, hostile-file tests, golden lifecycle, conflict, versioned export, and reconciliation. |
| 9 — connector platform | Implemented for tested protocols | Common SDK and conformance tests for Excel/file, REST, OData, SOAP, SFTP, middleware, and private bridge simulators. |
| 10 — vendor/email/portal boundaries | Implemented to tested scope | Canonical email simulation and supplier portal pass; vendor manifests remain customer-validation-required. |
| 11 — remaining procurement domain | Implemented | Revisions, split awards, currency, policy, compliance, PO changes, partial delivery, replacement, CAPA, and invoice handoff. |
| 12 — knowledge/analytics/configuration | Implemented | Approved knowledge, sourced briefs, readiness/config export, supplier metrics, retention, and no employee score. |
| 13 — controlled pilot release | Locally verified; customer acceptance pending | Native security/API/browser/provider gates, Compose health, PostgreSQL restore, versioned object recovery, production runbook, and customer acceptance pack pass local review; external image scan and customer-environment acceptance remain external gates. |

## Final definition-of-done evidence

### Agent

- The 331-test API suite covers the bounded loop, role-scoped adapters, one
  mutation maximum, proposals, state migration, entity resolution,
  attachments, provider fallback, and mutation proof.
- Deterministic natural-language corpus: 151 scenarios.
- Live Groq selection: 18/20 (90%) after the final provider-library upgrade,
  with external writes disabled.

### Manual product and coordination

- Playwright against the running Compose stack: 43 passed across desktop,
  tablet, and mobile; two screenshot cases are intentionally skipped outside
  the canonical capture project. The affected tablet agent conversation also
  passed three consecutive focused repetitions.
- Axe critical violations: zero for all seven demo roles.
- Screenshot evidence exists at 1440×900, 1280×800, 1024×768, 768×1024, and
  390×844 under `test-results/client-demo/`.
- Task, notification, follow-up, daily brief, and manager-source regressions
  are included in the complete API suite.

### Integration and business lifecycle

- The golden test bootstraps a clean workspace from fixtures and executes
  sourcing, supplier response, verification, comparison, approval, PO,
  acknowledgement, delivery, Gate, Stores, Quality rejection,
  replacement/reinspection, invoice match, finance handoff, export,
  reconciliation, idempotent re-import, and stale conflict protection.
- Connector conformance covers capability truth, modes, idempotency,
  timeout-after-commit recovery, stale versions, emergency disable,
  read-after-write, and reconciliation.
- Oracle, SAP, Dynamics, and Odoo remain manifest-only,
  customer-validation-required boundaries. They expose no untested live
  capability.

### Security and contract gates

- API: 331 passed.
- Fresh and incremental migration: `0035_scoped_public_ids`.
- OpenAPI: current at `19529b40f71b`.
- TypeScript and optimized web build: pass, 27 routes.
- Production npm audit: zero vulnerabilities.
- Python audit: no known third-party vulnerabilities; dependency integrity
  passes.
- Isolation, forged IDs, unauthorized capabilities, hostile files, formula
  injection, prompt injection, duplicate writes, and ambiguous timeout
  recovery are covered by automated suites.

## External/customer acceptance evidence still required

1. Docker Compose builds and health pass, and PostgreSQL backup/restore
   reconciliation passes. Docker Scout image scanning is not run because it
   sends locally built image package metadata to Docker's external service and
   requires explicit user authorization.
2. The local MinIO versioned-object recovery drill passes. Customer managed
   storage policy, cross-region recovery, RPO, and RTO acceptance still require
   the customer's production-equivalent environment.
3. No customer ERP credentials or sandbox are available. Read-only, shadow,
   UAT, and limited-write customer acceptance remain external work. Vendor
   capabilities stay disabled and unverified.
4. No production SMTP/IMAP domain, customer DNS, or mailbox is available.
   Canonical simulation is tested; real deliverability is not claimed.
5. External penetration testing and customer-specific privacy/legal review are
   operational acceptance activities, not claims established by repository
   tests.

The required customer data-flow inventory, role/supplier-token permission
matrix, connector capability table, mapping evidence checklist, staged pilot
criteria, incident drills, penetration-test rules of engagement, support/SLA
ownership, and sign-off fields are provided in
`docs/runbooks/customer-pilot-acceptance.md`.

All repository-controlled implementation and local release gates are now
complete. The items above require permission to transmit scan metadata or a
customer-controlled production-equivalent environment. None should be
converted into a passing production claim by using mocks or documentation
alone.
