# GenuineGigs — Procurement-First Agentic Manufacturing Operations Platform

## Comprehensive Product and Repository Improvement Plan

> **Status:** Authoritative execution contract for the next implementation cycle  
> **Primary source of truth:** `HANDOFF2(2).md`, then checked-in source code  
> **Execution style:** patch-first, phased, test-gated, no repository rewrite  
> **Immediate objective:** deliver an end-to-end procurement operations product that can run against a first-class Excel/CSV external-system connector, connect safely to real ERPs through a reusable connector platform, and complete the requirement-to-receipt-to-invoice-handoff cycle through manual and agentic workflows  
> **Long-term objective:** establish the reusable AI work, integration, and coordination layer that can later connect ERP, PLM, MES, QMS, CMMS, HRMS, email, documents, and other manufacturing systems without replacing their systems of record

---

# 1. How Codex must use this plan

Read the complete current handoff and this file before changing code. Treat checked-in source code as more current than historic plan files, screenshots, reports, or earlier architectural notes.

This plan is intentionally prescriptive so the implementation agent does not need to redesign the product or reconsider the architecture.

## 1.1 Required working style

1. Inspect `git status --short`, `git diff --check`, and relevant changed files before editing.
2. Preserve the intentionally dirty worktree and all unrelated work.
3. Do not use `git reset --hard`, `git checkout --`, destructive cleanup, or broad generated-file replacement.
4. Make the smallest safe change that completes the current phase.
5. Add or update regression tests before modifying behavior that caused a demonstrated user failure.
6. Complete phases in the order defined in this plan.
7. Do not pause after scaffolding, model definitions, design tokens, or test creation.
8. Do not report a phase as complete until its phase gate passes.
9. Do not claim Docker, live Groq, Oracle, SAP, SMTP, security, accessibility, or browser verification unless it was actually run and passed.
10. If Docker is unavailable because of WSL or Docker Desktop integration, continue all non-Docker work and report the exact unresolved Docker gate.

## 1.2 Patch-first constraints

Do not rewrite the repository.

Do not replace:

- FastAPI;
- SQLAlchemy;
- PostgreSQL;
- Redis/Celery;
- MinIO/S3-compatible storage;
- Next.js and React;
- the existing LangGraph direction;
- canonical procurement services;
- role, tenant, plant, membership, approval, audit, idempotency, and document-security controls.

Do not add:

- CrewAI;
- AutoGen;
- another general agent SDK;
- a second task engine;
- a second procurement state machine;
- a new frontend UI framework;
- a new global state library;
- a separate “AI procurement” data model;
- a third V1/V2/V3 workflow path;
- direct LLM database, SQL, shell, ERP credential, or unrestricted HTTP access.

New small modules are allowed where they reduce the responsibilities of existing monoliths, but public contracts and canonical services must remain stable unless a migration is explicitly included.

## 1.3 Source-of-truth order

When information conflicts, use this order:

1. checked-in code;
2. current database migrations;
3. generated OpenAPI contract;
4. automated tests;
5. `HANDOFF2(2).md`;
6. this plan;
7. historic plans and screenshots.

The handoff contains an apparent contradiction: a July 18 completion note claims the bounded runtime upgrade is implemented, while the July 19 snapshot says the live `run_message` path still uses one-shot capability selection and legacy routing. Phase 0 must resolve this from code and tests before any runtime work.

---

# 2. Product direction

## 2.1 Product definition

GenuineGigs must be presented and built as:

> **An AI work and coordination layer for manufacturing companies that works above their existing business systems. It gives each operational role a context-aware assistant, converts records and documents into accountable work, helps employees perform that work, coordinates handoffs and follow-ups, and safely prepares or executes approved actions in the systems of record.**

The current commercial wedge is procurement. The product must first become an excellent **AI procurement operations layer**, not another general ERP.

## 2.2 What the product owns

GenuineGigs should own:

- role assistants;
- conversation and context;
- task coordination;
- work dependencies;
- approvals and proposals;
- follow-ups and escalations;
- document intake and extraction;
- artifact preparation;
- cross-system record references;
- exception coordination;
- audit receipts;
- proactive alerts;
- manager summaries;
- safe integration orchestration.

## 2.3 What remains in customer systems

Existing systems remain authoritative for their domains:

- ERP: financial and inventory ledgers, material/vendor masters, official transactions;
- PLM: product definitions, drawings, specifications, revisions;
- MES: production execution and schedules;
- QMS: formal quality records where already deployed;
- CMMS: maintenance system of record;
- HRMS: employment, payroll, sensitive HR data;
- email/document systems: original communications and files where required.

GenuineGigs may synchronize approved metadata, cache needed records, store workflow context, and safely write through supported APIs, but it must not silently replace these systems.

## 2.4 Procurement completion definition

The procurement product is complete for a serious pilot only when a customer can operate the complete procurement cycle using either a connected ERP or an Excel/CSV-based external system of record.

The product must support:

1. customer onboarding for company, plants, departments, users, roles, reporting lines, approval limits, procurement policies, currencies, taxes, UOMs, materials, suppliers, supplier capabilities, and required certificates;
2. initial and incremental master-data ingestion from Excel/CSV, ERP APIs, secure file exchange, or approved manual entry;
3. material requirement intake from ERP/MRP, Excel/CSV, API, upload, or conversation;
4. deduplication, source lineage, external IDs, versioning, and conflict handling for imported requirements;
5. approved-material and supplier-eligibility validation;
6. supplier request/RFQ preparation, supplier shortlist, review, immutable issue, and delivery-status tracking;
7. quotation receipt through supplier portal, email ingestion, manual upload, spreadsheet upload, or API;
8. document validation, extraction, source evidence, confidence review, correction, and approval;
9. deterministic normalization of UOM, currency, taxes, discounts, freight, payment terms, lead time, validity, certificates, and technical deviations;
10. multi-line comparison, split-award support, partial quantities, recommendation explanation, negotiation rounds, and quotation revision history;
11. configurable approval policies, segregation of duties, multi-level approval, delegation, reminders, and escalation;
12. purchase-order preparation, amendment/versioning, controlled supplier issue, and safe ERP or Excel write-back;
13. supplier acknowledgement, requested changes, committed delivery dates, ASN, and delay updates;
14. Gate entry, Stores receipt, shortage/excess/damage capture, Quality inspection, accepted/rejected/held disposition, and return/replacement coordination;
15. partial delivery, backorder, rejection, reinspection, replacement, cancellation, and closure handling;
16. optional supplier-invoice capture and PO/receipt/invoice three-way-match preparation, with finance handoff but without autonomous payment posting;
17. read-only visibility of ERP payment or invoice status where the customer permits it;
18. manual and assistant execution through the same canonical services and records;
19. role-specific assistants for Plant Manager, Purchase Executive, Purchase Manager, Gate, Stores, Quality, Integration Admin, and optional Finance Reviewer;
20. tasks, dependencies, notifications, proactive exceptions, morning briefs, end-of-day status capture, and sourced manager summaries;
21. complete audit, action receipts, immutable artifacts, external references, integration attempts, and reconciliation;
22. customer-visible control of read/write scope, connection mode, approval requirements, and emergency disablement;
23. an Excel/CSV connector that can serve as the external test system of record for the entire demo and automated acceptance suite;
24. a reusable connector SDK and mapping engine that allows any ERP with an API, standard protocol, middleware, or file exchange to be integrated without changing procurement business logic;
25. verified reference adapters for the ERP vendors selected for the target market, with claims limited to capabilities that have passed contract and customer acceptance tests;
26. evidence-linked metrics for cycle time, savings, supplier performance, workload, exception age, integration health, and agent quality;
27. reliable degraded/manual operation when the LLM, email provider, document worker, or external ERP is unavailable.

## 2.5 Meaning of “connect to all ERPs”

Do not interpret this goal as hard-coding every ERP vendor into the procurement domain.

The product must instead become **ERP-agnostic through a connector platform**. Every external system must connect through the same capability, mapping, safety, and reconciliation contracts.

Support five integration patterns:

1. official vendor API adapter;
2. standard protocol adapter such as REST/OpenAPI, OData, or SOAP;
3. customer middleware or iPaaS adapter;
4. secure file exchange using XLSX, CSV, or SFTP;
5. customer-hosted bridge for private-network systems.

The product may say that it can integrate with any ERP that exposes one of these supported patterns. It must not claim that every ERP has an out-of-the-box certified connector.

Out-of-the-box connector priorities for the procurement-completion cycle are:

1. Excel/CSV external-system connector — mandatory and used for testing;
2. generic REST/OpenAPI connector;
3. generic OData connector;
4. Oracle Fusion Procurement adapter based on the existing implementation;
5. SAP S/4HANA adapter completed only to the capability level actually tested;
6. Microsoft Dynamics 365 Finance and Supply Chain / Business Central mapping pack;
7. Odoo procurement mapping pack;
8. secure SFTP file connector for legacy and SME ERPs.

Tally, Busy, Marg, Zoho, custom ERPs, and other regional products should initially connect through file exchange, middleware, or a custom adapter built with the same SDK. Add a dedicated adapter only when customer demand justifies its maintenance cost.

---

# 3. Non-negotiable product invariants

These rules must hold across every phase.

1. `PurchaseRequirement` remains the only active procurement demand record.
2. Missing approved material uses the material-master request process; it does not create a duplicate demand object.
3. Manual and assistant paths call the same canonical services and state machine.
4. The LLM interprets, resolves, plans, summarizes, and selects authorized tools.
5. Canonical services authorize, calculate, validate, persist, and audit.
6. The model never writes business tables directly.
7. The model never receives ERP credentials, raw SQL, shell, or unrestricted HTTP tools.
8. One business mutation maximum per assistant turn.
9. Multiple bounded read and resolution tools are allowed before that mutation.
10. External, commercial, immutable, inventory, financial, quality-disposition, and ERP actions retain explicit authority boundaries.
11. Mutation success language requires a matching persisted `AgentActionReceipt` or equivalent durable proof.
12. Every read and write is tenant-, workspace-, plant-, membership-, role-, and reporting-scope aware.
13. Manual work remains usable when the provider is unavailable or agents are disabled.
14. Draft preview never publishes, communicates externally, approves, posts, or changes inventory.
15. Supplier email, dispatch, delivery, ERP posting, external acknowledgement, and reconciliation remain distinct states.
16. Generated final business documents remain versioned, immutable, checksummed, and privately delivered through the API.
17. Agent-to-agent coordination is persisted, inspectable, bounded, and authorized; it is not hidden model roleplay.
18. The interface uses business language while the backend retains exact lifecycle precision.
19. Never expose raw UUIDs, JSON, internal capability names, runs, checkpoints, tool calls, receipts, artifacts, or outboxes to normal users unless explicitly requested by an authorized administrator.
20. Existing migrations are never edited after application; schema changes use a new migration.
21. Excel/CSV is an external integration source, not a replacement for PostgreSQL, canonical services, audit, or workflow state.
22. Every imported row retains source file, sheet, row, external key, mapping version, import batch, hash, and validation outcome.
23. Re-imports are idempotent and never silently create duplicate master or transaction records.
24. File write-back creates a new controlled workbook/export version; it never destructively overwrites the customer’s only copy.
25. Unknown sheets and unmapped columns are preserved where practical and never treated as executable instructions.
26. Spreadsheet formulas, macros, links, and embedded content are untrusted; the platform never executes macros.
27. External-system ownership is explicit per entity and field: external-owned, GenuineGigs-owned, or synchronized/mirrored.
28. Conflicting external changes stop the write or enter an exception workflow; last-write-wins is not the default.
29. Connector capability claims are generated from tested manifests, not marketing copy or provider names.
30. No ERP adapter may bypass the integration outbox, approval, idempotency, verification, external-reference, and reconciliation pipeline.
31. One connector failure cannot block unrelated manual procurement work.
32. Email, supplier portal, Excel, and ERP ingestion converge on the same document, quotation, requirement, PO, and inbound models.
33. Supplier invoice matching may prepare a finance handoff, but payment release and journal posting remain outside autonomous scope.

---

# 4. Current baseline to preserve

The repository already contains substantial working foundations. Do not recreate them.

## 4.1 Procurement domain

Preserve and improve the existing sequence:

```text
Approved material
→ Material requirement
→ Supplier request draft
→ Supplier selection and review
→ Send to suppliers
→ Supplier quotations
→ Extraction and human verification
→ Comparison and recommendation
→ Approval
→ Purchase order
→ Supplier acknowledgement
→ Gate
→ Stores
→ Quality
→ Inventory impact and exceptions
```

## 4.2 Existing governance

Preserve:

