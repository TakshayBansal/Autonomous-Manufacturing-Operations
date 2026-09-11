# Manufacturing Agent OS V1: Procurement Agent Module

## Summary
- Build the first real product slice of a larger **Manufacturing Agent OS**, starting with purchase-side procurement because it is frequent, manual, and easy for manufacturers to understand.
- V1 workflow: `material need -> RFQ -> quotations -> comparison -> negotiation -> PO draft -> supplier acknowledgement -> gate/store/inspection -> exception closure`.
- Oracle/SAP/Tally remain the customer's ERP system of record. Our product becomes the execution, agent, task, evidence, approval, and exception layer above ERP.
- V1 release target is a production-minded **design partner pilot**, using tenant-scoped baseline data, simulated ERP actions, and import/export-ready integration boundaries.
- Core database is **PostgreSQL**; supporting infrastructure is **Redis** for queues/sessions/rate limits and **MinIO/S3-compatible storage** for uploaded documents.

## Implementation Plan
- Create a greenfield monorepo in `C:\Users\Takshay\Desktop\Important\GenuineGigs` with:
  - `Next.js` frontend for role-based workbenches and control towers.
  - `FastAPI` backend for workflow APIs, agent actions, integrations, document processing, and audit.
  - `PostgreSQL` for users, org structure, procurement records, cases, tasks, approvals, audit, and integration logs.
  - `Redis` for async jobs, rate limits, and session support.
  - `MinIO` for PDFs, Excel files, scanned quotations, attachments, and extracted evidence.
  - Docker Compose for local development and repeatable local workspace startup.
- Build the product foundation first:
  - Tenant, company, plant, department, role, user, and reporting hierarchy.
  - Role-bound agents mapped to actual employees and managers.
  - Task engine for approvals, follow-ups, pending work, and agent-created actions.
  - Case engine for business issues with owner, severity, timeline, evidence, and linked records.
  - Append-only audit ledger for user actions, agent suggestions, uploads, approvals, and simulated integration events.
  - Simulated outbox for RFQ messages, negotiation messages, ERP postings, and supplier follow-ups.
- Implement initial roles:
  - Plant Manager: sees operational risk, ageing tasks, supplier issues, department bottlenecks.
  - Purchase Manager: approves RFQs, awards, overrides, and PO drafts.
  - Purchase Executive: creates RFQs, verifies quotations, compares vendors, negotiates, follows up.
  - Store Manager: records/reviews receipt, shortage, excess, and damage.
  - Quality Inspector: records inspection, rejection, quality hold, and certificate issues.
  - Admin: manages users, roles, baseline data, imports, and workspace reset.

## Procurement Module
- Build one complete purchase case:
  - Create purchase requirement manually or from material shortage.
  - Generate RFQ from requirement lines, item specs, need-by date, plant, and approved supplier shortlist.
  - Simulate RFQ publishing through outbox instead of real email.
  - Upload supplier quotations in PDF, scanned PDF/image, and XLSX formats.
  - Extract supplier, quote number, date, validity, item, quantity, UOM, unit price, GST/tax, freight, packaging, MOQ, lead time, promised date, payment terms, deviations, certificates, and notes.
  - Show source evidence, confidence, parser/model version, and verification status for extracted fields.
  - Require buyer verification for low-confidence or commercially significant fields.
  - Compare vendors using deterministic landed cost, delivery compliance, MOQ, technical compliance, supplier quality score, and delivery history.
  - Disqualify blocked suppliers, missing mandatory certificates, late mandatory delivery, unverified prices, and unacceptable deviations.
  - Add negotiation journal with original quote, target, drafted message, approval, counteroffer, and revised terms.
  - Award each RFQ line to one supplier with Purchase Manager approval.
  - Generate PO draft grouped by supplier/site/currency/plant/commercial terms.
  - Show Oracle/SAP-ready PO field mapping and simulated posting correlation ID.
  - Track supplier acknowledgement, ASN, gate entry, store receipt, inspection, quality hold, rejection, shortage, and closure.
- Initialize the main production pilot workflow:
  - Material shortage triggers requirement.
  - RFQ goes to three suppliers.
  - Cheapest quote is late or missing a certificate.
  - Agent recommends a safer supplier with visible reasoning.
  - Negotiation improves price.
  - PO draft is approved.
  - Gate/store/quality events reveal shortage or rejection.
  - Exception case remains visible to purchasing and plant management.

