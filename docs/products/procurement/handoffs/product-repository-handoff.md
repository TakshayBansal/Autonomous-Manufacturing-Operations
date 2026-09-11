# GenuineGigs Complete Product and Repository Handoff

> Last updated: 2026-07-16
> Repository: `C:\Users\Takshay\Desktop\Important\GenuineGigs`
> Status: active development; worktree intentionally uncommitted

This is the primary context package for an engineer or LLM taking over GenuineGigs. It documents the implemented product: workflows, master data, screens, roles, PDFs, storage, agents, APIs, entities, runtime, migrations, tests, compatibility surfaces, and production gaps.

Read it completely, then inspect `git status --short`. The dirty worktree contains valuable implementation. Do not reset, revert, delete, or regenerate unrelated files. Never use `git reset --hard` or `git checkout --` unless explicitly requested.

## 1. Product identity and canonical process

GenuineGigs is a focused manufacturing procurement and inbound-material ERP with an optional governed role assistant.

```text
Approved material master -> Material requirement -> RFQ draft/PDF
-> RFQ publication to capable suppliers -> Quotation upload
-> Field extraction and human verification -> Supplier comparison
-> Plant Manager + Purchase Executive approval -> Final PO/PDF
-> Gate entry -> Store receipt -> Quality inspection
-> Inventory impact / exception handling
```

The normal product is not dependent on AI. Every action can be completed manually through deterministic FastAPI services and ERP-style workbenches. The assistant calls the same services. Forecasting, inventory prediction, production scheduling, and automatic quantity calculation are outside this release; a Plant Manager or Purchase Executive supplies quantity.

## 2. Decisions that must not be reversed

- `PurchaseRequirement` is the only active demand record.
- A material-master request only adds a missing approved material.
- Objective creation is retired: `POST /objectives` is HTTP 410; old Objective data/routes are compatibility-only.
- Purchase Executive owns RFQ preparation/publication.
- Purchase Manager owns quotation verification, comparison, and final PO.
- Plant Manager and Purchase Executive approve the same immutable comparison version.
- Gate Operator, Store Manager, Quality Inspector own inbound entry in that order.
- Draft preview never publishes, emails, approves, posts, or changes inventory.
- Supplier email and ERP posting are separate controlled effects.
- Tenant/plant isolation, idempotency, audit, and human authority are mandatory.

## 3. Roles, capabilities, and visible work

| Role | Responsibility | Main navigation |
| --- | --- | --- |
| Plant Manager | Requirements, team work, comparison decision | My work, Requirements, Comparison |
| Purchase Executive | Requirements, RFQ publication, comparison decision | My work, Requirements, RFQs, Comparison |
| Purchase Manager | Quote verification, comparison/recommendation, PO | My work, Quotations, Comparison, Purchase orders |
| Gate Operator | Admit delivery against issued PO | My work, Receive at gate |
| Store Manager | Optional ASN and quantity receipt | My work, Store receipt |
| Quality Inspector | Accepted/rejected/held disposition | My work, Quality inspection |
| Admin | Users, roles, master data, agents, audit, workspace | My work, Admin, Audit |

All roles default to `/control-centre` (My Work). Navigation is server-filtered; hiding a route is not authorization.

Workspace ownership is separate from operational role. A creator remains Plant Manager and receives `workspace.owner`, deriving `workspace.manage_members`, `workspace.manage_master_data`, `workspace.manage_agents`, and `workspace.view_setup`.

Server read scopes: procurement is Plant/Purchase Managers, Purchase Executive, Admin; PO/inbound is available to roles needing handoff; documents are procurement/quality/admin; audit is Plant Manager/Admin; integrations are Purchase Manager/Admin; administration is Admin.

## 4. Detailed workflow

### 4.1 Material and supplier master

The approved master consists of `Item`, `Uom`, optional `ItemSpecification`, and `TaxPolicy`. Requirements reference approved Items.