- role ownership;
- reporting hierarchy;
- capability registry;
- task lifecycle;
- proposals and confirmations;
- action receipts;
- audit events;
- workflow transitions;
- CSRF protection;
- HTTP idempotency;
- selected optimistic concurrency;
- private object storage;
- signed download links;
- agent and ERP kill switches;
- simulation modes;
- integration outbox, attempts, external references, and reconciliation.

## 4.3 Existing agent building blocks

The following appear to exist and must be verified, integrated, or consolidated rather than recreated:

- `agent_runtime.py` bounded tool loop;
- `agent_state.py` and `AgentThreadStateV2`;
- `agent_resolution.py`;
- capability registry;
- `ToolResult`-style schemas;
- `AgentProfile`;
- `AgentThread` and messages;
- runs, events, checkpoints, and tool calls;
- proposals;
- action receipts;
- delegations;
- agent memory and knowledge;
- live Groq scorecard scaffold.

---

# 5. Principal gaps to solve

## 5.1 Agent runtime gap

The live assistant must stop behaving as a single-turn classifier plus handwritten dispatcher. The target is a bounded, compositional tool agent that can:

- understand a natural request;
- resolve entities;
- inspect workflow state;
- search related records;
- evaluate tool observations;
- execute one canonical mutation or create one controlled proposal;
- persist the result;
- respond with grounded business language and relevant next actions.

## 5.2 Capability contract gap

Every declared capability must have one implemented typed adapter. No capability may:

- fall through to “not implemented yet”;
- silently map to an incompatible legacy intent;
- discard declared arguments;
- require unrelated task context when an exact business record was supplied.

## 5.3 Conversation-state gap

All live state writes must pass through one versioned state module. The assistant must reliably remember:

- current goal;
- selected page record;
- recent records;
- draft facts;
- attachments;
- pending proposals;
- blockers;
- last successful receipt.

Topic changes must remove incompatible stale blockers and candidates.

## 5.4 Manual UX gap

The interface exposes technical lifecycle actions as unrelated buttons. Each workbench must show:

- current business state;
- relevant record context;
- blockers;
- one dominant next action;
- secondary review/download actions;
- clear consequence confirmation only where needed.

## 5.5 Product-home gap

The first screen must prioritize:

1. decisions requiring attention;
2. work prepared by the assistant;
3. explicit tasks left;
4. blockers;
5. work waiting on others;
6. team follow-ups for managers;
7. one visible conversational interface.

It must not prioritize generic metrics, raw process stages, or configuration concepts.

## 5.6 Integration trust gap

The product needs a customer-visible integration control plane showing:

- connected system;
- read permissions;
- write permissions;
- plants and business units;
- sync status;
- proposed writes;
- dispatched writes;
- acknowledgements;
- reconciliation failures;
- emergency disable control.

## 5.7 Enterprise evidence gap

The code contains useful controls, but the product is not yet certified or production-proven. Security claims, ERP support claims, provider privacy claims, and reliability claims must remain factual and supported.

## 5.8 Excel and file-integration gap

The existing plan does not yet make Excel/CSV a first-class external system. This is a major gap because it is the safest way to test realistic integration behavior without customer ERP credentials and it is also a valid production integration path for manufacturers that operate from spreadsheets or legacy exports.

The product needs workbook discovery and mapping, canonical templates, dry-run validation, row-level lineage and errors, idempotent imports, incremental re-import, controlled export/write-back, conflict detection, reconciliation, golden fixture workbooks, and end-to-end tests that use Excel as the external source of truth.

## 5.9 Universal ERP connector gap

The current adapter set does not equal universal ERP connectivity. The repository needs one connector protocol, one capability manifest, one mapping engine, one sync model, one write-safety pipeline, and one certification harness. Vendor-specific adapters must be thin translations over this foundation.

## 5.10 Procurement-domain completeness gap

The core requirement-to-quality path exists, but a market-complete procurement product must also handle multi-line sourcing, split awards, partial quantities, quotation revisions, negotiation rounds, PO amendments and cancellations, partial deliveries and backorders, returns and replacements, supplier onboarding/compliance, invoice capture and three-way-match preparation, source-system conflicts, and real email/supplier-response ingestion.

## 5.11 Integration test-environment gap

A connector cannot be considered safe because mocked unit tests pass. The repository needs an external-system simulator based on Excel/CSV, deterministic contract fixtures, replayable integration scenarios, connector conformance tests, failure injection, and reconciliation evidence.

---

# 6. Target assistant experience

## 6.1 Interaction standard

The assistant should feel comparable to a modern work agent, while remaining governed.

It must:

- understand normal human language rather than exact commands;
- tolerate spelling mistakes and abbreviations;
- understand business numbers and item codes;
- resolve “latest,” “this,” “it,” and “the one I just created”;
- understand relative dates;
- use selected page context without requiring the user to repeat it;
- use attachments as task inputs;
- execute multi-step reads before one mutation;
- ask only for genuinely missing information;
- preserve already provided facts;
- explain blockers and offer allowed remediation;
- answer the user’s question first;
- return actual business IDs immediately after persistence;
- never promise future work that is not scheduled or running;
- never dump raw task lists or objects;
- never repeat generic role-ownership boilerplate after every reply.

## 6.2 Correct conversation examples

### Create a requirement

**User**

> Create a requirement for 100 KG Aluminium Ingot needed one month from today and assign it to Meera.

**Assistant behavior**

1. Resolve material by code/name/alias in current plant.
2. Resolve quantity/UOM/date.
3. Resolve the active Purchase Executive assignee.
4. Inspect whether genuinely required information is missing.
5. Call the canonical requirement service.
6. Persist the receipt and recent entity.
7. Return:

```text
Material requirement REQ-2026-00xx was created.

Aluminium Ingot · 100 KG
Needed by 19 August 2026
Assigned to Meera Iyer

Next: Meera can prepare the supplier request.

[Open requirement] [Ask Meera to start]
```

### Prepare an RFQ

**User**

> Prepare the supplier request for the latest requirement.

**Assistant behavior**

1. Resolve recent eligible requirement.
2. Inspect workflow state.
3. Resolve capable suppliers.
4. Create or return the idempotent RFQ draft.
5. Generate preview.
6. Persist receipt.
7. Return:

```text
Supplier request RFQ-2026-00xx is ready for review.

REQ-2026-00xx · Aluminium Ingot · 100 KG
3 approved suppliers selected
Response deadline: 2 August 2026

It has not been sent yet.

[Review draft] [Edit suppliers]
```

### Create a supplier comparison from attachments

**User**

> Compare these quotations for RFQ-2026-0033 and recommend the best supplier.

The user uploads PDF, image, or XLSX files.

**Assistant behavior**

1. Validate attachments and scope.
2. Resolve the RFQ.
3. Associate each quote with the correct supplier or ask one bounded disambiguation question.
4. Start extraction.
5. Show processing state.
6. Identify low-confidence or missing fields.
7. Allow inline verification or deep-link to evidence review.
8. Once eligible quotes are verified, call canonical comparison generation.
9. Return the canonical comparison and document.
10. Explain recommendation and risks.
11. Offer the controlled approval submission action.

### Follow-up reference

**User**

> What is its ID?

**Assistant**

> The supplier request is **RFQ-2026-00xx**.

### Topic change

When the user abandons Copper and starts an Aluminium request, stale Copper candidates and blockers must be cleared immediately.

---

# 7. Target agent architecture

## 7.1 Live execution loop

Integrate one bounded LangGraph execution path into `run_message`.

```text
Create run and context
→ load typed thread state
→ load role-scoped tool definitions
→ model chooses read/resolution tool or final response
→ validate tool schema and authorization
→ execute tool
→ append compact observation
→ repeat within budgets
→ stop after one mutation or one proposal
→ persist receipt/proposal/state/events
→ compose grounded response
```

### Required budgets

Use configuration-backed limits. Initial defaults:

- maximum model/tool loop steps: 6;
- maximum read/resolution calls: 5;
- maximum business mutations: 1;
- maximum controlled proposals: 1;
- maximum search candidates returned: 3;
- maximum task items in normal response: 5;
- maximum delegation depth: 3;
- maximum runtime: use existing configured bound, with a clear timeout response;
- token/context limits: use existing settings and compact observations.

## 7.2 Tool categories

### Resolution and read tools

Implement or standardize:

- `resolve_record(reference, allowed_types)`;
- `search_records(record_type, query, status, limit)`;
- `get_record_summary(entity_type, entity_id)`;
- `get_workflow_state(entity_type, entity_id)`;
- `resolve_material(query)`;
- `resolve_assignee(role, query)`;
- `list_actionable_work(status='active', limit=5)`;
- `get_supplier_capabilities(item_ids)`;
- `get_quote_extraction_state(quote_or_document_id)`;
- `get_comparison_state(rfq_or_comparison_id)`;
- `get_integration_delivery_state(entity_type, entity_id)`;
- `search_approved_knowledge(query, scope)`.

### Canonical mutation tools

Implement direct typed adapters for:

- create material-master request;
- create purchase requirement;
- prepare RFQ draft;
- update RFQ draft;
- upload/associate supplier quotation;
- correct/accept/reject extracted quotation field;
- verify quotation;
- generate comparison;
- delegate task;
- request task update;
- record task blocker/completion;
- prepare Gate entry;
- prepare Store receipt;
- prepare Quality inspection record;
- create exception/case where canonical behavior requires it.

### Controlled proposal tools

These must create a proposal and stop the loop:

- send RFQ to suppliers;
- submit recommendation for approval;
- approve/reject/request changes;
- create final purchase order;
- send PO to supplier;
- dispatch ERP write;
- perform quality disposition where authority requires confirmation;
- close critical exception;
- modify approved master data.

## 7.3 Typed adapter contract

Every adapter must accept the same inputs and return the same structure.

```python
AdapterContext = (
    db,
    actor,
    membership,
    thread,
    run,
    validated_args,
    correlation_id,
)

ToolResult = {
    "status": "success|needs_input|blocked|proposal|failed",
    "business_summary": str,
    "records": list,
    "observations": list,
    "missing_fields": list,
    "blockers": list,
    "allowed_next_actions": list,
    "proposal": object | None,
    "receipt": object | None,
    "citations": list,
}
```

Rules:

- every registry capability has exactly one adapter;
- every adapter validates its declared schema;
- mutations require a receipt;
- proposals must not create the final controlled effect;
- adapters call canonical domain services;
- no adapter directly mutates arbitrary ORM fields to bypass workflow logic;
- no adapter returns raw ORM rows or giant JSON payloads to the model.

## 7.4 State ownership

Make `AgentThreadStateV2` the only live state read/merge/write gateway.

Required state:

```json
{
  "schema_version": 2,
  "active_goal": {
    "capability": null,
    "status": null,
    "started_at": null
  },
  "draft_fields": {},
  "selected_context": {
    "entity_type": null,
    "entity_id": null,
    "business_number": null
  },
  "recent_entities": [],
  "candidate_set": [],
  "pending_proposal_id": null,
  "last_receipt": null,
  "attachments": [],
  "blocked_on": null,
  "last_user_correction": null,
  "updated_at": null
}
```

State rules:

- explicit user corrections override inferred values;
- current-turn selected page context outranks older conversation state;
- recent persisted entities are stored by canonical ID and business number;
- topic changes clear incompatible draft fields, candidates, and blockers;
- successful mutation stores the receipt and primary record;
- proposal confirmation/rejection updates pending state;
- state writes are schema-validated;
- old state is migrated lazily or via migration helper without breaking threads.

## 7.5 Universal resolution policy

Resolution order:

1. exact scoped database ID;
2. exact scoped business number;
3. selected page record;
4. current work-item record;
5. recent conversation entity;
6. safe relative qualifier such as “latest eligible requirement”;
7. normalized search;
8. at most three labelled candidates.

Material matching should support:

- item code;
- exact name;
- normalized name;
- common abbreviations and aliases stored as data;
- punctuation and spacing variants;
- safe typo-tolerant candidate ranking.

Do not implement business behavior as a long list of exact phrase patterns. Deterministic parsing may normalize dates, quantities, units, business numbers, and provider-outage cases, but the model and tools must handle general phrasing.

## 7.6 Response generation

The response layer receives only compact, grounded observations.

It must:

- answer the user’s request in the first sentence;
- include the persisted business number after creation;
- distinguish created, prepared, submitted, sent, dispatched, acknowledged, reconciled, and failed;
- show no more than five tasks unless more were requested;
- hide raw UUIDs unless requested;
- hide internal runtime terminology;
- show relevant next actions only;
- include blockers and remediation;
- include evidence/source links where appropriate;
- never claim future work will happen “shortly” unless an actual background job exists and its status is shown;
- never claim mutation success without receipt validation.