## Agent And UI Design
- Treat agents as role-bound coworkers inside the virtual org structure, not as generic chatbots.
- Purchasing Agent can draft RFQs/messages, suggest suppliers, extract quotes, explain comparison tradeoffs, suggest negotiation points, and create follow-up tasks.
- Purchasing Agent cannot approve RFQs, approve awards, create real POs, update inventory, change supplier master data, or close cases without authorized human action.
- Plant Manager Agent can summarize open risks, overdue tasks, supplier ageing, department blockers, and ask role agents for updates through internal tasks.
- Frontend must feel like an industrial operations console:
  - Dark graphite navigation, warm off-white workspace, steel grey borders, safety orange for action, red for critical, green for complete.
  - `IBM Plex Sans` for UI and `IBM Plex Mono` for RFQ/PO numbers, timestamps, quantities, and audit hashes.
  - Dense tables, ledgers, timelines, task queues, evidence panels, approval queues, and calculation breakdowns.
  - No generic AI landing page, glowing chatbot, gradient hero, decorative blobs, oversized cards, or vague "AI magic" copy.
  - First screen after login is a real workbench/control tower.
  - Every screen shows ownership, due date, ageing, status, source evidence, ERP reference, approval state, and next action where relevant.
- Main screens:
  - Sign-in, Plant Manager Control Tower, Purchase Executive Workbench, Purchase Manager Approval Centre, RFQ Builder, Quotation Inbox, Quote Evidence Review, Bid Comparison, Negotiation Journal, Award Approval, PO Draft View, Inbound Tracking, Store Receipt Workspace, Quality Inspection Workspace, Case Register, Simulated Outbox, Integration Centre, Audit Ledger, Workspace Reset.

## Security And Industrial Readiness
- Identity and access:
  - Argon2id password hashing, HttpOnly database-backed sessions, CSRF protection, login rate limiting, lockout, and audit events.
  - Role checks at route, service, and query levels.
  - Tenant and plant filtering on every data access.
- Data and document security:
  - Tenant-scoped baseline or explicitly anonymized data only for V1 pilot.
  - Private object storage and short-lived authorized download URLs.
  - Upload quarantine before parsing.
  - MIME/signature validation, size limits, encrypted PDF rejection, macro workbook rejection, formula-injection handling, corrupt file rejection, and OCR/parser timeouts.
  - Logs redact sessions, secrets, documents, prompts, and model outputs.
- Action safety:
  - No real ERP write-back, real email, WhatsApp sending, payment action, gate admission, or inventory mutation in V1.
  - Simulated external actions are clearly labelled in UI and audit records.
  - Approval decisions are immutable after submission.
  - Idempotency keys are used for simulated integration events and future real adapters.
- AI safety:
  - AI outputs are schema-validated before storage.
  - AI failures fall back to deterministic templates and manual review.
  - Imported document text cannot alter permissions, prompts, workflow rules, or configuration.
  - Store provider/model/version for every extraction, summary, recommendation, or draft.

## Interfaces And Integration
- Core domain models:
  - `Tenant`, `Plant`, `Department`, `Role`, `User`, `AgentProfile`, `ReportingLine`.
  - `Task`, `Case`, `AuditEvent`, `Notification`, `OutboxMessage`.
  - `Supplier`, `SupplierSite`, `SupplierContact`, `Item`, `Uom`, `ItemSpecification`, `SupplierItemCapability`.
  - `PurchaseRequirement`, `RFQ`, `RFQLine`, `SupplierQuote`, `QuoteLine`, `QuoteExtractionRun`.
  - `BidComparison`, `NegotiationRound`, `AwardDecision`, `PODraft`.
  - `SupplierAcknowledgement`, `ASN`, `GateEntry`, `StoreReceipt`, `InspectionResult`, `InventoryImpact`.
- API groups:
  - `/auth`, `/org`, `/tasks`, `/cases`, `/audit`.
  - `/procurement/requirements`, `/procurement/rfqs`, `/procurement/quotes`, `/procurement/comparisons`, `/procurement/negotiations`, `/procurement/awards`, `/procurement/po-drafts`.
  - `/inbound/gate-entries`, `/inbound/receipts`, `/inbound/inspections`.
  - `/agents/actions` for role-bound summaries, drafts, recommendations, extraction requests, and task creation.
  - `/integrations/imports`, `/integrations/outbox`, `/integrations/events`.