Missing material uses a separate request with proposed code, name, UOM, specification, and reason. Status is pending/approved/rejected. Admin or owner decides with rationale. Approval creates Item/UOM/specification records. It does not create a requirement/RFQ.

Supplier data includes name/status, ERP vendor ID, site, currency, terms, contact, quality/delivery scores, and `SupplierItemCapability` links with approved flag. RFQs use approved item-capable suppliers; UI/agent never invents suppliers.

### 4.2 Material requirement

The single **New requirement** form has title, reason, source, named Purchase Executive, and multiple lines. Each line has material, positive quantity, UOM, need-by date, optional specification, and inspection flag. Add/Remove line is supported.

Backend stores one `PurchaseRequirement` plus lines and creates named Purchase Executive Task/assignment metadata. Manual and agent creation share service, audit, cases, and RFQ eligibility. Agent records may retain thread/run/correlation.

States are `draft -> approved -> rfq_drafted`, with cancellation. Current entry creates an approved requirement. Without items or assignees, creation is disabled and setup is shown.

### 4.3 RFQ

Purchase Executive generates RFQ from requirement; lines preserve material, description, quantity, UOM, date, certificates. Deadline and shortlist are editable.

Actions: Generate, Save, Preview draft PDF, Download final PDF, Publish. Preview only makes a watermarked artifact. Publication requires confirmation/version, finalizes PDF, creates invitations/portal tokens, prepares supplier emails, audits, and progresses `draft -> published -> responses_open`. Closed/cancelled also exist. Email dispatch is separate.

### 4.4 Quotation upload, extraction, verification

Purchase Manager selects RFQ/supplier and uploads PDF, PNG, JPG/JPEG, or XLSX (10 MB default). Private quarantine validation checks extension, MIME, signature, structure, checksum, and size.

Extraction uses PyPDF, Tesseract + `pdf2image`, image OCR, `openpyxl`, then optional Groq structured extraction. Formula-like spreadsheet cells are lower confidence.

Fields: quote number/date, validity, quantity/UOM, unit price, GST, freight, packaging, MOQ, lead time, promised date, payment terms, certificates, deviations, and lines. Each stores evidence, confidence, parser/model version, status, and missing-field summary.

Original PDF appears beside fields. Purchase Manager accepts, corrects, or rejects each `needs_review` field. Only verified quotes enter comparison. Statuses: `extracting`, `needs_review`, `needs_manual_entry`, `verified`, `rejected`, `superseded`. Negotiation changes return values to review.

### 4.5 Supplier comparison and dual approval

Purchase Manager generates/regenerates a line-level `BidComparison` from verified quotes. It evaluates base price, freight, packaging, recoverable/non-recoverable tax, landed unit/total cost, delivery, technical/certificate compliance, supplier quality/delivery scores, MOQ, feasibility, score components, disqualification reasons, and recommendation.

Generation produces `draft` or `no_eligible_supplier`. Manager adds recommendation rationale, previews PDF, then explicitly freezes/submits.

```text
draft / ready_for_manager_review / rejected
-> ready_for_approval -> partially_approved -> approved
```

Submission finalizes a comparison PDF bound to its exact version, creates named Plant Manager and Purchase Executive approval requests/tasks, and prevents commercial edits. Order does not matter. First approval is partial; both approve. Rejection requires rationale, invalidates the other pending decision, and returns a new-version revision to Purchase Manager. Decisions never transfer across versions.

### 4.6 Purchase order

Only Purchase Manager creates final PO from a dual-approved comparison; UI requires `CONFIRM_PO`. Confirmation resolves the recommended supplier/award, creates `PODraft`/lines, final immutable PDF, status `approved_pending_outbox`, pending ERP proposal, audit, and downstream work. It does not automatically email or post.

PO screen supports draft preview, final download, and supplier-email preparation. Statuses: `pending_approval`, `approved_pending_outbox`, `posting`, `simulated_posted`, `posted`, `failed`, `rejected`.