---

# 8. Complete procurement assistant skills

The procurement release must cover the whole existing workflow, not only requirements and RFQs.

## 8.1 Plant Manager assistant

Required skills:

- create a requirement;
- delegate sourcing work;
- ask for status by requirement/RFQ/PO/material;
- list decisions requiring attention;
- summarize procurement risks;
- explain comparison recommendations;
- approve/reject/request changes where authorized;
- follow up on descendants;
- receive daily procurement brief;
- see delayed material and quality-hold impact;
- request a factual team summary.

## 8.2 Purchase Executive assistant

Required skills:

- clarify requirement information;
- prepare supplier request;
- identify approved capable suppliers;
- modify supplier shortlist and deadline;
- produce preview;
- prepare controlled send proposal;
- track supplier responses;
- upload/associate quotations;
- draft and send approved follow-ups;
- detect missing supplier documents;
- explain RFQ state and blockers.

## 8.3 Purchase Manager assistant

Required skills:

- inspect quotation processing state;
- review extraction confidence;
- correct and verify fields;
- compare verified quotations;
- calculate normalized landed cost through deterministic services;
- explain recommendation and disqualifications;
- prepare negotiation points;
- submit recommendation for approval through proposal;
- prepare final PO after approval;
- track supplier acknowledgement;
- summarize supplier performance and risks.

## 8.4 Gate assistant

Required skills:

- list expected deliveries;
- resolve PO/ASN/challan context;
- extract challan information;
- detect missing documents;
- prepare Gate entry;
- show mismatch warnings;
- notify Stores after persisted entry.

## 8.5 Stores assistant

Required skills:

- list Gate-admitted deliveries awaiting receipt;
- retrieve PO/material/supplier context;
- record received, damaged, shortage, and excess quantities;
- explain validation errors;
- prepare receipt;
- notify Quality when inspection is required;
- close the handoff when inspection is not required.

## 8.6 Quality assistant

Required skills:

- retrieve material specification and certificate requirements;
- show inspection checklist;
- inspect supplier and batch history;
- record accepted, rejected, and held quantities;
- explain quantity validation;
- create/update exceptions;
- prepare inspection report;
- alert Procurement and management about supplier quality problems.

## 8.7 Admin assistant

Required skills:

- explain workspace readiness;
- configure roles and reporting lines through governed forms;
- inspect agent policy and provider health;
- inspect integration state;
- reconcile demo users;
- request material-master approval;
- review audit and failed integrations;
- never bypass role or approval rules.

## 8.8 Integration Administrator assistant

Required skills:

- explain connection health and tested capabilities;
- guide Excel/CSV mapping and import preview;
- identify invalid rows and likely mapping corrections;
- compare an external record with the canonical record;
- prepare a sync, export, or reconciliation run;
- explain failed attempts and conflicts;
- prepare credential rotation or connection-disable actions;
- generate a connector acceptance report;
- never reveal credentials, approve commercial decisions, bypass validation, force production writes, or treat timeouts as success.

## 8.9 Optional Finance Reviewer assistant

Required skills:

- retrieve approved PO, receipts, inspection results, and supplier invoice;
- prepare deterministic two-way or three-way match results;
- explain quantity, price, tax, freight, duplicate, and missing-evidence discrepancies;
- request missing evidence and route exceptions;
- prepare the finance handoff;
- read payment status when authorized;
- never release payment, post journals, change bank data, or approve its own exception.

---

# 9. Manual procurement UX redesign

## 9.1 Core interaction rule

For every selected business record, show:

- record identity;
- current state;
- owner;
- due date;
- blocker;
- one primary next action;
- secondary review/download actions;
- concise recent activity;
- contextual assistant.

Do not show every technically possible mutation at the same time.

## 9.2 Requirements workbench

### List view

Show:

- requirement number;
- material summary;
- total quantity/UOM;
- needed-by date;
- assigned buyer;
- current state;
- next action;
- overdue/risk indication.

Do not show raw internal IDs or empty technical columns.

### Create flow

Default simple flow:

1. material;
2. quantity/UOM;
3. need-by date;
4. reason;
5. assigned Purchase Executive;
6. review and create.

Support multiple lines without forcing complexity on single-line requirements.

When a material is absent:

- explain that it is not approved;
- offer **Request new material**;
- prefill proposed name/code/UOM/specification/reason from conversation/form;
- preserve the original requirement draft;
- resume after approval where policy allows.

## 9.3 RFQ workbench

Replace peer actions with a state-driven flow:

```text
1. Request details
2. Suppliers
3. Review
4. Send
5. Track responses
```

### State actions

| State | Primary action | Secondary actions |
|---|---|---|
| Approved requirement, no RFQ | Prepare supplier request | View requirement |
| Incomplete RFQ draft | Complete supplier request | Save and exit |
| Complete draft | Review and send | Save and exit |
| Review | Send to N suppliers | Edit, download preview |
| Prepared for dispatch | View delivery status | Download issued PDF |
| Dispatched | Track quotations | Download issued PDF |
| Failed delivery | Resolve delivery failure | Retry where authorized |

Implementation requirements:

- preserve originating requirement across navigation and refresh;
- autosave ordinary draft edits with saved/error state;
- generate preview inside Review;
- centralize send action in one component;
- remove duplicate publish controls;
- clearly explain immutability and recipients;
- distinguish pending dispatch from delivered email.

## 9.4 Quotation workbench

Use a workbench with:

- RFQ and supplier context;
- source document preview;
- extraction progress;
- fields grouped by commercial, delivery, tax, technical, certificate, and deviation sections;
- confidence and evidence;
- accept/correct/reject actions;
- clear statement of whether a field blocks verification/comparison;
- one primary action: **Verify quotation** when ready.

The assistant attachment workflow must deep-link here and show the same canonical record.

## 9.5 Comparison workbench

State sequence:

```text
Verify quotations
→ Compare verified quotations
→ Review recommendation
→ Send recommendation for approval
→ Await decisions
→ Approved / Changes requested
```

Show:

- supplier columns or cards;
- landed cost breakdown;
- delivery feasibility;
- compliance;
- supplier quality/delivery history;
- recommendation reasons;
- risks and disqualifications;
- source evidence links;
- editable manager rationale;
- immutable submitted version.

Do not show generate, preview, submit, decision, and PO controls as equal actions.

## 9.6 Approval workbench

Each approver sees:

- decision required;
- comparison version;
- recommended supplier;
- value and delivery summary;
- risks;
- manager rationale;
- source document links;
- approve, reject, request changes;
- mandatory rationale where required.

Do not duplicate the same decision control on multiple pages. Other pages deep-link to the canonical decision screen.

## 9.7 Purchase order workbench

State sequence:

```text
Approved supplier selection
→ Review PO draft
→ Create purchase order
→ Send to supplier
→ ERP synchronization
→ Supplier acknowledgement
```

Keep separate:

- draft preparation;
- final PO creation;
- supplier communication;
- ERP dispatch;
- ERP acknowledgement/reconciliation;
- supplier acknowledgement.

## 9.8 Inbound workbenches

Every Gate, Stores, and Quality form must be opened with selected business context. Do not force raw-ID dropdown selection when linked context already exists.

Show one next action and the dependency chain:

```text
Expected delivery
→ Gate admitted
→ Store received
→ Quality inspected
→ Inventory impact recorded
```

---

# 10. Assistant-first product shell

## 10.1 Desktop layout

At widths above 1280px:

```text
Compact navigation | Main work area | Persistent role assistant
```

Recommended widths:

- navigation: 220–232px;
- assistant: 360–400px;
- main content: flexible remainder.

The main area must expand when the assistant is intentionally collapsed.

## 10.2 My Work homepage

The first viewport must contain real work, not mostly navigation or metrics.

Required sections in priority order:

1. **Needs your attention**
2. **Assistant prepared**
3. **My tasks**
4. **Waiting on others**
5. **Team follow-ups** for managers
6. **Recent activity** only below the main work

### Needs your attention

Cards represent decisions or risks:

- comparison approval;
- RFQ ready to send;
- quotation fields needing review;
- PO awaiting creation;
- supplier delivery risk;
- quality hold;
- ERP synchronization failure.

### Assistant prepared

Show artifacts and drafts already prepared:

- supplier request draft;
- quotation extraction;
- supplier comparison;
- follow-up message;
- PO draft;
- inspection checklist.

### My tasks

Show explicit task text, linked business context, due state, and next action.

### Waiting on others

Show supplier, approver, employee, Gate, Stores, Quality, ERP, or background processing dependency.

### Team follow-ups

For managers, show employees, work items, blockers, due status, and request-update action.

## 10.3 Navigation

Normal-role navigation should be compact and grouped:

- My Work;
- Procurement;
  - Requirements;
  - Supplier requests;
  - Quotations;
  - Comparisons and approvals;
  - Purchase orders;
- Inbound;
  - Gate;
  - Stores;
  - Quality;
- Team, where relevant;
- Reports, where relevant;
- Admin, only for authorized roles.

Add role-scoped badges for actionable counts.

Compatibility and technical routes remain hidden from ordinary navigation.

## 10.4 Assistant panel

The assistant must be visible by default on wide screens.

It includes:

- role and plant context;
- selected record context;
- messages;
- attachments;
- processing status;
- business result cards;
- allowed next actions;
- composer;
- suggested prompts based on role and selected state.

Do not show internal sections labelled runs, checkpoints, tools, receipts, or capability IDs.

## 10.5 Responsive behavior

At tablet widths:

- navigation becomes compact/collapsible;
- assistant becomes a full-height drawer;
- main content uses full available width;
- no horizontal page overflow.

At mobile widths:

- attention items appear first;
- assistant is accessible through a persistent action/composer;
- forms become single column;
- tables scroll or become business cards;
- all interactive targets are at least 44px;
- dialogs trap focus and remain usable.

## 10.6 Visual system

Use a modern, restrained operations design.

Required characteristics:

- neutral light work surface;
- dark compact navigation;
- white or subtly tinted surfaces;
- semantic status colors used sparingly;
- consistent 8px spacing scale;
- clear typography hierarchy;
- restrained borders and shadows;
- no gradients, decorative AI artwork, oversized hero branding, or giant empty cards;
- no permanent large blank area;
- no decorative process rail on the general homepage.

Create reusable semantic components:

- `StatusBadge`;
- `RecordIdentity`;
- `WorkflowStepper`;
- `PrimaryAction`;
- `SecondaryAction`;
- `ConsequenceDialog`;
- `TaskCard`;
- `AttentionCard`;
- `PreparedWorkCard`;
- `NotificationBadge`;
- `EmptyState`;
- `ErrorState`;
- `LoadingState`;
- `EvidenceField`;
- `AgentResultCard`;
- `IntegrationStatus`.

---

# 11. Task, notification, and coordination layer

## 11.1 Task as the shared work primitive

Every task must contain or derive:

- required outcome;
- owner membership and role;
- delegator;
- linked business record;
- material/supplier context;
- priority;
- due date;
- blocker;
- expected output;
- dependency;
- completion summary/evidence;
- next responsible role;
- follow-up and escalation state.

## 11.2 Semantic task idempotency

Prevent duplicate active tasks for the same semantic work.

Define a semantic key using:

```text
tenant + plant + task_type + linked_entity_type + linked_entity_id + owner_membership + active_generation/version
```

Requirements:

- service-level get-or-create behavior;
- unique database enforcement where safe;
- reconciliation command for existing duplicates;
- completed historical tasks remain preserved;
- duplicate reconciliation is audited.

## 11.3 Notification design

Notifications are business alerts, not every internal event.

Required categories:

- decision required;
- task assigned;
- task overdue;
- update requested;
- supplier response overdue;
- quotation review required;
- comparison ready;
- approval pending;
- PO acknowledgement overdue;
- delivery approaching or late;
- Gate/Stores/Quality handoff pending;
- quality hold/rejection;
- ERP synchronization failure;
- agent proposal requiring confirmation.

Notification requirements:

- role and scope enforcement;
- deduplication;
- read/read-all;
- deep link to selected record/action;
- priority and due state;
- badge counts refreshed after mutation;
- no raw internal event text.

## 11.4 Manager follow-up

A manager can ask:

> What is blocking REQ-2026-0033?

The system should:

1. resolve the record;
2. inspect workflow and active task;
3. identify the authorized descendant owner;
4. return current known state immediately;
5. optionally create a persisted update request;
6. notify the employee;
7. capture their response/blocker;
8. summarize upward with owner, timestamp, blocker, and commitment.

