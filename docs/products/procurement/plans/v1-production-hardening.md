# Production Procurement OS Hardening Plan

## Summary
Build the first sellable milestone as a production-grade **procure-to-receive workflow**: RFQ generation, supplier quotation intake, comparison, negotiation, award approval, PO draft/posting, supplier acknowledgement, ASN/gate entry, store receipt, optional inspection, exception closure, and Plant Manager visibility. Default choices: **Oracle-first ERP adapter**, SAP supported through the same adapter contract, **deterministic quotation extraction with mandatory human verification**, and local PostgreSQL/MinIO/Redis simulation when live ERP credentials are absent.

## Implementation Changes
- Replace seeded/hard-coded demo behavior with real workflow services and state machines. All UI actions must operate on selected records from API data, never fixed IDs like `RFQ-2026-0031`, `PO-DRAFT-2026-0019`, or `REC-001`.
- Enforce tenant/plant scope everywhere with one shared `get_scoped_or_404`/`query_scoped` helper used by every read, mutation, document, outbox, ERP, and agent action. Add optimistic locking, immutable approval records, idempotency keys, and audit creation for every important mutation.
- Complete procurement domain behavior: create requirements, generate RFQs from requirement lines/specs/supplier capabilities, publish RFQs through approved outbox, receive supplier quotations through buyer upload and secure supplier portal token links, verify extracted fields, generate comparisons, create negotiation rounds, approve awards, generate PO drafts, approve/post POs, receive inbound events, inspect material, calculate usable inventory, and create/close exception cases.
- Build real document security: MinIO/S3 storage, quarantine bucket, MIME/signature validation, file-size limits, encrypted/corrupt PDF rejection, macro workbook rejection, formula-injection neutralization, Tesseract OCR in Docker for scanned PDFs/images, parser timeouts, confidence/evidence storage, and short-lived scoped download URLs.
- Rework ERP integration as adapter-driven production infrastructure. Implement `LocalERPAdapter` for PostgreSQL-backed simulation and `OracleFusionProcurementAdapter` for Oracle REST mappings; add `SapS4HanaAdapter` skeleton with contract tests and documented endpoint mappings. All real ERP writes go through an approved integration outbox with idempotency, retry, reconciliation status, payload diff, correlation ID, and audit.
- Upgrade frontend into a professional role-based operations product: simple left navigation, role home queues, one primary next action per screen, connected record timelines, ageing/overdue visualizations, landed-cost waterfall, supplier comparison matrix, workflow progress tracker, exception heatmap, approval queue, document evidence panel, ERP sync status, and audit ledger. Use restrained industrial design tokens, IBM Plex Sans/Mono, compact tables, clear status colors, and no generic AI/marketing surfaces.
- Add production readiness: Redis-backed rate limits/job queues, secure cookie flags by environment, structured redacted logs, background workers for parsing/OCR/outbox/sync, `.env.example` for Oracle/SAP/SMTP/MinIO/Redis, deployment docs, backup/restore notes, and remove generated egg-info/build artifacts from tracked source.

## Public Interfaces
- Add/replace APIs for real workflows:
  `/procurement/requirements`, `/procurement/rfqs`, `/procurement/rfqs/{id}/publish`, `/supplier/rfqs/{token}/quotes`, `/procurement/quotes/{id}/verify-fields`, `/procurement/comparisons/{rfq_id}/generate`, `/procurement/negotiations`, `/procurement/awards/{id}/approve`, `/procurement/po-drafts/{id}/approve`, `/inbound/asns`, `/inbound/gate-entries`, `/inbound/receipts`, `/inbound/inspections`, `/cases/{id}/close`.
- Add integration APIs:
  `/integrations/connections`, `/integrations/sync-jobs`, `/integrations/outbox`, `/integrations/outbox/{id}/approve`, `/integrations/outbox/{id}/dispatch`, `/integrations/reconciliation`.
- Add core types/tables:
  `IntegrationConnection`, `IntegrationSyncJob`, `IntegrationExternalReference`, `IntegrationOutboxEvent`, `DocumentValidationResult`, `QuoteFieldVerification`, `WorkflowTransition`, `ApprovalDecision`, `SupplierPortalToken`, `ERPAdapterResult`.
- Define `ERPAdapter` methods:
  `pull_master_data`, `pull_material_needs`, `pull_open_purchase_orders`, `push_purchase_order`, `pull_purchase_order_status`, `push_receipt`, `pull_receipts`, `pull_inspections`, `reconcile_external_reference`.
- Oracle adapter maps to Fusion Procurement REST resources including draft purchase orders, lines, attachments, validation, and submit actions. SAP adapter maps to S/4HANA OData APIs such as Purchase Order, Purchase Requisition, and Material Document/Goods Movement services.

## Test Plan
- Security/API: cross-tenant and cross-plant IDOR tests for every ID-based endpoint, RBAC denial tests, CSRF tests, rate-limit/lockout tests, immutable approval tests, idempotency replay tests, audit completeness tests, and secure document URL tests.
- Workflow: requirement-to-RFQ, RFQ publish, supplier quote intake, extraction/verification gating, comparison disqualification, negotiation, award approval, PO draft approval, ERP outbox dispatch, acknowledgement, ASN, gate entry, receipt, optional inspection, inventory impact, exception creation, and exception closure.
- Document: valid PDF/XLSX/image, scanned PDF OCR, encrypted PDF, corrupt PDF, MIME spoofing, oversized file, XLSM macro rejection, formula injection, parser timeout, low-confidence field blocking, and AI-disabled completion.
- ERP: local adapter contract tests, Oracle payload mapping tests with recorded fixtures, SAP mapping contract tests, outbox retry/reconciliation tests, no-write mode tests, and approval-required-before-dispatch tests.
- Frontend: Playwright E2E for each role, responsive desktop/tablet/mobile visual checks, no hard-coded action IDs, route access control, build/typecheck passing from a fresh checkout, and UI scenarios where users can complete the full procure-to-receive flow without guessing the next step.

## Assumptions And Sources
- First sellable milestone is the complete **procure-to-receive** vertical slice, not a broad multi-module Manufacturing OS.
- Oracle is the first concrete real connector; SAP support is built through the same adapter interface and documented/tested with contract fixtures until live credentials exist.
- Local development must run without Oracle/SAP access using PostgreSQL-backed simulation that behaves like the real adapter/outbox path.
- Quotation extraction is deterministic plus human review; AI may draft/explain but cannot approve, post, mutate inventory, change master data, or close cases.
- Official integration references used: [Oracle Fusion Cloud Procurement REST APIs](https://docs.oracle.com/en/cloud/saas/procurement/26b/fapra/index.html), [Oracle Procurement REST endpoints](https://docs.oracle.com/en/cloud/saas/procurement/26b/fapra/rest-endpoints.html), [SAP Purchase Order OData API](https://api.sap.com/api/API_PURCHASEORDER_PROCESS_SRV), [SAP Purchase Requisition OData API](https://api.sap.com/api/API_PURCHASEREQ_PROCESS_SRV), and [SAP Material Document API](https://api.sap.com/api/API_MATERIAL_DOCUMENT_SRV).