Secure supplier acknowledgement (accepted/rejected with confirmed quantity/date) and optional Store ASN are supported. ASN is not required for the simple flow.

### 4.7 Gate, Store, Quality

Gate Operator records issued PO, optional ASN, vehicle, supplier challan, packages, arrival notes/time. It notifies Stores and does not accept stock.

Store Manager records gate-admitted PO, positive received quantity, damaged quantity, and derived shortage/excess. Store cannot receive before Gate; damage cannot exceed receipt. It notifies Quality. If inspection is not required, receipt can be accepted without inspection.

Quality Inspector records inspected, accepted, rejected, held quantities plus status/notes. Dispositions cannot exceed inspected quantity. `InventoryImpact` records usable/rejected/held quantities. Shortage, damage, rejection, hold, certificate, or supplier problems create/update a Case.

### 4.8 Exceptions, negotiation, integrations

Case stores severity, owner, due date, linked records, timeline, evidence, resolution. Close requires resolution; Plant Manager/Admin override requires rationale.

Negotiation is a secondary implemented flow:
`draft -> pending_approval -> manager_approved -> supplier_countered -> accepted_pending_reverification -> closed`. It is not a mandatory primary step. Changed pricing returns the quote to verification.

Email/ERP effects use persistent outbox records. ERP event requires approval then dispatch; failure can retry. Reconciliation compares local/external state. Simulation is default.

## 5. PDFs, artifacts, and MinIO

ReportLab generates RFQ, comparison, and PO PDFs. Every `GeneratedArtifact` stores type/entity, version, source snapshot SHA-256, Document/checksum, draft/final state, generator/user, and finalization time.

Drafts have diagonal DRAFT watermark and not issuek�u���] subtitle. Finals are controlled documents. Wide comparisons use landscape A4. Repeated headers, company/plant metadata, and generated footer are included. An identical final snapshot is reused rather than duplicated.

- RFQ PDF: material, description, quantity, UOM, need-by, certificates, deadline, suppliers, instructions.
- Comparison PDF: supplier/quote, landed costs, compliance, quality, recommendation/reasons, RFQ/version/rationale.
- PO PDF: company/plant, PO, supplier, RFQ/award, ship-to, currency/terms/total, material/tax/date lines.

Private MinIO:

- container endpoint `http://minio:9000`;
- host endpoint `http://localhost:9000`;
- console `http://localhost:9001`;
- buckets `genuinegigs-quarantine`, `genuinegigs-evidence`, configured `genuinegigs-documents`.

Browser never receives `minio:9000`. `GET /documents/{id}/download-url` returns `/documents/{id}/content?token=...`. API validates signed payload/HMAC, expiry/session/scope, streams private bytes inline with no-store. Separately encoded payload/HMAC fixed intermittent delimiter-related 403s. Never make buckets public.

## 6. Tasks and My Work

`Task` stores title/type, requested outcome/instructions, priority/severity, owner user/membership/role, creator/delegator, due date, expected output, entity/Case/parent, manual/agent source, source run, acceptance, blocker, completion, follow-up/escalation, and shared-queue flag.

```text
open -> accepted -> in_progress -> review -> completed
                   -> blocked -> in_progress
active states -> cancelled (delegator/Admin only)
```

Assignee updates execution. Blocked requires reason; completed requires summary. Delegation is self/Admin/reporting descendants only. Manager follow-up notifies assignee; overdue follow-up increments escalation.

My Work answers next task, why, evidence, expected result, owner, due date, blockers, and waiting role. Opening a task is navigation only and never performs a consequential action.

## 7. Governed role assistant

Each `WorkspaceMembership` may have one role `AgentProfile`. Threads are membership-private and personal/work-item scoped. The assistant is contained in the page grid, not a blocking global modal. `/agent` is the queue, delegation, run, proposal, receipt, team/workspace activity page.

### Runtime and provider

Bounded LangGraph nodes: validate request; resolve identity/context; classify intent; select workflow; prepare plan; execute validated local decision; validate persisted result.