No recursive free-form agent chats. Enforce depth, cycle, reporting, and privacy restrictions.

## 11.5 Daily work loop

After procurement core reliability is complete, add:

### Morning brief

- priorities;
- decisions;
- overdue work;
- supplier deadlines;
- blockers;
- assistant-prepared work;
- people waiting.

### End-of-day check

- completed commitments;
- incomplete tasks;
- reason/blocker selection;
- tomorrow commitment;
- follow-up proposal.

### Manager summary

- team work completed;
- overdue work;
- blockers requiring authority;
- supplier and material risks;
- no opaque employee score.

---

# 12. Supplier communication and portal

## 12.1 Communication states

Use precise states:

```text
Drafted
→ Approved for dispatch
→ Dispatched
→ Delivered or failed, when available
→ Supplier responded
```

Do not call outbox creation “email sent.”

## 12.2 Required communication workflows

Support:

- RFQ email draft;
- controlled supplier request dispatch;
- secure quotation upload;
- supplier clarification;
- quotation deadline reminder;
- supplier follow-up;
- negotiation message;
- PO dispatch;
- PO acknowledgement;
- confirmed delivery date;
- missing-certificate request;
- corrective-action communication.

## 12.3 Lightweight supplier portal

For pilot completeness, support only:

- secure token access;
- RFQ view/download;
- quotation submission;
- clarification response;
- PO acknowledgement;
- delivery-date confirmation;
- certificate/dispatch-document upload.

Do not build a broad supplier marketplace or supplier ERP.

---

# 13. Supplier intelligence and business value

## 13.1 Supplier scorecard

Derive factual metrics from persisted records:

- quotation response rate;
- quotation turnaround;
- price competitiveness;
- delivery commitment accuracy;
- on-time delivery;
- quality acceptance/rejection;
- certificate compliance;
- PO acknowledgement time;
- deviation frequency;
- corrective-action closure time;
- material capabilities;
- commercial terms.

## 13.2 Recommendation explanation

Comparison recommendations must show:

- landed cost;
- required-date feasibility;
- technical compliance;
- certificates;
- supplier quality and delivery history;
- payment terms;
- MOQ;
- disqualification reasons;
- risks;
- human-overridable rationale.

Do not ask the LLM to calculate authoritative prices, taxes, quantities, or scores when deterministic services exist.

## 13.3 Customer ROI metrics

Expose:

- requirement-to-supplier-request time;
- supplier-request-to-first-quotation time;
- quotation processing time;
- comparison preparation time;
- approval turnaround;
- requirement-to-PO time;
- supplier acknowledgement delay;
- handoff delay;
- blocker age;
- follow-ups automated;
- assistant-prepared work accepted;
- manual correction rate;
- hours saved estimate with transparent assumptions;
- supplier delivery and quality trends;
- purchase price variance where data is available.

Metrics should deep-link to supporting records.

---

# 14. Complete procurement lifecycle, canonical data contracts, and Excel test ERP

This section closes the difference between a procurement demo and an end-to-end procurement operations product.

## 14.1 Customer and procurement setup

A new customer workspace must have a guided readiness sequence:

1. company and legal entity;
2. plants, stores, gates, quality locations, and business units;
3. users, memberships, roles, reporting lines, plant access, and approval delegates;
4. currencies, exchange-rate source, tax policy, UOMs, payment terms, incoterms, and calendars;
5. item/material master and specifications;
6. supplier master, contacts, sites, capabilities, categories, compliance documents, and validity dates;
7. approval matrix, quotation-count policy, emergency/single-source policy, segregation of duties, and amount thresholds;
8. email, supplier portal, Excel/file, and ERP connections;
9. agent autonomy, provider, retention, knowledge, and notification policy;
10. readiness validation and a signed configuration summary.

The workspace must show whether each dependency is ready, incomplete, intentionally disabled, or blocked.

## 14.2 Canonical procurement record ownership

For each entity and field, store an ownership mode:

- `external_owned`: ERP/Excel is authoritative; GenuineGigs may mirror but cannot overwrite without an approved external write;
- `local_owned`: GenuineGigs is authoritative and may export the result externally;
- `mirrored`: changes may originate on either side and require version/conflict rules;
- `derived`: deterministic result calculated from source records;
- `evidence`: immutable source document or extraction evidence.

Every synchronized entity must carry connection ID, external system and record type, stable external ID/business number, source version or update time, mapping version, import/export batch, payload hash, reconciliation time, and sync state.

Never use supplier names, row positions, or display labels as the only identity key.

## 14.3 Required procurement entity coverage

### Foundation

- plants and purchasing organizations;
- users, roles, delegates, and approval limits;
- UOM, currencies, tax codes, payment terms, incoterms;
- materials/items, specifications, revisions, certificates;
- suppliers, sites, contacts, capabilities, categories, compliance status;
- inventory availability and open-demand context as read-only external context.

### Demand and sourcing

- material requirement and lines;
- demand source and production/business impact;
- supplier request/RFQ and lines;
- invitations and delivery status;
- clarifications and supplier messages;
- quotation and quotation revisions;
- extraction runs and field evidence;
- verification decisions;
- negotiation rounds;
- comparison versions;
- recommendation, award, award lines, split quantities, and justifications;
- approval requests and decisions.

### Ordering and fulfilment

- PO draft and lines;
- PO version/amendment;
- supplier issue and delivery state;
- acknowledgement and requested changes;
- ASN and dispatch documents;
- Gate entry;
- Stores receipt and receipt lines;
- Quality inspection, accepted/rejected/held quantities, certificates, and disposition;
- return, replacement, reinspection, and closure;
- inventory-impact handoff;
- supplier invoice and invoice lines;
- three-way-match result and finance exception/handoff.

### Coordination and governance

- tasks and dependencies;
- exceptions/cases;
- notifications;
- generated artifacts;
- audit and workflow transitions;
- agent proposals and receipts;
- integration outboxes, attempts, external references, and reconciliation.

## 14.4 Procurement policy engine

Make procurement policy configurable and deterministic. At minimum support:

- minimum quotation count by amount, category, plant, and urgency;
- single-source and emergency purchase justification;
- supplier eligibility and conditional-supplier approval;
- amount-based and category-based approval levels;
- segregation of requester, comparer, approver, and PO confirmer;
- technical approval when deviations exist;
- budget-check requirement where an ERP provides budget data;
- quote-validity requirements;
- allowed currency and exchange-rate policy;
- tax and landed-cost rules;
- certificate and quality requirements;
- split-award permission;
- over/under-delivery tolerance;
- receipt and inspection tolerance;
- invoice-match tolerances;
- escalation and SLA rules.

The model may explain policy. It does not calculate or override policy decisions.

## 14.5 Complete sourcing and comparison behavior

Implement deterministic support for multi-line RFQs, supplier-specific line participation, no-bid and partial-bid responses, quotation revisions, unit conversion, currencies and dated exchange rates, discounts, taxes, freight, insurance, packing, lead time, delivery schedule, validity, warranty, payment terms, technical deviations, alternate materials, certificates, supplier performance, split awards, partial quantities, and scenario comparison.

The comparison document must show assumptions, formulas, source evidence, exclusions, and unresolved uncertainty. Any user override requires a reason and approval where policy requires it.

## 14.6 PO lifecycle completeness

Support:

```text
approved award
→ PO draft
→ review
→ controlled creation
→ supplier issue
→ acknowledgement
→ requested change
→ accepted commitment
→ amendment/change order when authorized
→ fulfilment
→ closure or cancellation
```

Every amendment creates a new version, preserves the previous issued version, shows changes and commercial impact, repeats approval where required, creates a separate external action, and reconciles the acknowledged external version.

## 14.7 Inbound and exception completeness

Support full and partial delivery, multiple ASNs and receipts, shortage, excess, damage, wrong material, missing certificate, accepted/rejected/held quantities, return-to-vendor, replacement, reinspection, backorder, supplier corrective action, production-impact notification, and evidence-backed case closure.

Never collapse Gate, Stores, Quality, inventory, and finance effects into one generic “received” status.

## 14.8 Supplier invoice and finance handoff

Add a limited purchase-to-pay tail without building a finance ERP:

1. receive invoice by upload, email, supplier portal, Excel, or ERP sync;
2. validate supplier, invoice number, date, currency, tax, and duplicates;
3. extract line and charge evidence;
4. resolve PO and receipts;
5. calculate deterministic two-way or three-way match;
6. classify quantity, price, tax, freight, receipt, quality-hold, duplicate, and missing-document discrepancies;
7. route exceptions to Procurement, Stores, Quality, supplier, or Finance Reviewer;
8. create a finance-ready handoff after required approvals;
9. read external invoice/payment status where authorized;
10. never release payment or post accounting entries autonomously.

## 14.9 Excel/CSV connector role

The Excel/CSV connector is both a production connector for companies using spreadsheets or file exports and the mandatory external-system simulator for development, demos, automated testing, and ERP-adapter conformance.

PostgreSQL remains the internal durable workflow database. Excel simulates or represents the customer’s external master and transaction source.

## 14.10 Supported file formats and safety

Initial required support:

- `.xlsx`;
- `.csv`;
- a ZIP containing a declared group of CSV files.

Optional later support:

- `.xlsm` as data only with macros preserved but never executed;
- SharePoint/OneDrive synchronized workbook;
- SFTP folder synchronization.

Do not initially support legacy binary `.xls` without a sandboxed conversion dependency and security review.

Safety requirements:

- validate extension, MIME, file signature, size, sheet count, row count, and decompression limits;
- never execute macros, formulas, external links, Power Query, scripts, or embedded objects;
- use cached formula values only when available and mark formula-derived values;
- reject password-protected files unless a secure approved flow exists;
- store originals privately and immutably;
- produce a new output version instead of overwriting the original;
- prevent spreadsheet-formula injection in generated CSV/XLSX output.

## 14.11 Canonical workbook templates

Provide a versioned **GenuineGigs Procurement Exchange Workbook** with these sheets:

1. `README`
2. `Organizations`
3. `Plants`
4. `Users`
5. `ReportingLines`
6. `UOMs`
7. `Currencies`
8. `TaxCodes`
9. `Items`
10. `ItemSpecifications`
11. `Suppliers`
12. `SupplierContacts`
13. `SupplierCapabilities`
14. `InventorySnapshot`
15. `Requirements`
16. `RequirementLines`
17. `OpenPOs`
18. `OpenPOLines`
19. `Receipts`
20. `ReceiptLines`
21. `QualityStatus`
22. `Invoices`
23. `InvoiceLines`
24. `PaymentStatus`
25. `RFQExport`
26. `ComparisonExport`
27. `POExport`
28. `ExceptionExport`
29. `SyncLog`

Every sheet defines required and optional columns, data type, stable external key, allowed values, examples, ownership direction, validation rules, and mapping version.

## 14.12 Excel mapping wizard

The Integration Control Centre must provide:

1. upload/select file;
2. detect sheets, headers, sample values, dates, currencies, and likely record types;
3. select a standard template or create a mapping profile;
4. map source columns to canonical fields;
5. define transforms, defaults, lookups, and reference resolution;
6. identify missing required fields;
7. preview insert/update/unchanged/conflict/error counts;
8. inspect row-level errors;
9. save a versioned mapping profile;
10. execute a dry run;
11. commit an approved import;
12. produce an import report and reconciliation summary.

The assistant may suggest mappings. The user confirms mappings that alter business meaning.

## 14.13 Import model and lineage

Reuse existing integration models where possible. Add only missing concepts such as connector definition/manifest, connection capability, mapping profile/version, import batch, import row result, export batch, file artifact version, external record state, and conflict linkage.

Each row result records source file, workbook version, sheet, one-based row, source external key, normalized payload hash, action, canonical entity and ID, validation messages, mapping version, and correlation ID.

## 14.14 Idempotent import and incremental sync

Rules:

- the same file and mapping cannot create duplicate records;
- the same external key updates or reconciles the same scoped entity;
- unchanged rows are skipped;
- deleted source rows do not automatically delete canonical records;
- explicit deletion/inactivation policy is required;
- stale versions create conflicts rather than overwriting newer data;
- master-data conflicts are reviewed before dependent transaction import;
- imports are chunked and resumable;
- failed rows do not corrupt independent successful rows;
- batch status distinguishes previewed, approved, running, partially completed, completed, failed, and safely rolled back.

## 14.15 Controlled Excel write-back

Support three modes:

1. **Import-only**;
2. **Export package** for customer review/manual import;
3. **Managed workbook round trip** using stable keys and a new version.