- ERP boundary:
  - Define an `ERPAdapter` interface for master data import, open PO import, receipt import, inspection import, and simulated PO posting.
  - V1 implementation uses baseline data, CSV imports, and Oracle/SAP-like payloads.
  - Future real Oracle/SAP connectors should plug into the adapter without changing procurement workflow logic.

## Build Sequence
- Week 1: product foundation
  - Monorepo, Docker Compose, database migrations, baseline data, auth, RBAC, org model, audit ledger, task/case engine, and industrial UI shell.
- Week 2: procurement workflow
  - Requirements, RFQ builder, supplier shortlist, simulated RFQ publish, quotation inbox, document upload, extraction pipeline, and buyer verification.
- Week 3: decision workflow
  - Landed-cost engine, compliance rules, bid comparison, negotiation journal, award approvals, PO drafts, and simulated ERP posting logs.
- Week 4: inbound workflow and control tower
  - Supplier acknowledgement, ASN, gate entry, store receipt, inspection, inventory impact, procurement exceptions, and Plant Manager visibility.
- Week 5: hardening
  - Security tests, parser failure tests, role/tenant isolation tests, audit completeness, accessibility, visual QA, workspace reset, backup/restore notes, and deployment docs.

## Test Plan
- Unit tests:
  - Landed cost, GST/tax separation, scoring, hard disqualification, state transitions, approval rules, usable inventory, and exception creation.
- API tests:
  - Auth, RBAC, tenant isolation, role permissions, CSRF, rate limits, idempotency, optimistic locking, and audit creation.
- Document tests:
  - PDF, scanned PDF/image, XLSX, encrypted PDF, corrupt file, oversized file, MIME spoofing, macro workbook, formula injection, and OCR timeout.
- Workflow tests:
  - Requirement to RFQ, RFQ to quote verification, quote comparison to negotiation, award to PO draft, PO acknowledgement to ASN, gate entry to receipt, receipt to inspection, and inspection rejection/hold to exception case.
- Agent tests:
  - Agent cannot access unrelated tenant/plant data.
  - Agent cannot approve, post, close, or mutate restricted entities.
  - Agent suggestions are recorded with model/provider/version.
  - AI-disabled mode still completes the baseline workflow.
- E2E and visual tests:
  - Purchase Executive completes RFQ and comparison.
  - Purchase Manager approves award and PO draft.
  - Store Manager records receipt but cannot inspect.
  - Quality Inspector records inspection but cannot receive.
  - Plant Manager sees end-to-end case history and overdue risk.
  - Screens pass desktop and responsive checks for density, readability, spacing, and industrial seriousness.

## Acceptance Criteria
- Fresh setup starts the full product locally with baseline manufacturing data.
- Baseline procurement workflow completes in 10-15 minutes without external credentials.
- All important mutations create audit records.
- Low-confidence quote fields cannot enter comparison until verified.
- Buyer cannot approve award or PO draft.
- Store Manager cannot inspect material.
- Quality Inspector cannot record store receipt.
- Accepted usable inventory cannot exceed inspected and accepted quantity.
- Simulated ERP/email actions are clearly labelled and stored in outbox logs.
- Product remains usable when AI provider is disabled.
- Plant Manager sees the full timeline from material need to receipt/inspection exception.
- UI feels like a coherent industrial operations product that could sit beside Oracle/SAP, not a generic AI-generated website.

## Assumptions
- Implementation starts in `C:\Users\Takshay\Desktop\Important\GenuineGigs`, currently empty and not a git repo.
- Current sandbox writable root is `C:\Users\Takshay\Documents\GenuineGigs`, so implementation in the Desktop folder may require workspace permission adjustment or escalated file-write approval.
- V1 uses simulated Oracle/SAP-style data and CSV imports, not live ERP credentials.
- V1 is optimized for a design partner pilot but uses production-minded security, audit, workflow, and integration boundaries.
- Initial module is purchase-side procurement for manufacturing, not generic procurement and not sales-side RFQ.
- Multi-agent org structure is part of the foundation, but only procurement, store, quality, purchase manager, and plant manager roles are active in V1.