Limits cover graph steps, tool calls, tokens/context bytes, runtime, handoff/delegation depth, and requests/minute. Recent history and confirmed procurement facts live in `AgentThread.context_state`; explicit correction overwrites older facts with message provenance.

`AgentCheckpoint` persists context resolution, validated decision, human interrupt/resume, failure, and final metrics. Events, tool calls, proposals, and receipts show activity without hidden chain-of-thought.

- Primary Groq action model: `openai/gpt-oss-120b`.
- Fast profile: `llama-3.1-8b-instant`.
- Groq mode can return typed decisions for authorized local tools.
- Limited mode explains scoped records but never executes free-form commands.
- Provider/model/error/correlation are persisted without secrets.
- Provider outage never blocks manual work.

Implemented assistance:

- Plant Manager can create/delegate one canonical requirement only when approved material, quantity/UOM, need-by, and unique Purchase Executive resolve.
- Transaction creates one requirement, Task, governed delegation, audit, receipt; never Objective.
- Assigned Purchase Executive can prepare idempotent RFQ draft/private draft PDF.
- Assigned Purchase Manager can prepare comparison/PDF from verified quotes.
- Purchase Manager may receive `confirm_purchase_order` proposal; PO happens only after confirmation.
- Typed blocks include summary, record, missing information, warning, artifact, receipt, role handoff, approval/proposal, and limited mode.

Action claims only follow persisted tool results. Controlled proposals (RFQ publish, PO confirm, approvals, dispatch, inspection, closure) recheck membership, tenant/plant, role/capability, entity/version, expiry, and idempotency. Rejection needs rationale. Confirmation resumes linked run and creates receipt.

Server context is built from selected membership, task ownership, linked IDs, reporting scope, tools, restrictions, budgets, and policy. Model IDs cannot broaden access. Employees see assigned/linked/approved/private data; managers see formal descendant status, never private transcripts; peers cannot assign peers.

## 8. Workspace, login, and identity

Global `Account` is separate from tenant-scoped `User` and `WorkspaceMembership`; one account can join isolated workspaces.

Login: email/password; development demo quick-fill; multiple memberships return workspace options; user chooses workspace/plant/role on login; session pins membership; switching rotates CSRF/scope.

Security:

- Argon2 passwords and login/recovery throttles;
- `gg_session` HttpOnly cookie, configurable Secure/SameSite, default ten-hour TTL;
- unsafe mutations require `x-csrf-token` and `Idempotency-Key`;
- email verification/reset tokens;
- TOTP MFA enrollment/confirm/disable and recovery data;
- session listing/revocation;
- audited invitations.

Workspace owner/Admin can list/create/resend/revoke invitations. Raw one-time seven-day token is emailed; only hash is stored. Acceptance captures name/password and creates Account/User/Membership/access. Outbox/audit never store raw token. Development/test may return a development token.

### Fresh workspace

Creation collects company, workspace, plant, plant code and creates isolated Tenant, Company, Plant, departments, creator User/Membership/access, flags, profile. Departments: Plant Leadership, Procurement, Gate and Security, Stores, Quality.

Development automatically adds existing standard demo accounts as Purchase Manager, Purchase Executive, Gate, Store, Quality, Admin. Purchase Executive reports to Purchase Manager; others to creator/Plant Manager. No sample transactions are copied.

Readiness derives from required role coverage + at least one approved material + at least one capable supplier: `needs_team`, `needs_master_data`, or `complete`. Creation selects the membership then redirects to `/procurement`; all memberships are selectable at login.

## 9. Frontend design and routes

Next.js 16 App Router + React + TypeScript + Lucide. Dense industrial workbench, not decorative AI SaaS.

Layout: dark sticky 292px navigation; warm canvas/paper; breadcrumb/title/subtitle; grouped My work/Process records navigation; seven-step process bar; four-question context guide; task-first area/process rail; contained tables/forms; assistant; Ctrl/Cmd+K palette.