Write-back must never edit the only customer copy in place. Generate a new version with a manifest, change summary, approved fields, business numbers, status, timestamps, correlation IDs, reconciliation sheet, and formula-injection protection. Preserve unknown sheets and unmapped columns where technically safe.

## 14.16 Golden Excel ERP fixture

Create a deterministic fixture pack:

```text
tests/fixtures/excel_erp/
  genuinegigs_procurement_exchange_v1.xlsx
  mapping_profile_v1.json
  expected_import_summary.json
  expected_export_summary.json
  malformed/
  conflicts/
  revisions/
```

The golden workbook includes at least two plants, users and reporting lines, UOM/currency examples, ten materials, six suppliers and capabilities, inventory context, open/completed requirements, open POs, partial receipts, a quality hold, invoices, and payment status. Negative fixtures contain invalid, ambiguous, duplicate, stale, and hostile spreadsheet data.

## 14.17 Excel-driven end-to-end acceptance scenario

The complete product must pass this scenario without a live ERP:

1. Admin creates a clean workspace.
2. Integration Admin uploads the golden workbook.
3. Mapping preview shows valid, invalid, unchanged, and conflict rows.
4. Admin fixes or excludes invalid rows and commits import.
5. Plant Manager asks for material/inventory context and creates a requirement.
6. Purchase Executive prepares and sends the supplier request through simulated email/portal.
7. Supplier quotations arrive as PDF/XLSX/email fixtures.
8. Purchase Manager verifies extraction, compares, negotiates or selects, and requests approval.
9. Plant Manager approves.
10. Purchase Manager creates the PO.
11. PO and status export to a new workbook version.
12. Supplier acknowledgement and partial delivery import from workbook/email fixtures.
13. Gate, Stores, and Quality complete their steps.
14. A rejected quantity is returned and replaced.
15. A supplier invoice is uploaded and three-way matched.
16. Final procurement, receipt, quality, invoice-handoff, task, audit, and reconciliation states export.
17. Re-importing the same external data creates no duplicates.
18. A stale changed row produces a conflict and never silently overwrites newer data.

This is the minimum integration proof before claiming the procurement product is end-to-end complete.

---

# 15. Universal ERP, file, email, and cross-system integration platform

## 15.1 Connector design objective

Procurement business logic must never contain vendor-specific SAP, Oracle, Dynamics, Odoo, Excel, or SFTP branches. Every connector implements a common protocol and advertises a tested capability manifest. Canonical services create business actions; connectors translate, dispatch, verify, and reconcile external effects.

## 15.2 Connector capability manifest

Each connection exposes provider, adapter version, schema version, environment, authentication methods, supported record types, read/write capabilities, incremental-sync and webhook support, attachment support, preflight, idempotency, read-after-write, reconciliation, reversal/compensation, rate limits, known limitations, and verified contract tests.

The Integration Control Centre and permission engine use this manifest. Unsupported actions are never shown merely because a generic route exists.

## 15.3 Standard connector operations

Applicable operations:

```text
get_manifest()
test_connection()
list_scopes()
discover_schema(record_type)
read_record(record_type, external_id)
search_records(record_type, filters, cursor, limit)
pull_changes(record_type, cursor)
validate_mapping(record_type, mapping_profile)
normalize_external_record(record_type, payload)
prepare_write(operation, canonical_record, mapping_profile)
preflight_write(operation, external_state, payload)
dispatch_write(operation, payload, idempotency_key)
read_write_result(external_reference)
reconcile(canonical_record, external_record)
reverse_or_prepare_compensation(external_reference)
health()
disable()
```

Use existing integration abstractions where they fit. Do not duplicate outbox, attempts, references, or reconciliation models.

## 15.4 Supported connectivity patterns

- official vendor APIs with customer-approved service accounts;
- configurable REST/OpenAPI with allowlisted endpoints and schemas;
- OData with entity sets, filters, selects, pagination, ETags, and typed mapping;
- SOAP through allowlisted WSDL operations;
- XLSX/CSV upload and scheduled SFTP pull/push;
- customer-hosted outbound-only bridge for private networks;
- middleware/iPaaS webhook or polling contracts.

The model never receives arbitrary HTTP, WSDL operations, database access, or credentials.

## 15.5 Canonical synchronization directions

### External system to GenuineGigs

Support organizations/plants, users/directory references, UOM/currencies/taxes/payment terms, materials/specifications, suppliers/sites/contacts/capabilities, inventory and demand context, requirements, open POs/amendments, acknowledgements, ASNs, receipts, inspection status, invoices, and payment status where permitted.

### GenuineGigs to external system

Potential controlled writes include requisition/requirement draft, RFQ where supported, approved award/reference, PO draft or approved PO, PO amendment/cancellation request, document attachment, receipt/inspection handoff, invoice-match/exception handoff, and workflow reference/status.

Every capability is enabled independently. Read permission never implies write permission.

## 15.6 Mapping engine

A versioned mapping profile supports source/target record type, field and line mapping, required fields, defaults, enum/code maps, UOM/currency/tax transformations, date/time rules, plant mapping, identity resolution, reference lookups, conditions, null policy, precision/rounding, ownership, validations, and effective dates.

Mapping changes require impact preview, production approval, and regression tests using sanitized fixtures.

## 15.7 Synchronization engine

Implement initial full import, incremental cursor sync, webhook ingestion, scheduled polling, manual sync, resumable batches, checkpoints, rate-limit handling, retry/backoff, dead letters, duplicate suppression, deletion/inactivation policy, and observability. Every excluded, failed, or conflicting record is countable and inspectable.

## 15.8 Write safety pipeline

```text
Canonical approved action
→ connection/capability check
→ role/authority check
→ mapping and scope check
→ fresh external state
→ business/field validation
→ version or ETag check
→ deterministic payload
→ payload hash and semantic idempotency key
→ shadow/preflight result
→ explicit approval where required
→ integration outbox
→ adapter dispatch and attempt
→ external reference
→ read-after-write verification
→ reconciliation
→ notification, audit, or exception
```

No UI or agent code directly calls vendor APIs.

## 15.9 Connection modes

1. disconnected/demo;
2. file import-only;
3. read-only synchronization;
4. shadow write;
5. UAT write;
6. limited production write;
7. expanded production write;
8. emergency disabled.

Mode changes are audited and may require security-owner approval.

## 15.10 Integration Control Centre

Show provider and adapter version, environment, mode, health, latency, last read/write/reconciliation, enabled plants/business units, capability scopes, mapping versions, sync cursors and queue age, imports/exports, shadow payloads, dispatches, failures, dead letters, mismatches, credential expiry without secrets, rate-limit state, emergency disable, and downloadable acceptance report.

## 15.11 Reference adapter priorities

### Excel/CSV

Production quality and the integration simulator/acceptance baseline.

### Generic REST/OpenAPI

Pass common conformance tests and support customer mappings without procurement-code changes.

### Generic OData

Pass read, pagination, ETag, preflight, write, and reconciliation tests against a local test server.

### Oracle Fusion Procurement

Complete only the resources required for the pilot. Use OAuth client credentials, business-unit scope, payload contracts, mocked provider tests, UAT acceptance, idempotency, and reconciliation. Do not generalize beyond verified resources.

### SAP S/4HANA

Use supported APIs/OData/BAPI/IDoc through approved architecture. Provide manifest, mapping pack, mocked tests, and UAT process. Do not claim live write until a customer sandbox passes.

### Microsoft Dynamics 365

Provide the mapping/reference adapter for the customer’s Finance and Supply Chain or Business Central edition through supported APIs/OData.

### Odoo

Provide a reference adapter for products, vendors, sourcing/PO, receipts, and status through approved APIs.

### Legacy and SME ERPs

Connect through Excel/CSV, SFTP, generic API, middleware, or customer bridge. Build dedicated adapters only from validated demand.

## 15.12 Connector conformance and certification pack

Every adapter passes manifest completeness, authentication/rotation, scope, pagination/incremental sync, mapping/precision, stable identity, duplicate event/write, timeout before and after commit, idempotent retry, stale-version conflict, partial success, rate limit, malformed response, read-after-write, mismatch, compensation behavior, credential redaction, kill switch, observability, and audit.

Generate an acceptance report containing adapter and mapping versions, test data, date, environment, supported capabilities, limitations, and results.

## 15.13 Email and document integration

Support an inbound procurement mailbox/provider connector, message threading, supplier/contact resolution, outbound RFQ/PO delivery, inbound quotation/acknowledgement/ASN/certificate/invoice attachments, validation/quarantine, bounded association confirmation, delivery/bounce/failure state, templates, sender policy, retention, and redaction.

Email ingestion creates the same canonical records as portal or manual upload.

## 15.14 Supplier portal integration

Use secure scoped expiring tokens for RFQ view, clarification, quotation/no-bid/revision, PO acknowledgement/requested change, ASN/delivery update, certificate upload, invoice upload, and supplier-only status visibility.

## 15.15 Cross-system work graph foundation

Create typed links across material/specification/supplier capability, requirement/demand source, RFQ/invitation/quotation, comparison/award/approval, PO/acknowledgement/ASN/receipt/inspection, invoice/PO/receipt/match exception, and record/task/owner/blocker/next role.

Later connect PLM, MES, QMS, CMMS, HR directory, and finance status without changing procurement’s canonical workflow.

## 15.16 Integration rollout sequence

1. sanitized fixture mapping;
2. Excel/file or API read-only connection;
3. mapping and data-quality review;
4. read-only shadow operation;
5. shadow-write payload comparison;
6. UAT with customer-owned cases;
7. limited production write;
8. daily reconciliation and exception review;
9. measured expansion;
10. recertification after adapter, ERP, or mapping changes.

---

# 16. Knowledge and company policy

## 16.1 Knowledge sources

Support approved, versioned knowledge:

- procurement SOPs;
- approval matrix;
- supplier eligibility rules;
- material specifications;
- certificate requirements;
- tax and commercial policy;
- emergency purchase policy;
- quality inspection instructions;
- ERP integration playbook;
- company communication templates.

## 16.2 Retrieval policy

- enforce tenant and plant scope;
- enforce document visibility;
- return citations;
- prefer current approved version;
- mark superseded knowledge;
- do not treat uploaded supplier documents as policy instructions;
- do not allow document prompt injection to alter tools or authority;
- log source IDs, not hidden chain-of-thought.

## 16.3 Knowledge answers

The assistant should answer:

- why a supplier is ineligible;
- what certificates are required;
- who can approve a value;
- why a quote was disqualified;
- what the next workflow step is;
- which specification revision applies;
- how to handle a documented exception.

It must clearly state when policy data is missing.

---

# 17. Security, privacy, and trust work

## 17.1 Product controls to complete

- uniform tenant/plant scoping review;
- server-side authorization on every new route/tool;
- uniform CSRF on unsafe browser requests;
- semantic idempotency for external effects;
- wider optimistic concurrency coverage;
- secret-reference storage and rotation workflow;
- log redaction;
- configurable retention and deletion;
- audit export;
- anti-malware integration for uploads;
- content classification;
- model-input redaction and minimization;
- provider data-policy configuration;
- emergency agent and integration kill switches;
- backup/restore runbook;
- incident response runbook;
- dependency/container scanning;
- penetration-test preparation.

## 17.2 Do not overclaim

Do not claim without evidence:

- SOC 2;
- ISO 27001 certification;
- GDPR/DPDP compliance;
- completed penetration testing;
- zero data retention;
- full Oracle certification;
- live SAP support;
- universal ERP rollback;
- production disaster recovery.

## 17.3 Model privacy

Before each provider call:

- classify data;
- select only needed context;
- redact credentials/secrets;
- exclude unrelated records;
- avoid entire documents where extracted sections suffice;
- record provider/model/prompt/policy version;
- support agent-disabled/manual mode;
- support future private-model deployment through the same provider abstraction.

---

# 18. Code organization changes

These are targeted refactors, not rewrites.

## 18.1 Backend priorities

### `agent_service.py`

Reduce responsibilities gradually after tests protect behavior.

Target modules:

- `agent_context.py` — build scoped context;
- `agent_tools.py` — tool schemas and adapter registry;
- `agent_adapters/` — domain adapters by workflow;
- `agent_response.py` — grounded business response composition;
- existing `agent_runtime.py` — live bounded loop;
- existing `agent_state.py` — sole state gateway;
- existing `agent_resolution.py` — shared resolution.

Do not create all files empty. Extract only while moving live behavior and tests.

### `domains/workflows.py` and `procurement_v2.py`

Create a documented canonical-service map per lifecycle stage. Resolve overlap without changing contracts unnecessarily.

Example:

| Stage | Canonical service module |
|---|---|
| Requirement | `domains/workflows.py` |
| RFQ draft/update/publish | selected canonical functions in `domains/workflows.py` |
| Artifacts | `procurement_v2.py` |
| Quote extraction | `documents.py` plus workflow verification service |
| Comparison | one documented V2 comparison service |
| Approval | one documented V2 approval service |
| PO | one documented V2 PO service |
| Inbound | canonical workflow service |

Add service-level tests before retiring aliases.

### `main.py`

Do not broadly rewrite. Move route bodies to existing/new routers only when working on that route and preserving OpenAPI paths.

### `backend_plan.py`

Rename only after caller and contract audit. Its historical name is confusing but not a priority before product reliability.

## 18.2 Frontend priorities

### `IndustrialConsole.tsx`

Split incrementally into:

- `AppShell`;
- `SidebarNavigation`;
- `WorkspaceHeader`;
- `NotificationMenu`;
- `AssistantPanel` wrapper;
- data hooks/query refresh layer;
- route-specific screen components.

### `WorkflowForms.tsx`

Split by domain only after tests protect each workflow:

- requirements;
- RFQ;
- quotations/evidence;
- comparison/approvals;
- PO;
- inbound/quality;
- integrations/admin.

### API client

After backend contracts stabilize, converge manual types toward the generated OpenAPI client. Do not hand-edit `api.generated.ts`.

## 18.3 Allowed dependencies

Prefer no new runtime dependencies. Add a dependency only if:

- the existing stack cannot reasonably provide the function;
- it is actively maintained;
- licensing is acceptable;
- security impact is reviewed;
- bundle/runtime impact is documented;
- tests justify it.

---

# 19. Implementation phases

The phases below are ordered. Each phase ends with a mandatory gate.

## Phase 0 — Establish the factual baseline

**Goal:** resolve the handoff contradiction and lock the current behavior before changing architecture.

### Tasks

1. Inspect `run_message` and determine whether `agent_runtime.run_bounded_tool_loop` is live.
2. Determine whether all state writes use `AgentThreadStateV2`.
3. Generate a registry-to-adapter completeness report.
4. Identify every capability still routed through `AgentTurnDecision`.
5. Identify every “not implemented yet” branch reachable by a declared capability.
6. Identify canonical service ownership for requirement, RFQ, quote, comparison, approval, PO, and inbound.
7. Run current API, deterministic agent, typecheck, build, OpenAPI, and Playwright tests.
8. Run the literal RFQ failure transcripts against the API/test server.
9. Capture baseline screenshots of My Work, assistant, requirement, RFQ, quote review, comparison, approval, PO, Gate, Stores, and Quality.
10. Record Docker and live Groq availability separately.

### Deliverable

Create `docs/architecture/current-runtime-truth.md` containing only verified findings, affected files, and current test results.

### Gate

- baseline tests recorded;
- literal transcript tests exist;
- runtime integration status proven from code/test, not inferred from filenames;
- no behavior change yet except required regression fixtures.

---

## Phase 1 — Make typed state and resolution authoritative

**Goal:** remove inconsistent entity and conversation handling.

### Tasks

1. Make `AgentThreadStateV2` the sole state mutation gateway.
2. Add schema loading/migration for old thread state.
3. Replace direct handler JSON mutations with state API calls.
4. Standardize recent-entity storage.
5. Standardize selected page/work-item context.
6. Implement topic-change clearing rules.
7. Standardize exact ID, business number, selected, recent, latest, and candidate resolution.
8. Improve material/assignee resolution and candidate labels.
9. Add tests for:
   - `it` and `its ID`;
   - latest requirement;
   - exact requirement/RFQ/PO numbers;
   - topic switch Copper → Aluminium;
   - explicit correction;
   - ambiguous candidates;
   - cross-scope denial;
   - relative date and quantity/UOM normalization.

### Gate

- no live state writes outside state module, except documented migration/bootstrap code;
- all resolver tests pass;
- existing workflows unchanged;
- no cross-scope candidate leakage.

---

## Phase 2 — Complete typed adapters

**Goal:** every advertised role capability has one correct canonical adapter.

### Tasks

1. Create an adapter registry keyed by capability ID.
2. Enforce declared required/optional arguments through typed schemas.
3. Remove mappings from modern capabilities to incompatible legacy intents.
4. Implement missing direct adapters for all required procurement/inbound skills.
5. Ensure one receipt for every successful mutation.
6. Ensure controlled actions create proposals rather than effects.
7. Ensure adapters return compact `ToolResult` observations.
8. Add registry completeness test:
   - every enabled capability has adapter;
   - role policy matches adapter;
   - no declared capability reaches “not implemented yet.”
9. Add adapter authorization, idempotency, and scope tests.

### Gate

- 100% enabled capability-to-adapter coverage;
- zero modern capabilities use legacy task-context gates;
- no mutation succeeds without receipt;
- controlled actions stop at proposal.

---

## Phase 3 — Activate the bounded multi-tool runtime

**Goal:** make the live assistant compositional rather than one-shot.

### Tasks

1. Integrate `run_bounded_tool_loop` into `run_message` behind a tenant/runtime feature flag.
2. Supply only role-authorized tools.
3. Persist tool observations, events, checkpoints, calls, and termination reason.
4. Enforce limits at each iteration.
5. Stop after first mutation or controlled proposal.
6. Add compact tool observations.
7. Keep deterministic parsing only for normalization and explicitly enabled provider-outage fallback.
8. Add safe fallback behavior:
   - unambiguous reads may continue;
   - unambiguous low-risk canonical mutations only if policy explicitly permits;
   - otherwise explain provider unavailability and preserve manual path.
9. Shadow-run old and new routing in test/dev where useful, without duplicate mutation.
10. Roll out feature flag to demo workspace after evaluation passes.

### Required multi-step tests

- latest requirement → resolve → inspect state → prepare RFQ;
- attached quotes → resolve RFQ/supplier → start extraction;
- comparison request → inspect quote eligibility → identify blockers or generate;
- “why is this blocked?” → resolve record → workflow state → answer;
- manager update → resolve task/owner → create follow-up;
- one mutation maximum;
- proposal stops loop;
- timeout/budget termination;
- unauthorized tool rejected;
- prompt injection in uploaded document ignored.

### Gate

- live `run_message` uses bounded runtime for enabled tenants;
- deterministic evaluation success target at least 95%;
- zero false mutation claims;
- zero unauthorized/cross-scope actions;
- old path remains available only behind explicit rollback flag until later removal.

---

## Phase 4 — Complete core procurement agent skills

**Goal:** make procurement useful end to end through conversation.

### Vertical slices

Implement and verify in this order:

1. requirement creation and missing-material continuation;
2. RFQ preparation, editing, review, and send proposal;
3. quotation attachment upload and extraction state;
4. field verification;
5. comparison and explanation;
6. approval proposal/decision;
7. PO preparation and controlled creation;
8. supplier communication and acknowledgement;
9. Gate, Stores, and Quality assistance;
10. exception resolution and status questions.

Each slice must include:

- natural conversation;
- selected-page action;
- direct canonical adapter;
- receipt/proposal;
- manual workbench deep link;
- task and notification updates;
- API tests;
- browser test;
- business result card.

### Gate

- complete requirement-to-quality assistant demo passes for every role;
- assistant-created records appear in manual screens;
- no duplicate agent-only records;
- all controlled actions remain controlled.

---

## Phase 5 — Simplify manual workbenches

**Goal:** make manual procurement understandable without backend vocabulary.

### Tasks

1. Implement requirement contextual list/detail/create flow.
2. Replace RFQ panel with requirement-scoped stepper.
3. Centralize RFQ send action.
4. Implement quotation evidence workbench.
5. Implement comparison state sequence.
6. Centralize approval action.
7. Implement PO state sequence.
8. Improve Gate, Stores, and Quality context.
9. Replace generic raw tables.
10. Add autosave and recoverable errors.
11. Synchronize selected page context with assistant.
12. Refresh records, tasks, notifications, and badges after mutations.

### Gate

- one primary action per state;
- no raw UUID/JSON/internal noun in normal workflow surfaces;
- manual end-to-end browser flow passes on desktop/tablet/mobile;
- assistant and manual deep links select the same record.

---

## Phase 6 — Redesign My Work and assistant shell

**Goal:** make the product look and behave like an AI operations workspace.

### Tasks

1. Implement compact navigation.
2. Implement persistent desktop assistant and responsive drawer.
3. Replace oversized generic metrics with concise actionable summaries.
4. Implement Needs your attention.
5. Implement Assistant prepared.
6. Implement My tasks.
7. Implement Waiting on others.
8. Implement Team follow-ups.
9. Add notification bell and navigation badges.
10. Hide technical agent/runtime language.
11. Add role-specific empty, loading, permission, offline, and error states.
12. Apply design tokens and reusable semantic components.
13. Meet accessibility and responsive requirements.

### Visual acceptance at 1440×900

- no large unused right-side region;
- assistant composer visible;
- at least one actionable item fully visible above fold;
- no generic process rail dominating homepage;
- no more than three major above-fold sections;
- compact sidebar;
- business terminology only.

### Gate

- screenshot tests approved at required viewports;
- axe/accessibility critical checks pass;
- no horizontal overflow;
- client demo flow can be completed without exposing internal concepts.

---

## Phase 7 — Coordination, notifications, and proactive procurement

**Goal:** demonstrate the future management and coordination value.

### Tasks

1. Implement semantic task idempotency and duplicate reconciliation.
2. Enrich task identity with business context.
3. Implement governed manager follow-ups.
4. Implement task update response capture.
5. Implement deduplicated proactive rules:
   - quotation deadline approaching;
   - insufficient quotations;
   - extraction review pending;
   - quote validity expiring;
   - approval overdue;
   - PO acknowledgement overdue;
   - delivery late/at risk;
   - Gate/Stores/Quality handoff overdue;
   - quality hold/rejection;
   - integration failure.
6. Add morning brief.
7. Add end-of-day unresolved-work check.
8. Add sourced manager summary.
9. Add notification preferences without allowing users to bypass required alerts.

### Gate

- manager follow-up is persisted and scoped;
- proactive alerts are deduplicated;
- factual summaries cite records and timestamps;
- no hidden autonomous approval or employee scoring.

---

## Phase 8 — Build the Excel/CSV external-system connector and test ERP

**Goal:** make Excel/CSV a first-class production connector and the deterministic external system for all integration acceptance tests.

### Tasks

1. Inspect existing import, document, outbox, external-reference, and reconciliation models; reuse them before adding schema.
2. Define connector manifest, mapping profile, import batch, row result, export batch, and external ownership contracts.
3. Implement `.xlsx`, `.csv`, and ZIP-of-CSV validation and parsing.
4. Create the versioned Procurement Exchange Workbook and schema documentation.
5. Implement workbook discovery and mapping preview APIs.
6. Implement mapping wizard UI with row-level errors and dry run.
7. Implement stable external IDs, source lineage, hashes, and idempotent upsert.
8. Implement incremental re-import, unchanged-row skip, conflict detection, and explicit inactivation policy.
9. Implement export package and managed-workbook round-trip modes.
10. Preserve original files and create new output versions.
11. Add formula/macro/link safety and CSV formula-injection protection.
12. Build golden, malformed, conflict, revision, and scale fixture workbooks.
13. Add Excel-driven clean-workspace bootstrap.
14. Add Excel assistant capabilities for mapping explanation, import preview, errors, export, and reconciliation.
15. Implement the complete Excel-driven end-to-end acceptance scenario from Section 14.17.

### Gate

- clean workspace can be configured from the golden workbook;
- re-import is idempotent;
- invalid rows are isolated and explained;
- stale changes create conflicts;
- a complete requirement-to-quality-to-invoice-handoff cycle runs without a live ERP;
- approved outputs export to a new workbook version;
- reconciliation proves expected external/canonical state;
- no macros/formulas are executed;
- no raw credentials or unnecessary file content reach the LLM.

---

## Phase 9 — Build the universal connector SDK and Integration Control Centre

**Goal:** ensure every ERP, file, middleware, email, and customer-bridge adapter uses one safe protocol.

### Tasks

1. Create or consolidate the connector interface and capability manifest.
2. Create adapter registry and provider/version discovery.
3. Implement generic connection modes and capability permissions.
4. Implement versioned mapping profiles and transform validation.
5. Implement initial, incremental, scheduled, webhook, and manual sync orchestration.
6. Implement common import/export/outbox/attempt/external-reference/reconciliation services.
7. Implement preflight, current-state read, concurrency, semantic idempotency, read-after-write, and compensation hooks.
8. Implement retry, rate-limit, dead-letter, partial-success, and kill-switch behavior.
9. Build Integration Control Centre UI.
10. Build connector conformance suite and generated acceptance report.
11. Add customer-hosted bridge protocol and reference simulator.
12. Add generic REST/OpenAPI, OData, and SFTP/file reference connectors.
13. Ensure assistant/manual actions only use canonical services and integration proposals.