Tokens: nav `#172123`, strong nav `#101719`, canvas `#f1ece2`, paper `#fffdf7`, muted paper `#f8f4eb`, line `#d4cabb`, text `#171b1c`, action orange `#d8792b`, success green `#2d7d5b`, danger red `#b33a34`. IBM Plex Sans style stack; mono for IDs.

Rules: restrained panels, no gradients/decorative AI art, plain language plus ERP term, exact IDs/statuses retained, status pills, confirmations for consequence, rationale for rejection/override, useful empty states, safe wrapping/scrolling.

Responsive: main columns collapse <1280; nav becomes static/top <1180; grids/forms collapse around 980/900/820; login one-column <820; assistant remains non-fixed/contained; tables scroll horizontally.

| Route | Rendered behavior |
| --- | --- |
| `/`, `/control-centre` | My Work, queue/handoffs, metrics, cases, comparison, timeline |
| `/procurement` | Multi-line requirement + ledger |
| `/rfq-builder` | RFQ generation/edit/PDF/publication |
| `/quotes` | Upload, source preview, field verification, ledger |
| `/comparison`, `/approvals` | Comparison, PDF, dual approval, PO confirmation |
| `/po-drafts` | PO preview/download/email preparation |
| `/gate`, `/store`, `/quality`, `/inbound` | Physical entry and status ledgers |
| `/agent` | Agent queue/runs/proposals/receipts/delegations/team |
| `/workspace/setup` | Workspaces, readiness, seats, material/supplier master |
| `/accept-invitation` | Invitation credential setup |
| `/admin`, `/audit` | Administration/master/agent policy and audit |

Advanced compatibility routes still build but are absent from normal navigation: `/evidence`, `/negotiations`, `/cases`, `/outbox`, `/integrations`. They are not mandatory primary steps.

## 10. Backend architecture

FastAPI + Pydantic + SQLAlchemy.

- `main.py`: auth and main procurement/inbound/document/integration/org routes.
- `domains/workflows.py`: scope, navigation, My Work, workflow services/transitions.
- `procurement_v2.py`: master requests, suppliers, PDFs, dual approvals, final PO/email.
- `documents.py`: validation, MinIO, PDF/OCR/XLSX extraction, jobs/evidence.
- `storage.py`: S3/MinIO abstraction.
- `task_service.py`: hierarchy-safe task lifecycle/follow-up.
- `agent_service.py`: context, graph, Groq, tools, proposals, workspace bootstrap.
- `routers/agents.py`, `routers/identity.py`: agent/workspace/task/identity APIs.
- `integrations.py`, `erp.py`: adapters, outbox, sync, retry, reconciliation.
- `workers.py`, `celery_app.py`: background queues.
- `core/security.py`, `middleware.py`, `permissions.py`, `rate_limit.py`, `metrics.py`: security/governance/observability.
- `db/models.py`: persistence; `models.py`, `api_schemas.py`, `agent_schemas.py`: contracts.

Scoped entities carry tenant/plant. Helpers enforce scope. Important mutations create `AuditEvent` and `WorkflowTransition`. Versioned records expose ETags.

## 11. Data model catalog

### Identity/organization

`Tenant` (workspace kind/onboarding/flags), `Account` (global identity), `WorkspaceMembership` (role/plants/department/manager/permissions), `WorkspaceInvitation`, `IdentityToken`, `Company`, `Plant`, `Department`, `RoleDefinition`, `User`, `ReportingLine`, `UserPlantAccess`, `AuthSession`, `LoginAttempt`, `TenantFeatureFlag`, `BusinessNumberSequence`.

### Work/governance

`Task`, `Notification`, `Case`, append-only `AuditEvent`, `WorkflowTransition`, compatibility `ApprovalDecision`, and `IdempotencyRecord`.

### Master/procurement