### Gate

- every enabled connection advertises only tested capabilities;
- Excel, generic REST test server, OData test server, and SFTP fixture pass the same conformance suite;
- shadow write shows deterministic payload and consequences;
- duplicate, timeout, and stale-version tests do not create duplicate external effects;
- Control Centre can disable a connection immediately;
- failures never appear as successful business actions.

---

## Phase 10 — Complete reference ERP, email, and supplier-channel adapters

**Goal:** prove that procurement can connect to real enterprise patterns while keeping claims accurate.

### Tasks

1. Complete Oracle Fusion procurement scope already represented in the repository.
2. Add mocked contract tests and customer-UAT checklist for Oracle.
3. Complete SAP adapter protocol/mapping implementation to a clearly declared scope.
4. Add SAP mocked contract suite and sandbox acceptance checklist; keep live write disabled until accepted.
5. Add Dynamics 365 mapping/reference adapter for the selected customer edition.
6. Add Odoo reference adapter.
7. Add SMTP/IMAP or provider-based email adapter with inbound attachment association.
8. Add outbound RFQ/PO delivery status, bounce/failure, retry, and reconciliation.
9. Complete supplier portal quotation, revision, acknowledgement, ASN, certificate, and invoice flows.
10. Add connector acceptance-report UI and downloadable evidence pack.
11. Add customer-specific mapping override without forking procurement services.
12. Add secret provisioning, rotation, expiry alert, and no-secret logging tests.

### Gate

- Excel remains the baseline connector and all reference adapters pass common conformance tests;
- Oracle supported scope passes mocked and available UAT tests;
- SAP, Dynamics, and Odoo claims exactly match tested capability manifests;
- email ingestion creates the same canonical records as upload or portal;
- portal and email access are tenant and supplier scoped;
- no adapter bypasses approval, outbox, verification, or reconciliation.

---

## Phase 11 — Complete remaining procurement domain capabilities

**Goal:** close every domain gap required for an end-to-end procurement operations product.

### Tasks

1. Complete multi-line and partial supplier bids.
2. Complete quotation revisions and supersession.
3. Complete deterministic landed-cost and multi-currency normalization.
4. Complete split awards and partial quantities.
5. Complete configurable procurement policy and approval matrix.
6. Complete supplier onboarding, capability, certificate, and compliance readiness.
7. Complete PO amendments, cancellation, and versioned supplier reissue.
8. Complete partial delivery, backorder, return, replacement, and reinspection.
9. Complete supplier performance and corrective-action workflows.
10. Add invoice upload/extraction, duplicate detection, deterministic two/three-way match, exception routing, and finance handoff.
11. Add read-only invoice/payment-status integration.
12. Add all corresponding role assistant tools, workbenches, tasks, notifications, artifacts, audit, and tests.
13. Add lifecycle closure rules and remaining-quantity reconciliation.

### Gate

- multi-line, split, partial, and amended scenarios pass;
- no issued version is silently modified;
- invoice match is deterministic and evidence-backed;
- no payment or journal action exists in assistant autonomy;
- all exception states have owner, next action, evidence, and closure path.

---

## Phase 12 — Knowledge, analytics, customer configuration, and management coordination

**Goal:** make the product adaptable, measurable, and aligned with the long-term agentic operations vision.

### Tasks

1. Add approved SOP/policy ingestion and source citations.
2. Add configuration for roles, reporting lines, delegates, approval limits, plants, categories, procurement policies, follow-ups, escalation, communication templates, autonomy, integrations, and retention.
3. Add supplier scorecards and risk explanations.
4. Add cycle-time, savings, workload, blocker-age, supplier, integration, and agent-quality metrics.
5. Add morning brief, end-of-day check, and sourced manager summary.
6. Add governed manager follow-up through persisted tasks/delegations.
7. Add event-driven proactive procurement alerts from workflow, document, email, Excel, and ERP changes.
8. Add customer readiness checklist and configuration export.
9. Ensure fresh customer workspaces contain no demo transactions.
10. Add evidence deep links for every metric and management statement.

### Gate

- a new workspace reaches a measurable readiness state;
- management summaries are factual and sourced;
- no opaque employee score is generated;
- configuration changes are audited;
- analytics reconcile with source records.

---

## Phase 13 — Production hardening and controlled pilot release

**Goal:** prepare a credible customer deployment with Excel first and real ERP progression.

### Tasks

1. uniform authorization, tenant, plant, supplier-token, and reporting-scope audit;
2. CSRF, idempotency, concurrency, and external semantic-idempotency coverage audit;
3. document and spreadsheet anti-malware and hostile-content testing;
4. log, trace, attachment, and provider-payload redaction;
5. retention, deletion, export, and legal-hold controls as required;
6. provider privacy configuration and subprocessor documentation;
7. backup, restore, and point-in-time recovery test;
8. incident-response, connector-disable, and manual-continuity drills;
9. dependency, image, container, and secret scans;
10. external penetration-test preparation and remediation process;
11. observability dashboards for API, agent, document, task, email, connector, outbox, and reconciliation;
12. feature-flag rollout and rollback documentation;
13. customer data-flow, permission matrix, connector manifest, mapping, and acceptance documents;
14. curated live Groq evaluation with every external write disabled;
15. Excel-only pilot acceptance;
16. read-only ERP pilot acceptance;
17. shadow-write and UAT acceptance;
18. limited production-write acceptance for one approved workflow;
19. support, SLA, escalation, and customer-success runbook.

### Gate

- no critical known security defect;
- backup and restore evidence exists;
- Excel-only end-to-end pilot passes;
- read-only and shadow modes pass with customer-like data;
- live-provider evaluation is recorded with model and prompt versions;
- supported connector claims are evidence-backed;
- manual workflows remain available during provider or connector failure;
- limited write can be disabled and reconciled without data ambiguity;
- release and rollback runbooks are tested.

---

# 20. Test and evaluation programme

## 20.1 Required automated suites

### Agent natural-language evaluation

Minimum 150 cases covering:

- normal phrasing;
- terse commands;
- spelling errors;
- Hinglish and common workplace wording where supported;
- item codes/names;
- relative dates;
- recent references;
- selected-page context;
- topic changes;
- ambiguous records;
- attachment workflows;
- missing material;
- existing RFQ idempotency;
- insufficient capable suppliers;
- extraction blockers;
- comparison blockers;
- controlled actions;
- authorization;
- provider failure;
- prompt injection;
- duplicate requests;
- integration failure;
- manager follow-up.

Required thresholds before pilot:

- deterministic/mock task success: at least 95%;
- live provider end-to-end success: at least 85%;
- false success claims: 0;
- unauthorized actions: 0;
- cross-tenant/plant disclosure: 0;
- uncontrolled commercial/ERP actions: 0;
- normal resolvable requests requiring more than one clarification: less than 5%;
- raw internal dump responses: 0.

## 20.2 Workflow tests

Cover:

- valid and invalid state transitions;
- task semantic idempotency;
- duplicate request replay;
- stale `If-Match`;
- comparison version isolation;
- approval version isolation;
- outbox retry and duplicate dispatch;
- external references;
- reconciliation mismatch;
- Gate → Stores → Quality ordering;
- quantity constraints;
- document scope/download;
- supplier token expiry.

## 20.3 Frontend tests

Cover:

- My Work above-fold content;
- notification and nav badges;
- assistant attachments;
- proposal confirmation;
- agent error recovery;
- deep-link selected context;
- RFQ stepper;
- quotation evidence review;
- comparison/approval sequence;
- PO sequence;
- Gate/Stores/Quality;
- workspace switching;
- responsive drawer/nav;
- keyboard/focus;
- contrast/axe;
- offline/provider-disabled manual path.

Required screenshot viewports:

- 1440×900;
- 1280×800;
- 1024×768;
- 768×1024;
- 390×844.

## 20.4 Excel and connector acceptance tests

Required Excel/file tests:

- standard workbook import;
- arbitrary customer headers through a saved mapping;
- missing required sheet or column;
- duplicate external keys;
- duplicate file upload;
- unchanged re-import;
- incremental update;
- stale update conflict;
- cross-plant key collision;
- invalid dates, decimals, UOM, currency, tax, and enum codes;
- formulas and macro-bearing files treated as untrusted data;
- CSV formula-injection prevention;
- large workbook chunking and resume;
- partial row failure;
- export version generation;
- unknown sheet and column preservation;
- round-trip reconciliation;
- no destructive overwrite;
- complete golden-workbook procurement scenario.

Required connector conformance tests:

- manifest and capability truth;
- authentication and rotation;
- scope and field allowlist;
- full and incremental read;
- pagination and cursors;
- webhook duplicate suppression;
- mapping and version changes;
- preflight;
- idempotent write retry;
- timeout before commit;
- timeout after external commit;
- external duplicate prevention;
- stale ETag/version conflict;
- partial provider success;
- rate limit and backoff;
- malformed response;
- read-after-write;
- reconciliation mismatch;
- compensation/reversal preparation;
- emergency disable;
- secret and payload redaction.

Required end-to-end external-source matrices:

1. Excel-only source and write-back;
2. generic REST test ERP;
3. generic OData test ERP;
4. local simulated ERP;
5. mocked Oracle;
6. mocked SAP, Dynamics, and Odoo mapping contracts;
7. email plus supplier portal ingestion;
8. provider and connector outage with manual continuity.

## 20.5 Standard verification commands

Run from repository root unless the project scripts specify otherwise:

```bash
git status --short
git diff --check
npm run typecheck
npm run build:web
npm run check:api-contract
npm run test:api
npm run test:e2e
```

When Docker is working:

```bash
docker compose up --build -d
docker compose ps -a
docker compose logs --tail=200 api worker beat web postgres redis minio
```

After schema changes:

```bash
# create a new migration; never edit applied migrations
# upgrade disposable and production-like test databases
# regenerate API client only after backend schema stabilizes
npm run generate:api
npm run check:api-contract
```

Run live Groq scorecard separately with ERP live writes disabled.

---

# 21. Client-demo acceptance script

The release is not complete until this script works without developer intervention.

## Demo setup

- one clean workspace with no transactional seed data;
- all standard role accounts can select the workspace;
- Excel/CSV connector enabled in import/export mode;
- golden Procurement Exchange Workbook available;
- simulated supplier email and portal clearly labelled;
- live ERP writes disabled;
- role assistants enabled;
- prepared quotation, acknowledgement, ASN, certificate, and invoice fixtures.

## Scenario 0 — Bootstrap from Excel

Integration Admin uploads the golden workbook.

Expected:

- workbook and sheet discovery succeeds;
- mapping profile is selected or confirmed;
- insert/update/unchanged/conflict/error preview is shown;
- row-level validation is understandable;
- approved rows import with source lineage;
- materials, suppliers, capabilities, users, plants, inventory context, open POs, receipts, and invoice context become visible;
- invalid rows remain isolated;
- importing the same workbook again creates no duplicates;
- Integration Control Centre shows import and reconciliation status.

## Scenario 1 — Plant Manager creates work

User:

> We need 100 KG Aluminium Ingot one month from today. Create the requirement and assign it to Meera.

Expected:

- correct material resolved from imported master data;
- current inventory/open-demand context is available when authorized;
- exact date displayed;
- canonical requirement created;
- real requirement number returned;
- Meera task created once;
- requirement visible in manual screen;
- assistant remembers it.

Follow-up:

> What is its ID?

Expected: same business number immediately.

## Scenario 2 — Purchase Executive prepares supplier request

User:

> Prepare the supplier request for the latest requirement.

Expected:

- correct eligible requirement resolved;
- RFQ draft created or reused;
- capable suppliers selected from imported capabilities;
- preview created;
- RFQ number returned;
- not falsely described as sent;
- review action opens the same RFQ workbench.

User:

> Send it to the suppliers.

Expected:

- controlled proposal;
- recipients, deadline, document version, and consequence shown;
- no dispatch before confirmation;
- after confirmation, exact prepared/dispatched/delivery state shown;
- supplier portal tokens and simulated email events are scoped and auditable.

## Scenario 3 — Purchase Manager processes quotations

User uploads PDF, image, and XLSX quote fixtures and says:

> Compare these quotations for the latest supplier request and recommend the best option.

Expected:

- files validated and associated;
- extraction progress visible;
- uncertain fields identified;
- verification flow accessible;
- currencies, UOM, taxes, discounts, freight, delivery, validity, terms, and deviations normalized deterministically;
- canonical comparison created after eligibility;
- recommendation explained with cost, delivery, compliance, supplier performance, and risks;
- downloadable document available;
- same comparison visible manually.

## Scenario 4 — Negotiation, split award, approval, and PO

Expected:

- a quotation revision or negotiation round preserves history;
- split award or partial quantity is possible when policy permits;
- approvers receive tasks for the same frozen comparison version;
- rejection or change request carries rationale;
- stale approvals do not apply to a newer version;
- after approval, Purchase Manager prepares the PO through a controlled action;
- supplier issue, ERP/file export, and external acknowledgement remain distinct;
- PO export creates a new workbook version and reconciliation entry.

## Scenario 5 — Acknowledgement, partial delivery, and inbound quality

Import or receive a supplier acknowledgement and partial ASN.

Expected:

- commitment date and requested changes are visible;
- Gate sees PO, supplier, vehicle/document, and expected quantity context;
- Stores sees Gate-admitted receipt and remaining quantity;
- Quality sees receipt, specification, certificate, and supplier history;
- accepted, rejected, and held quantities are validated;
- rejection creates return/replacement and supplier-corrective-action work;
- replacement delivery and reinspection close the correct remaining quantity;
- no inventory or ERP effect is falsely claimed before integration confirmation.

## Scenario 6 — Invoice and finance handoff

Upload a supplier invoice fixture.

Expected:

- invoice identity and duplicate checks run;
- invoice lines associate with PO and receipts;
- deterministic three-way match is produced;
- price, quantity, tax, freight, quality-hold, or missing-document discrepancy is explained;
- an exception routes to the correct role;
- accepted match creates a finance-ready handoff;
- no payment or journal posting is available to the assistant;
- invoice/match status exports and reconciles through Excel.

## Scenario 7 — Manager coordination

User:

> What is blocking the latest Aluminium requirement? Ask the responsible person for an update.

Expected:

- requirement and task resolved;
- current known blocker summarized;
- governed update request created for an authorized descendant;
- response/status displayed with timestamp, owner, blocker, and next commitment;
- no private transcript leakage;
- manager summary uses sourced operational facts rather than an opaque employee score.

## Scenario 8 — External conflict and reconciliation

Change a previously imported PO or supplier row using an older source version and re-import it.

Expected:

- stale change is detected;
- canonical data is not silently overwritten;
- conflict shows both versions and an authorized resolution path;
- same-file replay remains idempotent;
- export generates a new workbook rather than overwriting the original;
- reconciliation identifies no unresolved differences after approved resolution.

## Scenario 9 — Provider, connector, and worker failure

Disable LLM provider access, then simulate connector timeout and document-worker failure.

Expected:

- manual workflows remain functional;
- assistant clearly states degraded or unavailable state;
- no fake action claims;
- deterministic fallback occurs only where configured and unambiguous;
- uncertain external commit enters verification/reconciliation rather than retrying blindly;
- failed document job is recoverable and does not make unverified data comparison-eligible.

---

# 22. Rollout strategy

## 22.1 Feature flags

Use flags for:

- bounded runtime;
- typed thread state migration;
- Excel/CSV import;
- Excel controlled export/write-back;
- mapping wizard;
- generic REST/OData/SFTP connectors;
- each vendor adapter and each write capability;
- inbound email ingestion;
- supplier portal;
- invoice and three-way-match handoff;
- proactive notifications;
- morning/end-of-day briefs;
- read-only external connector;
- shadow write;
- UAT write;
- limited/live ERP write;
- advanced analytics.

## 22.2 Runtime rollout

1. tests only;
2. developer workspace;
3. demo workspace;
4. internal shadow comparison against old path;
5. pilot tenant read-only;
6. pilot tenant limited controlled writes;
7. broader rollout.

Never execute both old and new mutation paths for the same user request.

## 22.3 Rollback

Every phase that changes runtime or persisted contracts must document:

- feature flag rollback;
- database forward/backward compatibility;
- migration rollback where safe;
- queue/job handling;
- proposal and receipt compatibility;
- client contract compatibility;
- known irreversible external effects.

---

# 23. Aggressive implementation timeline

The following timeline assumes a focused 6–8 person team: product/domain founder, two backend/agent engineers, frontend engineer, integration engineer, QA/automation engineer, part-time security/infrastructure support, and direct access to at least one manufacturing design partner.

| Time | Target |
|---|---|
| Week 1 | Baseline truth, regressions, current architecture lock |
| Weeks 2–3 | Typed state, universal resolution, adapter completeness |
| Weeks 3–5 | Live bounded runtime and core procurement agent skills |
| Weeks 4–7 | Manual workbench simplification and assistant-first shell |
| Weeks 6–8 | Tasks, proactive alerts, manager coordination |
| Weeks 7–10 | Excel/CSV connector, mapping wizard, golden test ERP, round-trip export |
| Weeks 9–12 | Generic connector SDK, Control Centre, REST/OData/SFTP simulators |
| Weeks 11–15 | Oracle completion plus SAP/Dynamics/Odoo/email/portal reference adapters |
| Weeks 12–16 | Multi-line, split award, PO amendments, partial delivery, return/replacement |
| Weeks 14–17 | Invoice capture, three-way-match preparation, finance handoff |
| Weeks 15–18 | Knowledge, configuration, supplier intelligence, management summaries |
| Weeks 18–20 | Security, observability, recovery drills, Excel-only pilot release |
| Weeks 20–24 | Read-only ERP pilot, shadow write, UAT, one limited production-write workflow |

Aggressive release targets:

- **8 weeks:** excellent procurement demo with complete role assistants and manual workbenches;
- **10 weeks:** complete Excel-driven external-system demo and automated acceptance suite;
- **14 weeks:** ERP-agnostic connector platform with generic test adapters;
- **18–20 weeks:** end-to-end Excel-first controlled pilot including inbound and invoice handoff;
- **20–24 weeks:** first real ERP read-only/shadow/UAT deployment and one limited write workflow;
- **6–9 months:** repeatable connector acceptance and multiple customer deployments;
- **9–12 months:** hardened reference adapters across ERP vendors demanded by active customers.

A solo founder with coding agents can build the demo and Excel connector aggressively, but cannot responsibly certify several live ERP vendors, security operations, and customer-specific mappings in the same timeline without domain, integration, QA, and customer support capacity.

Critical sequencing rules:

1. Excel/CSV is not postponed until after ERP work; it is the first external-system implementation and test oracle.
2. No vendor adapter is built outside the common connector SDK.
3. No live write is enabled before read-only, shadow, UAT, idempotency, and reconciliation gates pass.
4. No maintenance, production, HR, or PLM module is started until procurement passes the Excel-only pilot and one real ERP integration gate.
5. Future departments reuse the same connectors, work graph, task engine, policy engine, runtime, knowledge, notification, and UI foundations.

---

# 24. Explicit exclusions for this release

Do not add in the procurement-completion cycle:

- full HRMS or payroll;
- full accounting or payment execution;
- replacement inventory ledger;
- full MES;
- production scheduling engine;
- CAD/PLM authoring;
- autonomous machine control;
- automatic payment, supplier bank-detail change, or financial journal posting;
- unrestricted inventory adjustments;
- hidden employee performance scoring;
- fully autonomous supplier negotiation;
- unrestricted agent-to-agent chats;
- generic no-code agent builder;
- custom foundation model training;
- claims of certifications not obtained;
- claims that every ERP has an out-of-the-box certified connector;
- direct database-table writes into customer ERPs;
- destructive in-place editing of the customer’s only Excel workbook.

---

# 25. Final definition of done

The plan is complete only when all of the following are true:

## Agent

- the live assistant uses a bounded multi-step tool loop;
- every enabled capability has a typed adapter;
- conversation state and entity resolution work across turns;
- users can use natural language without exact commands;
- attachments drive canonical quotation workflows;
- controlled actions require confirmation;
- no false mutation claims occur;
- all results use business language and actual IDs;
- provider failure does not block manual work.

## Manual product

- every workflow has one primary next action per state;
- requirements, RFQs, quotations, comparisons, approvals, POs, Gate, Stores, and Quality are understandable without backend terminology;
- assistant and manual actions converge on the same records;
- selected context is preserved;
- recoverable errors are clear;
- responsive and accessibility tests pass.

## Coordination

- tasks show business context;
- duplicate active workflow tasks are prevented;
- badges and notifications show work left;
- managers can request governed updates;
- proactive alerts are deduplicated and actionable;
- daily summaries are sourced and factual.

## Integration and trust

- Excel/CSV can operate as a complete external test/source system for the procurement lifecycle;
- standard workbook import, mapping, validation, idempotent re-import, controlled export, conflict handling, and reconciliation work;
- the golden Excel end-to-end scenario passes from clean workspace through invoice handoff;
- every connector implements the common capability, mapping, outbox, verification, and reconciliation contracts;
- generic REST, OData, and file/SFTP test connectors pass conformance tests;
- read-only, shadow, UAT, limited-write, and emergency-disabled modes work;
- writes are least-privilege, idempotent, validated, approved, verified, and reconciled;
- no credentials reach the browser or model;
- customer-visible integration controls and connector acceptance reports exist;
- Oracle, SAP, Dynamics, Odoo, Excel, email, and other provider claims match tested manifests;
- no external timeout, outbox creation, or local simulation appears as a confirmed ERP effect;
- security limitations are documented honestly.

## Business value

- customer can complete requirement-to-receipt-to-quality-to-invoice-handoff workflow;
- a company without ERP access can run and test the complete product through Excel/CSV;
- a company with an ERP can connect without changing procurement business logic;
- quotation processing and comparison are materially faster;
- split awards, amendments, partial deliveries, returns, and invoice exceptions have controlled workflows;
- approvals and follow-ups are visible;
- managers spend less time collecting status;
- ROI metrics are available and evidence-linked;
- procurement demonstrates the reusable integration, work, policy, and agent layer for future departments.

---

# 26. Required Codex completion report

The final implementation response must use this exact structure:

## Implemented

- concise list of completed business outcomes;
- concise list of architecture/runtime changes;
- concise list of UI/workflow changes.

## Files changed

- grouped backend files;
- grouped frontend files;
- migrations;
- tests;
- documentation.

## Verification

For every command, report exact result:

- `git diff --check`;
- API tests;
- deterministic agent evaluation;
- live Groq evaluation or explicit not-run reason;
- OpenAPI contract;
- TypeScript typecheck;
- production web build;
- Playwright desktop/tablet/mobile;
- accessibility checks;
- Docker Compose or exact blocker.

## Demo acceptance

Report PASS or FAIL for:

1. requirement creation and follow-up ID;
2. exact/latest RFQ preparation;
3. controlled RFQ send;
4. attachment-to-comparison;
5. approval-to-PO;
6. Gate-to-Quality;
7. manager follow-up;
8. provider failure/manual fallback;
9. new demo workspace role access;
10. no raw/internal UI output.

## External-system acceptance

Report PASS or FAIL for:

1. golden Excel workbook import into a clean workspace;
2. mapping preview, invalid rows, and user corrections;
3. idempotent re-import;
4. stale-row conflict prevention;
5. controlled Excel export/write-back to a new version;
6. round-trip reconciliation;
7. connector conformance matrix;
8. generic REST/OData/SFTP test systems;
9. ERP, email, and supplier-portal capability manifests;
10. read-only, shadow, UAT, and live modes actually tested;
11. failure injection and manual continuity;
12. unsupported providers and capabilities stated explicitly.

## Remaining blockers

Only factual unresolved issues. Do not restate future roadmap items as completed work.

---

# 27. Command to execute this plan

Use the following instruction with Codex:

> Read `HANDOFF2(2).md` and `PLAN.md` completely, then inspect the checked-in source to resolve any conflict. Treat `PLAN.md` as a patch-first execution contract. Implement the phases in order without redesigning the architecture, rewriting working canonical services, creating parallel workflows, or stopping after scaffolding. Excel/CSV is the mandatory first external system and integration test oracle: complete mapping, dry run, row lineage, idempotent re-import, controlled new-version write-back, conflict handling, and reconciliation before making live ERP claims. Add the exact failing regressions first, make the bounded runtime and typed state truly live, complete the procurement assistant vertical slices, simplify the manual workbenches, redesign My Work and the assistant, add governed coordination and safe integration controls, and run every phase gate. Preserve the dirty worktree, role authority, tenant/plant isolation, idempotency, audit, receipts, proposals, immutable documents, private storage, manual fallback, migrations, and generated-contract workflow. Finish with the exact Section 26 completion report and do not claim any verification that was not run.