`Supplier`, `SupplierSite`, `SupplierContact`, `Uom`, `Item`, `ItemSpecification`, `TaxPolicy`, `SupplierItemCapability`, `MaterialMasterRequest`.

`PurchaseRequirement`/line, `RFQ`/line/supplier invitation/portal token, `SupplierQuote`/line/extraction/field verification, `BidComparison`, `ComparisonApprovalRequest`, `NegotiationRound`/message, `AwardDecision`/line, `PODraft`/line, `SupplierAcknowledgement`.

### Inbound/documents

`ASN`, `GateEntry`, `StoreReceipt`, `InspectionResult`, `InventoryImpact`.

`Document` stores bucket/key/name/type/checksum/validation/entity. `GeneratedArtifact` stores version/snapshot/draft-final. `DocumentJob` and `DocumentValidationResult` store processing/checks.

### Agents/knowledge/integrations

`AgentProfile`, `AgentThread`, `AgentMessage`, `AgentRun`, `AgentEvent`, `AgentCheckpoint`, `AgentToolCall`, `AgentProposal`, `AgentActionReceipt`, `AgentDelegation`, `AgentMemory`, `AgentFeedback`, `KnowledgeDocument`, `KnowledgeChunk`; legacy `Objective`.

`OutboxMessage`, `IntegrationConnection`, `IntegrationSyncJob`, `IntegrationExternalReference`, `IntegrationOutboxEvent`, `IntegrationAttempt`, `ReconciliationResult`.

## 12. Public APIs

Exact generated contract: `packages/shared/src/api.generated.ts`; do not hand-edit except generated hash header.

- Health: health/live/ready and Prometheus metrics.
- Auth: login/logout/me/CSRF, sessions/revoke, MFA, password reset.
- Workspace: overview/setup/create/list/select, invitations CRUD/accept, work-item context.
- Organization: users/roles/plants/departments/access/reset.
- Tasks: list/create/team/detail/transition/request update/notifications.
- Master: items, assignees, suppliers, material requests/decisions.
- Requirements: list/detail/create and requirement-to-RFQ.
- RFQ: list/detail/update/publish/preview/artifacts/supplier submission.
- Quotes: list/detail/upload/extraction/verifications/verify.
- Comparison: generate/list/preview/artifacts/approvals/submit/decision/confirm-PO.
- PO: list/detail/create/approve/preview/artifacts/supplier-email/acknowledgement.
- Inbound: acknowledgements, ASN, gate, receipt, inspection, inventory impact.
- Documents: upload/list/detail/validation/download/content/reprocess.
- Cases: list/controlled close.
- Integrations: outboxes, approve/dispatch/retry, imports, connections/tests, sync, posting, reconciliation.
- Agents: home, threads/context/messages, runs/events/activity/cancel, proposals, delegations, team, feedback, knowledge, profiles/policy/emergency stop.
- Objectives: GET compatibility; creation HTTP 410.

Unsafe calls require CSRF and unique `Idempotency-Key`. Same key/request replays stored response with `Idempotency-Replayed`; changed payload conflicts. Requests receive `X-Correlation-ID`; sensitive supplier token paths are redacted in logs.

## 13. Demo dataset

Demo: Apex Components Pvt Ltd / Pune Plant / ERP location PUNE-PLANT-STORE-01.

All demo passwords are `Password@123`:

- Ananya Rao: `plant.manager@genuinegigs.local`
- Vikram Shah: `purchase.manager@genuinegigs.local`
- Meera Iyer: `purchase.exec@genuinegigs.local`
- Sanjay Patil: `gate.operator@genuinegigs.local`
- Rohit Kulkarni: `store.manager@genuinegigs.local`
- Farhan Ali: `quality.inspector@genuinegigs.local`
- Neha Kapoor: `admin@genuinegigs.local`

Reporting: Plant Manager -> Purchase Manager -> Purchase Executive; Plant Manager -> Gate, Store, Quality, Admin.

Master: `SLEEVE-A` Line shaft bearing sleeve, KG, EN8, Mill Test Certificate + Heat Number Traceability, recoverable GST18. Suppliers: Apex Alloy Works (approved/AAW-1001), Bharat Metals (approved/BM-2044), Crown Industrial Supply (conditional/CIS-8841); all have SLEEVE-A capability.

Reference transactions include 1,500 KG requirement, RFQ-2026-0031, three XLSX/PDF/OCR-style quote examples, comparison, negotiation/awards, simulated-posted PO, acknowledgement, ASN, gate, 1,480 KG receipt, partial quality acceptance, 70 KG exception, tasks, outbox, audit. Fresh workspaces copy none.

## 14. Runtime and infrastructure

Run `docker compose up --build -d`.

| Service | Purpose / port |
| --- | --- |
| postgres | pgvector PostgreSQL 16 / 5432 |
| redis | queue/cache / 6379 |
| minio, minio-init | private storage / 9000, console 9001, bucket initialization |
| mailpit | SMTP 1025, UI 8025 |
| migrate | one-shot `alembic upgrade head` |
| seed | one-shot idempotent baseline reconciliation |
| api | FastAPI/Uvicorn / 8000 |
| worker | Celery queues agents,documents,integrations,email,sync |
| beat | Celery scheduler |
| web | production Next / 3000 |

URLs: web `http://localhost:3000`; API/docs `http://localhost:8000`, `/docs`; MinIO console `http://localhost:9001`; Mailpit `http://localhost:8025`.

API never creates/migrates schema. Alembic owns schema. Tests use disposable SQLite metadata; Compose uses PostgreSQL. Helm chart in `deploy/helm/genuinegigs` includes API/web/workers/migration/config/ingress and expects managed PostgreSQL, Redis, S3, and Secrets.

### Environment controls

See `.env.example` for all values:

- database/Redis URLs;
- MinIO endpoint/buckets/keys/region/secure;
- session secret, cookie security/SameSite/TTL, origins;
- upload limit, parser/OCR timeout, download TTL;
- Groq key/models and agent enablement/budgets;
- graph/tool/context/checkpoint/rate/delegation/handoff limits;
- independent agent external-email/ERP switches;
- SMTP settings/mode;
- ERP provider/write mode/live switch and Oracle/SAP credentials;
- web/API URLs.

Production validation rejects insecure cookies, weak session secrets, invalid SameSite, wildcard CORS, inconsistent ERP live flags, and Groq without key when fallback is disabled. SMTP/ERP default to simulation. Live ERP requires both `ERP_WRITE_MODE=live` and `ERP_LIVE_ENABLED=true`; agent enablement is independent.

## 15. Migrations and contract workflow

- `0001_industrial_v1.py`: original procurement schema.
- `0002_role_agent_os.py`: account/membership/agent/workspace foundation.
- `0003_identity_hardening.py`: sessions/password/MFA/invitations.
- `0004_schema_compatibility.py`: forward repairs.
- `0005_missing_baseline_tables.py`: baseline tables.
- `0006_enable_demo_agents.py`: demo agent flags.
- `0007_procurement_v2.py`: canonical requirements, V2 approvals/artifacts/inbound/master requests.
- `0008_professional_agent_onboarding.py`: context/source/correlation/onboarding/capabilities.
- `0009.py`: Task coordination, AgentEvent, AgentActionReceipt.
- `0010_agent_checkpoints.py`: durable bounded-run checkpoints.

After schema changes: migration if needed; start API; `npm run generate:api`; update OpenAPI SHA header; `npm run check:api-contract`; typecheck/build/tests.

## 16. Repository map

- `apps/api`: API, migrations, tests.
- `apps/web`: Next app, components, styles, E2E.
- `packages/shared`: generated OpenAPI TypeScript.
- `docs/architecture`: industrial, procurement V2, role-agent architecture.
- `docs/runbooks/agent-operations.md`: rollout/incidents/retention.
- `deploy/helm/genuinegigs`: Helm.
- `docker-compose.yml`: local stack.
- `PLAN copy.md`: latest large implementation/acceptance plan.
- `PLAN.md`, `PLAN2.md`: older context, not authoritative over code.
- `CHANGE_REVIEW_REPORT.md`, `README.md`: review/short overview.

Key frontend: `IndustrialConsole.tsx` (shell/navigation/screens/My Work), `WorkflowForms.tsx` (workflow forms), `AgentDrawer.tsx` (context assistant), `AgentWorkspace.tsx` (runs/proposals/receipts), `WorkspaceCommandPalette.tsx`, `globals.css`, `lib/api.ts`.

## 17. Verification status

Verified 2026-07-16:

- 49 API tests passed.
- 39 full Playwright tests passed desktop/tablet/mobile.
- Latest assistant regression passed 3/3 desktop/tablet/mobile.
- TypeScript, OpenAPI contract, production Next build (25 routes) passed.
- Docker API/web/PostgreSQL/Redis/MinIO healthy; migration/seed successful.
- RFQ PDF opened through signed API content route with no internal MinIO URL.
- `git diff --check` had no whitespace errors.

Windows pytest cache warning is non-blocking.

## 18. Not production-certified

Outstanding: live Groq scorecard; real supplier SMTP; Oracle/SAP live acceptance; enterprise SSO; forecasting/production planning; hardened external supplier portal; load/penetration/resilience tests; backup/restore/DR; KMS/secret rotation; billing/entitlements; multi-region; exhaustive browser checks for compatibility/admin routes.

### Historical product versions

The repository previously presented itself primarily as a Manufacturing Agent OS. That version exposed a global/private role-agent drawer, agent/objective workspaces, many governance and integration screens, Groq planning, team delegation, knowledge, proposals, and a parallel Procurement Objective demand model. In real plant-manager testing it felt too complicated and the early runtime could forget quantity, re-ask known facts, drift into production scheduling, expose tools that were not executed, and imply actions from prose without persisted results.

The product was deliberately simplified to the one ERP process in sections 1-4. Objective creation and duplicate procurement entry were removed, normal navigation was reduced, development workspace seats became automatic, login gained workspace selection, and PDF upload/download became part of the obvious workflow.

The current version selectively reintroduces useful agent infrastructure as an optional task-scoped assistant. It has typed decisions, durable context/checkpoints, local authorization, verified receipts, proposals, and canonical RFQ/comparison/PO assistance. This does not restore the old product hierarchy: the ERP process remains authoritative, the agent is not required, Objective is not demand intake, and compatibility screens must not become extra mandatory steps.

## 19. Continuation rules

Before editing:

```powershell
git status --short
git diff --check
docker compose ps -a
```

Preserve:

1. One canonical PurchaseRequirement.
2. Missing material uses master approval.
3. Purchase Executive owns RFQ publication.
4. Purchase Manager owns verification/comparison/PO.
5. Plant Manager + Purchase Executive approve same frozen version.
6. PO creation, supplier email, email dispatch, ERP approval/dispatch stay separate.
7. Gate -> Store -> Quality is enforced.
8. Draft preview does not mutate workflow.
9. Private MinIO uses scoped API URLs.
10. Tenant/plant/membership/reporting scope is server-enforced.
11. Unsafe requests are CSRF-protected/idempotent.
12. Agent claims require persisted tool call/receipt.
13. Agent outage never blocks manual workflow.
14. Preserve dirty worktree and generated contracts.

Recommended future prompt:

```text
Read HANDOFF.md completely, then inspect the code for my request. Treat the
simple Requirement -> RFQ -> verified quotations -> dual-approved comparison
-> PO -> Gate -> Store -> Quality process as canonical. Do not create parallel
demand records or extra mandatory steps. Preserve role ownership, tenant
isolation, controlled external actions, immutable PDFs, private MinIO through
the API, migrations, generated contracts, and tests. Inspect the dirty worktree
before editing and do not revert unrelated changes.
```
