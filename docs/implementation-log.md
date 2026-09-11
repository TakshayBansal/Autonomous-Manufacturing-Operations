# GenuineGigs implementation log

This log records verified repository facts and implementation evidence. A feature is not marked complete merely because a model, route, adapter, or test scaffold exists.

## 2026-08-11 — V2 handover and acceptance closure

- Completed the governed end-of-shift flow: generate, edit while draft, verify, publish, carry-over context, transition audit and publication outbox event.
- Added the matching responsive Shift start / End-of-shift operating briefing UI and API client contracts.
- Added V2 API-boundary acceptance coverage for role authority, knowledge revision/ACL guards, Gigi confirmation, edge identity/deduplication and shift publication order.
- Added Playwright coverage spanning all flagship V2 routes, mobile overflow, accessibility, handover and administrator-only infrastructure controls.
- Local browser execution remains host-gated: Chromium cannot load because `libnspr4.so` is absent and dependency installation requires host sudo. In-process FastAPI clients also stall before application dispatch under the installed deprecated Starlette/httpx bridge; Uvicorn itself reaches application startup successfully. These are recorded as acceptance-environment limits, not passing gates.

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest -q tests/test_operational_v2.py tests/test_connector_conformance.py` | Pass: 51 tests. |
| Fresh SQLite `alembic upgrade head && alembic current` | Pass: `0046_v2_knowledge_metadata (head)`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 41 routes. |

## 2026-08-11 — V2 Quality Intelligence & Recovery

- Extended canonical production quality events with event type, asset/lot scope, measurement values, control limits, severity and source evidence.
- Added deterministic SPC control-limit evaluation that creates one evidence-linked operational deviation, recovery task/action, value exposure and outbox event.
- Added governed internal NCR/CAPA records with parent lineage, owner, containment, human-confirmed root cause, corrective action, effectiveness criteria/result and immutable verification/closure provenance.
- Added authority-scoped create/update/verify/close APIs with optimistic versions, valid-transition enforcement, immutable terminal states, audit records and transactional outbox events.
- Expanded the responsive Quality workspace with control-limit signals and editable NCR/CAPA recovery cards. Manager verification and closure remain explicit separate decisions.
- Seeded a breached bore-diameter sample, linked NCR and linked CAPA so the complete workflow is demonstrable without inventing production data.

### Verification

| Command | Result |
| --- | --- |
| Fresh SQLite `alembic upgrade head && alembic current` | Pass: `0047_v2_quality_recovery (head)`. |
| `pytest -q tests/test_operational_v2.py tests/test_connector_conformance.py` | Pass: 52 tests. |
| Quality OpenAPI required-path assertion | Pass: event, case, update, verify and close contracts present. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 41 routes. |

## 2026-08-11 — V2 Multi-Plant Operating Layer

- Added versioned, approved standard KPI definitions with formulas, units, direction and required context dimensions so site comparisons have a visible contract.
- Cross-site loss analysis now reports distinct supporting plant count and never labels a single-site recurrence as cross-site verified.
- Added a grounded corporate Gigi briefing that states data coverage and comparison limitations.
- Added governed best-practice transfers with source/target lineage, applicability context, expected benefit, explicit accept/pilot/complete states and mandatory target-site outcome evidence.
- Added authority-scoped transition API, optimistic versions, immutable audit and outbox evidence, plus a responsive corporate workflow for recording local before/after results.
- Kept Nashik explicitly without comparable operating data; seeded records demonstrate governance rather than claiming live multi-site performance.

### Verification

| Command | Result |
| --- | --- |
| Fresh SQLite migration | Pass: `0048_v2_multi_plant (head)`. |
| `pytest -q tests/test_operational_v2.py tests/test_connector_conformance.py` | Pass: 53 tests. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 41 routes. |

## 2026-08-11 — V2 Locale and Performance Hardening

- Added canonical plant timezone, ISO currency and BCP-47 locale fields and exposed them only through authenticated plant context.
- Added one V2 formatting provider for numbers, money, dates and times; removed all India-only constants, currency glyphs and browser-default date/time formatting from V2 components.
- Added deterministic local p95 and payload budgets for Command Center, Quality, Corporate and Knowledge read models.
- Added a production-asset budget gate covering total JavaScript, largest JavaScript chunk and total CSS after a real Next.js production build.

### Verification

| Evidence | Result |
| --- | --- |
| Fresh SQLite migration | Pass: `0049_v2_plant_locale (head)`. |
| Flagship read-model performance | Pass: p95 Command Center 35.27 ms, Quality 9.79 ms, Corporate 22.71 ms, Knowledge 7.27 ms; maximum payload 4,375 bytes. |
| `npm run check:v2-performance` | Pass: JS 1,978,789 bytes total; largest chunk 352,132 bytes; CSS 225,855 bytes. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 41 routes. |

## 2026-08-11 — V2 Permission Matrix and Guided Setup

- Added role-scoped operational-value redaction. Quality/operator-style roles retain loss facts and recovery context but receive no financial amounts; admin, Plant Manager and Purchase Manager retain financial context.
- Added regression coverage for financial redaction plus administrator, corporate and Quality verification boundaries.
- Expanded setup from a read-only summary into responsive create/edit forms for plant areas and lines and guided use-case, data-domain, rejection-target and downtime-target rules.
- Added scoped uniqueness/parent validation, administrator authority, audit records and transactional outbox events to all setup hierarchy and profile mutations.

### Verification

| Command | Result |
| --- | --- |
| Focused V2 service suite | Pass: 20 tests, including role matrix and five audited setup transitions. |
| `npm run typecheck` | Pass. |

## 2026-08-11 — Edge Store-and-Forward Hardening

- Replaced the placeholder signed-config comment with fail-closed Ed25519 verification against a separately provisioned trust root.
- Added the canonical message ID as `Idempotency-Key`; without this, the API middleware would have returned 428 and no queued event could complete delivery.
- Changed replay to materialize and close the SQLite read cursor before deleting acknowledged queue rows.
- Added Go tests for config tamper rejection, duplicate queue suppression, failed-delivery attempt persistence, database close/reopen and exactly one accepted replay.
- Updated the example configuration and deployment documentation with canonical JSON signature and trust-root requirements.

### Verification status

The Go source/test contract is checked in, but `go test ./...` remains unexecuted because this host has no Go toolchain (`go: command not found`). This is not recorded as a passing binary gate.

The complete locally executable V2 regression after this change passes 57 backend/connector/performance tests, the 41-route production build and updated asset budgets (1,994,785 bytes JavaScript; 227,248 bytes CSS).

## 2026-07-19 — Phase 0: factual baseline

### Inputs inspected

- Read `HANDOFF2.md`, `PLAN_LATEST.md`, and the older `PLAN.md` completely.
- Read root and workspace package scripts, API Python configuration, all migrations through `0012_agent_runtime_contract`, environment template, Docker Compose, Playwright configuration, and Helm deployment templates.
- Inspected the checked-in API/evaluation/browser tests and traced the assistant, procurement, integration, and UI entry points.
- Preserved the pre-existing dirty working tree; no reset, checkout, migration rewrite, or unrelated cleanup was performed.

### Verified runtime findings

- Alembic reports one head: `0012_agent_runtime_contract`.
- `POST /agent/threads/{thread_id}/messages` calls `agent_service.run_message`.
- The live path calls the provider once, converts the result to one `IntentEnvelope`, and dispatches through the large conditional in `process_intent_envelope`.
- `agent_runtime.run_bounded_tool_loop` has no live caller. Its tests are helper-level tests only.
- `AgentThreadStateV2` is not the sole state writer. `agent_service.py` contains numerous direct `thread.context_state = state` assignments and continues to maintain legacy `procurement`, `intent`, and `pending_confirmation` keys.
- `AgentTurnDecision` remains active through provider compatibility, deterministic outage behavior, legacy tests, and the `request_task_update` compatibility branch.
- The capability registry declares 25 capabilities. Most have explicit conditional branches; `request_task_update` routes back through `AgentTurnDecision`. The registry's `adapter` value is descriptive metadata, not an executable adapter registry used by the runtime.
- Invalid model capability IDs are normally downgraded through deterministic intent selection, but direct requested capabilities still validate strictly. The previous `Unknown assistant capability` symptom is therefore consistent with mismatched UI/server capability versions or a direct stale action.
- The current Excel path is a CSV-only background master-data import supporting only supplier/item rows. It lacks XLSX, multi-sheet discovery, mapping profiles, preview/approval, lineage, dry run, incremental sync, conflict handling, versioned write-back, and round-trip reconciliation.
- The generic integration layer is ERP-adapter-specific. It does not yet implement the connector SDK and capability-manifest contract required by the target plan.
- The implemented canonical procurement lifecycle reaches requirement, RFQ, quotes, comparison, negotiation, award/PO, acknowledgement, gate, receipt, quality, cases, outbox, and reconciliation. Invoice capture/matching and finance handoff are not implemented end to end.
- Manual routes are split across legacy routes in `main.py`, V2 routes, and compatibility aliases. The web UI still exposes internal lifecycle concepts such as outbox and separate generate/preview/save/publish controls.

### Baseline commands and results

| Command | Result |
| --- | --- |
| `git status --short` | Very dirty pre-existing tree; preserved. |
| `git diff --check` | No whitespace errors; line-ending warnings only. |
| `cd apps/api && .venv/bin/alembic heads` | Pass: `0012_agent_runtime_contract (head)`. |
| `npm run test:api` | Fail before collection: root script invokes unavailable global `pytest`. |
| `cd apps/api && .venv/bin/pytest` | Collected 163; passed the 100 generated eval cases and 14 runtime helper tests, then stalled in `test_control_tower`; interrupted after more than two minutes. This is not a passing gate. |
| `npm run typecheck` | Pass. |
| `npm run check:api-contract` | Pass: `d2f69aff7802`. |
| `npm run build:web` | Pass; 25 static routes generated. |

### Baseline risks

- Existing evaluation count is inflated by 10 templates with deterministic noise variants; it is not the required 150 meaningful scenario corpus.
- Unit coverage can pass while the live assistant remains a one-shot router.
- Migration `0001` derives its baseline from current SQLAlchemy metadata, so fresh-install success does not independently prove historical upgrade safety.
- Docker, browser workflows, responsive screenshots, accessibility, and a clean migration upgrade remain unverified in this baseline.
- Vendor adapters without customer credentials are contract/mock-level only and must not be described as production-certified integrations.

### Next implementation phase

Phase 1 will make typed state persistence and deterministic business-number/entity resolution the sole supported state and resolution gateways, with live-path regression tests before the dispatcher is replaced.

### Baseline repair

- Updated the root API test script to use the repository-owned Python virtual environment. This makes `npm run test:api` reproducible without a global `pytest` executable.

## 2026-07-19 — Phases 1–3: typed state, adapters, bounded runtime

### Decisions

- Legacy state is accepted only at `load_thread_state`; every application write now passes through `persist_thread_state` and Pydantic validation.
- Added typed field provenance, pending confirmation, material-request continuation, last execution, attachment, selected-context, candidate, receipt, and blocked-state preservation.
- Capability adapter names are now executable registrations. Missing registrations return a safe unavailable response and are test-auditable.
- Removed the remaining live `request_task_update` conversion back to `AgentTurnDecision`.
- The live `run_message` path now invokes the LangGraph bounded observe/act loop. Groq may perform multiple authorized reads before one mutation/proposal; deterministic/provider-outage mode finishes safely from the first grounded observation.
- Runtime budgets now cover decisions, reads, total tool calls, candidates, mutations, proposals, and elapsed time. Provider configuration continues to enforce model token and context budgets.

### Files changed

- `apps/api/app/agent_schemas.py`
- `apps/api/app/agent_state.py`
- `apps/api/app/agent_resolution.py`
- `apps/api/app/agent_runtime.py`
- `apps/api/app/agent_capabilities.py`
- `apps/api/app/agent_service.py`
- `apps/api/tests/test_agent_intent_runtime.py`

### Verification

| Command | Result |
| --- | --- |
| `rg "thread.context_state =" apps/api/app` | Only the centralized writer in `agent_state.py` remains. |
| `cd apps/api && .venv/bin/pytest tests/test_agent_intent_runtime.py -q` | Pass: 16 tests. |

The live regression proves a single user turn can resolve a material through a read observation and then create exactly one canonical requirement with a persisted receipt. Existing exact RFQ, latest eligible requirement, mistyped code, relative date, missing-material approval continuation, provider fallback, and recent-ID tests remain green.

### Known limitations entering Phase 4

- `AgentTurnDecision` remains only as an older provider/test compatibility type and in the retired legacy decision implementation; it is no longer used by a registered capability adapter.
- Individual capability implementations are still physically co-located in `process_intent_envelope`; they are executable and registry-complete, but will be extracted as the remaining procurement vertical slices are completed.
- Supplier quote attachment currently stops at mapping/review guidance instead of creating every canonical quotation/extraction job automatically.

## 2026-07-19 — Phase 4 progress: procurement assistant slices

### Completed in this increment

- Assistant document attachment now calls the same buyer-quotation service as the manual upload path.
- RFQ, selected supplier, and material capability are deterministically authorized before linking documents.
- Reusing a document is idempotent and returns the existing quotation; it does not create a duplicate quote.
- Existing document validation/extraction jobs and extraction evidence are linked to the canonical quotation and exposed with their real statuses.
- Added controlled negotiation preparation: the assistant creates a draft, submits it for review, persists a preparation receipt, and creates a human proposal. Supplier communication is prepared only after explicit confirmation.
- Added controlled capabilities for PO supplier-email preparation, ASN recording, and evidence-backed exception closure.
- Expanded exact business-record status lookup through PO acknowledgement, ASN, Gate, Stores, Quality, negotiation, award, and exception records.
- Fixed a latent undefined authority variable in controlled RFQ/comparison/PO proposals.
- Added an explicit flush at the adapter boundary because the canonical SQLAlchemy session disables autoflush; grounding now always sees receipts created in the same turn.

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest tests/test_agent_intent_runtime.py -q` | Pass: 18 tests. |

New regressions prove canonical idempotent quote linking and that a negotiation produces no supplier outbox message before confirmation, then exactly one controlled message after confirmation.

### Remaining Phase 4 gate work

- Browser coverage for every role from requirement through Quality.
- Rich assistant cards/deep links for acknowledgement, inbound, Quality, and exception status.
- End-to-end selected-page context tests for all slices.
- A complete requirement-to-quality assistant demonstration without direct database setup.

### Additional Phase 4 evidence and browser environment result

- Added a role-chain regression proving Gate Operator, Store Manager, and Quality Inspector agents each prepare a controlled proposal, require the owning employee's confirmation, call the canonical inbound service, and persist an action receipt.
- The regression creates the Gate entry, then the linked Store receipt, then a Quality inspection with accepted/rejected quantities; all three receipts are asserted.
- Added a Playwright contract for natural-language requirement creation and its canonical record/deep-link card at desktop, tablet, and mobile sizes.
- Repaired Playwright's API server command to use `apps/api/.venv/bin/python`.
- Browser servers start successfully when allowed to bind locally, but Chromium cannot launch on this WSL image because `libnspr4.so` is absent. `npx playwright install-deps chromium` was attempted with elevated execution and failed because host `sudo` requires an interactive password. Docker is also unavailable in this WSL distro. Browser results remain pending and are not marked passing.

## 2026-07-19 — Phase 5 progress: manual workflow language

### Completed in this increment

- Purchase-order approval now generates the final locked PO artifact in the manual path, matching the assistant's canonical artifact behavior.
- Replaced the PO's always-visible preview/download/email controls with a state-driven `Order details → Approve → Send → Acknowledgement` sequence and one dominant action per state.
- Reworded technical PO actions into `Approve purchase order`, `View approved order`, and `Prepare supplier delivery`, while keeping supplier delivery and ERP synchronization as separate authority boundaries.
- Reworked comparison wording and progression into `Verified quotations → Recommendation → Approvals → Create order`; replaced `Generate / regenerate` and `Freeze` language with business-facing actions.
- Reworked negotiation into `Draft message → Approve → Supplier response → Reverify offer`, hiding irrelevant disabled lifecycle buttons and showing only the action valid for the selected state.

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest tests/test_agent_intent_runtime.py -q` | Pass: 19 tests after inbound role-chain coverage. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: 25 routes. |
| Targeted Playwright requirement conversation | Not executed: host browser library `libnspr4.so` missing. |

## 2026-07-19 — Shared page context and requirement workbench

### Completed in this increment

- Added a typed selected-page context to assistant requests. The API scopes the supplied record, rejects forged or cross-scope IDs, persists the canonical business identity in `AgentThreadStateV2`, and makes it available for pronouns such as “it” and “this requirement”.
- The assistant drawer now derives supported record context from route query parameters and sends only the selected entity type and ID; document linking accepts only valid document-link entity types.
- Added searchable approved-material selection to manual requirement entry and an inline, clearly separate governed material-master request path.
- Replaced the raw requirements table with a responsive list/detail workbench. It shows business numbers, material names, quantities, dates, reasons, status, and one state-aware next action without exposing internal UUIDs.
- Requirement selection is preserved in the URL and shared with the assistant and RFQ workbench.

### Files changed

- `apps/api/app/models.py`
- `apps/api/app/agent_state.py`
- `apps/api/app/agent_service.py`
- `apps/api/app/routers/agents.py`
- `apps/api/tests/test_agent_intent_runtime.py`
- `apps/web/components/industrial/AgentDrawer.tsx`
- `apps/web/components/industrial/IndustrialConsole.tsx`
- `apps/web/components/features/WorkflowForms.tsx`
- `apps/web/app/globals.css`

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest -q tests/test_agent_intent_runtime.py` | Pass: 20 tests, 1 upstream deprecation warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 25 static routes. |

Browser execution remains pending for the previously recorded missing host Chromium libraries; this increment does not claim visual-browser verification.

## 2026-07-22 — Phase 11 progress: supplier compliance governance

### Completed in this increment

- Added migration `0023_supplier_compliance` with tenant/plant-scoped supplier compliance requirements and immutable certificate evidence records.
- Added global or material-specific mandatory evidence requirements, supplier evidence submission, human verification/rejection, expiry-aware readiness, and supplier `conditional`/`approved` recalculation.
- RFQ supplier selection and publish now apply the same readiness gate; comparison rows explicitly disqualify suppliers with missing, pending, or expired evidence.
- Added supplier-compliance workbench forms to configure requirements, submit evidence, and review pending evidence.
- Evidence submission creates a canonical Purchase Manager task; a decision completes that task with evidence-backed completion text.
- Added role-scoped agent tools to explain actual supplier readiness and prepare a controlled evidence decision. The decision is only applied through the existing proposal confirmation boundary and produces an action receipt.

### Files and contracts

- Migration: `apps/api/migrations/versions/0023_supplier_compliance.py`.
- Persistence: `SupplierComplianceRequirement`, `SupplierCertificate`.
- APIs: `/procurement/supplier-compliance/requirements`, `/procurement/supplier-certificates`, `/procurement/supplier-certificates/{id}/decision`, and `/procurement/suppliers/{id}/compliance`.
- Assistant capabilities: `review_supplier_compliance`, `review_supplier_certificate_proposal`.

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest tests/test_supplier_compliance.py -q` | Pass: 3 tests. |
| Fresh SQLite `alembic upgrade head && alembic current` | Pass: `0023_supplier_compliance (head)`. |
| Capability registration assertion | Pass: 42 capabilities, every adapter registered. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 26 routes. |
| `git diff --check` | Pass; existing CRLF normalization warnings only. |

### Known limitations / next work

- Scheduled expiry reminders and historical supplier-performance/CAPA analytics are the next Phase 11 slice.
- Browser visual verification remains constrained by the previously recorded missing host Chromium libraries.

## 2026-07-22 — Phase 11 progress: supplier performance and corrective action

### Completed in this increment

- Added migration `0024_supplier_performance_capa` for immutable, source-linked supplier performance events and governed supplier corrective actions.
- Quality inspection now records an idempotent acceptance metric backed by the exact inspection quantities and purchase-order supplier; retries cannot create a second metric.
- Supplier performance summaries are calculated from persisted evidence events rather than manually editable ratings and report open corrective actions separately.
- Corrective actions must reference a tenant/plant-scoped inspection, return, or exception; cross-supplier evidence links are rejected.
- Opening an action creates a semantically idempotent Purchase Manager task. Closure requires corrective-action text plus effectiveness evidence and completes the task.
- Added manual workbench controls and role-agent capabilities for supplier performance summaries and opening corrective actions. Agent-created actions call the canonical service and persist a mutation receipt.
- Added APIs for supplier performance summaries, corrective-action listing/creation, and optimistic-concurrency-protected status updates.

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest tests/test_quality_replacement.py tests/test_supplier_compliance.py -q` | Pass: 8 tests. |
| Fresh SQLite `alembic upgrade head && alembic current` | Pass: `0024_supplier_performance_capa (head)`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 26 routes. |
| `npm run generate:api && npm run check:api-contract` | Pass: contract `6a6d88d463af`. |
| `git diff --check` | Pass; existing CRLF normalization warnings only. |

### Honest limitations

- This slice records quality acceptance. Delivery timeliness and commercial-response metrics still need equivalent event producers before they should influence recommendations.
- Corrective-action supplier communication still uses the existing governed supplier-channel/outbox boundary; the workbench deliberately does not silently send messages.

### Regression repair during wider gate

- The wider agent regression pack found that the newly added compliance-readiness function had been inserted inside `create_requirement`, making requirement creation return `None` before persistence. The function is now at module scope after the complete canonical requirement service; the exact RFQ transcript regression passes again.
- Test storage is now explicitly hermetic: `tests/conftest.py` clears developer MinIO/S3 credentials and uses `/tmp/genuinegigs-test-uploads`, so a local `.env` cannot make unit tests depend on external object storage.
- Supplier comparison now uses quantity-weighted, inspection-backed quality acceptance when evidence events exist and exposes the evidence-event count in score components. It retains the existing master score only when no operational evidence exists.
- Additional regression result: quote revisions, split awards, and quality/replacement/performance group passes 9 tests.

## 2026-07-22 — Phase 11 completion slice: payment status and lifecycle reconciliation

### Completed in this increment

- Added migration `0025_invoice_payment_status` with append-only, tenant/plant-scoped external payment observations. The model stores connection, external key/version, observation time, payload hash, and source evidence.
- Promoted `read_invoices` and `read_payment_status` into the contract-tested connector baseline and added persisted sync-job types for both datasets. No connector receives a payment-release write capability.
- Excel now recognizes, validates, imports, deduplicates, exports, and round-trip reconciles `PaymentStatus`. Unknown values and missing invoice references are row-level errors.
- Added a read-only payment-status API, invoice workbench display, integration dataset selectors, and the `check_invoice_payment_status` role-agent capability. Its response explicitly attributes the status to the latest external observation and creates no mutation receipt.
- Added deterministic requirement lifecycle reconciliation across active POs, original receipts, quality holds, rejected/recovered quantities, finance handoffs, payment observations, open cases, and linked corrective actions.
- Added manual and controlled-agent closure paths. Closure is rejected until every condition reconciles, uses optimistic concurrency in the manual API, persists a transition/audit event, and never implies that GenuineGigs released payment.
- Extended the golden procurement test: closure is blocked before external `paid` evidence and succeeds after a read-only observation is recorded.

### Contracts and files

- Migration: `apps/api/migrations/versions/0025_invoice_payment_status.py`.
- APIs: `/procurement/invoice-payment-statuses`, `/procurement/requirements/{id}/lifecycle`, `/procurement/requirements/{id}/close`.
- Agent capabilities: `check_invoice_payment_status`, `review_requirement_lifecycle`, `close_requirement_lifecycle_proposal`.
- OpenAPI contract: `11730827e5d2`.

### Verification

| Command | Result |
| --- | --- |
| Invoice/Excel/connector focused suite | Pass: 40 tests. |
| Lifecycle/connector/compliance/quality suite | Pass: 49 tests. |
| Golden Excel-driven procurement lifecycle | Pass, including blocked-before-payment and successful final closure. |
| Fresh SQLite migration | Pass: `0025_invoice_payment_status (head)`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Compilation and TypeScript stages passed; a prior complete build in this session produced 26 routes. |
| `npm run generate:api && npm run check:api-contract` | Pass: `11730827e5d2`. |

### Known limitations

- Vendor-specific payment-status adapters remain declared but customer-unverified; only the Excel/reference connector behavior is contract-tested.
- The product reads external payment status but intentionally cannot authorize or release payment.

## 2026-07-22 — Phase 12: knowledge, measurable readiness, analytics, and sourced briefs

### Completed in this increment

- Added versioned SOP/policy ingestion using the existing KnowledgeDocument/KnowledgeChunk framework. Admins create drafts, approve or retire them, and approval automatically retires the prior approved version of the same controlled source.
- Enforced plant scope and allowlisted role visibility for knowledge. Only approved, current sources visible to the active role/plant enter agent context; citations now deep-link to the setup review surface.
- Added a manual knowledge workbench showing source, version, approval state, role visibility, and governed decisions.
- Added a measurable customer-readiness service covering plant, seven operating roles, reporting lines, materials, suppliers, supplier capabilities, external connection, mapping profile, agents, and approved knowledge. Every check has an evidence route.
- Added source-reconciled operational metrics for requirement cycle time, task workload, blocker age, supplier quality acceptance, integration success, agent-run success, and agent feedback. Savings is deliberately reported unavailable until a customer-approved baseline policy exists.
- Added task-sourced morning and end-of-day briefs, including scoped priorities, overdue work, blockers, completions, and deep links. No opaque employee score is generated.
- Added a secret-free configuration export containing memberships/reporting, connection modes/capabilities, agent policies, and retention readiness.
- Added agent capabilities `get_daily_brief`, `summarize_management_metrics`, and `review_workspace_readiness`, plus a daily brief on My Work and readiness/metric cards in Admin.
- Corrected material resolution to reflect the real persistence invariant: only approved materials become Item rows; draft materials remain MaterialMasterRequest rows. The prior resolver referenced a nonexistent `Item.status` field.

### APIs and contract

- `/workspace/readiness`
- `/workspace/analytics`
- `/workspace/brief?period=morning|end_of_day`
- `/workspace/configuration-export`
- OpenAPI contract: `01169192b42e`.

### Verification

| Command | Result |
| --- | --- |
| Phase 12 service/agent tests | Pass: 5 tests. |
| Combined Phase 11/12/Excel/golden regression | Pass: 54 tests. |
| Exact natural-language requirement regression after material resolver fix | Pass. |
| Capability registration assertion | Pass: 50 capabilities, all registered. |
| `npm run typecheck` | Pass. |
| Production build | Compilation and TypeScript stages pass; prior complete build in this session produced all 26 routes. |
| OpenAPI regeneration/check | Pass: `01169192b42e`. |

### Remaining Phase 12 limitations

- Retention is reported as readiness evidence, but a complete customer-configurable retention policy editor and purge scheduler still belong to production-hardening work.
- Savings remains intentionally blank until the customer defines an approved comparison baseline; the platform does not manufacture a savings number.

## 2026-07-19 — Phase 4 governed supplier and evidence actions

### Completed in this increment

- Replaced the disconnected supplier-follow-up card with a controlled capability that resolves the scoped RFQ and shortlisted supplier, validates the supplier contact, creates a human confirmation proposal, and only after confirmation creates an idempotent approved delivery-queue message.
- Added controlled quotation-evidence decisions. The agent may prepare typed Accept/Correct/Reject decisions, but the quotation and extracted evidence remain unchanged until the Purchase Manager confirms the proposal.
- Both actions use canonical procurement/workflow services, persist action receipts at confirmation, and stop the bounded runtime after one proposal.
- Comparison generation now persists a grounded deterministic recommendation rationale and returns the recommended supplier, weighted score rationale, verified quote count, risks, artifact identity, and manual review action in its assistant card.
- Replaced raw inbound, Gate, Stores, and Quality data tables with responsive business record cards and selected-record links. The selected PO, Gate entry, receipt, or inspection is shared with the assistant.
- Simplified the approval page to decisions, comparison review, and award review; removed raw task/comparison ledgers and remaining “freeze comparison” language from the normal approval flow.

### Files changed

- `apps/api/app/agent_capabilities.py`
- `apps/api/app/agent_schemas.py`
- `apps/api/app/agent_service.py`
- `apps/api/app/procurement_v2.py`
- `apps/api/app/domains/workflows.py`
- `apps/api/tests/test_agent_intent_runtime.py`
- `apps/web/components/features/WorkflowForms.tsx`
- `apps/web/components/industrial/IndustrialConsole.tsx`
- `apps/web/app/globals.css`

### Verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest -q tests/test_agent_intent_runtime.py` | Pass: 22 tests, 1 upstream deprecation warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 25 routes. |

## 2026-07-23 — Supplier PO response and delivery portal

### Completed vertical slice

- Added a lightweight public supplier workspace backed by scoped, expiring PO tokens. Suppliers can view only the linked purchase order and lines, record an immutable acknowledgement or requested change, submit one or more partial delivery notices, upload dispatch/certificate evidence, and send a clarification to the responsible internal role.
- Acknowledgement replay with the same response is idempotent; a changed replay is rejected. The token remains usable until expiry for subsequent delivery and clarification operations without weakening its tenant, plant, supplier, purpose, or PO scope.
- Supplier delivery notices create the same canonical ASN used by Gate and Stores. Dispatch references are idempotent, changed duplicates conflict, and cumulative supplier-notified quantity cannot exceed the remaining PO quantity.
- Each delivery creates a semantic Store Manager task and notification. The Store/Gate/Purchase Manager/Admin role assistants can list these canonical supplier delivery notices without exposing internal UUIDs to business users.
- Supplier evidence enters private quarantine, passes the existing MIME/signature/filename controls through a validation-only document job, then becomes available as linked delivery evidence. It is not incorrectly sent through quotation extraction.
- Supplier clarifications create the canonical channel-message record and a scoped task/notification for the responsible Purchase Executive or Purchase Manager.
- The internal inbound workbench now shows supplier dispatch references, expected quantities/dates, vehicles, and evidence validation state. The public `/supplier/portal` screen provides mobile-safe business forms and no authenticated application navigation.

### Migration and contract

- `0033_supplier_delivery_portal.py`: additive ASN dispatch reference, expected delivery, source, supplier document linkage, and submission timestamp.
- New public contracts: PO context, delivery submission, delivery-evidence upload, and clarification submission under scoped supplier tokens.
- Shared OpenAPI client regenerated and verified at `b9465500ac84`.

### Verification

| Command | Result |
| --- | --- |
| Supplier portal + supplier channel + PO amendment + quality replacement + agent runtime group | Pass: 40 tests, 1 upstream LangGraph warning. |
| Fresh SQLite `alembic upgrade head` | Pass through head `0033_supplier_delivery_portal`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes including `/supplier/portal`. |
| OpenAPI regeneration/check | Pass: current hash `b9465500ac84`. |

### Honest limitations / next slice

- Uploaded certificate evidence is linked to the delivery but does not automatically become an approved supplier-certificate master record; internal verification remains required.
- The supplier portal does not yet expose a signed PO artifact download. That remains the next portal-completeness slice.

## 2026-07-23 — Supplier invoice portal intake

### Completed vertical slice

- Suppliers with a valid PO-scoped token and accepted acknowledgement can upload PDF, PNG/JPEG, or XLSX invoices from the same lightweight portal.
- Files enter the existing private quarantine and hardened document-validation pipeline. The validated file creates the canonical `InvoiceExtractionRun`, buyer verification task, and notification; it does not create a supplier invoice, run matching, hand work to Finance, or approve payment.
- Exact document replays are idempotent both before flush and after persistence, preventing duplicate extraction/review work during rapid browser retries or later resubmission.
- Internal Purchase Managers continue to verify extracted commercial fields through the same invoice workbench and canonical invoice service used by manual and assistant intake.

### Verification

| Command | Result |
| --- | --- |
| Supplier portal + invoice extraction/matching focused group | Pass: 10 tests, 1 upstream LangGraph warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| OpenAPI regeneration/check | Pass: current hash `8ba7dc4d92e1`. |

### Safety boundary

- Supplier upload is evidence intake only. Human verification remains mandatory before canonical invoice creation, and finance handoff remains separate from payment release.

## 2026-07-24 — Unified supplier RFQ and PO portal

### Completed vertical slice

- `/supplier/portal?token=…` now resolves either an RFQ invitation or a purchase-order response token and renders the correct business workflow instead of exposing an API token without a usable supplier screen.
- RFQ suppliers see only the exact invited request and lines, can view its final immutable PDF, submit all or selected lines as a partial/multi-line quotation, submit later immutable revisions, attach quarantined quotation evidence, ask clarifications, or record an idempotent no-bid reason.
- Quote submission updates the existing `RFQSupplierInvitation` to `responded`; no-bid updates it to `no_bid`, creates the canonical inbound supplier message, and notifies the Purchase Executive. Changed no-bid replays fail safely.
- Quotation evidence is linked to the supplier's latest current quote, deduplicated by scoped content hash, validated through the existing document pipeline, and creates the same extraction review evidence used by manual/email quotation intake.
- PO suppliers can view the exact final PO artifact linked to their token. Artifact selection supports the canonical `po` representation and the older `po_pdf` compatibility representation without widening tenant, plant, supplier, or entity scope.
- RFQ and PO outbound emails now include a clickable URL based on configured `web_base_url`; raw token text is no longer the expected supplier experience. Issued emails attach the canonical final artifact, fixing the older `po_draft`/`po_pdf` lookup mismatch.

### Verification

| Command | Result |
| --- | --- |
| Supplier portal + quote revision + supplier email focused group | Pass: 11 tests, 1 upstream LangGraph warning. |
| Golden procurement + PO amendment + portal/channel group | Pass: 16 tests, 1 upstream LangGraph warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| OpenAPI regeneration/check | Pass: current hash `17b6423d7767`. |

### Safety boundary

- Supplier-submitted values and documents remain `needs_review`; portal submission never verifies a quotation, selects a supplier, approves an award, issues a PO, or releases payment.

## 2026-07-24 — Immutable supplier delivery commitment updates

### Completed vertical slice

- Added immutable `SupplierDeliveryUpdate` records for supplier schedule changes, delays, and expedites. Each update retains the previous and revised commitment, supplier reason, external retry key, ASN/PO/supplier lineage, and submission time.
- Supplier portal updates are strictly token-, tenant-, plant-, supplier-, PO-, and ASN-scoped. Updates are refused after the delivery reaches Gate.
- Exact retries return the same update; a changed payload under the same external reference conflicts. The ASN keeps a current expected-delivery projection while the immutable update history remains auditable.
- Delays create a critical Purchase Manager coordination task and notify both Purchase and Stores. Expedites/same-date schedule changes use action severity. Audit evidence records the old date, new date, and classified change.
- The supplier PO portal lets the supplier revise a submitted delivery commitment and explains that Stores and Procurement will be notified.
- Store/Gate/inbound workspaces load delivery-update history and show the supplier reason and changed commitment on the canonical ASN card.
- Store/Gate/Purchase Manager/Admin assistant delivery summaries include the latest revised commitment and supplier-provided reason.

### Migration

- `0034_supplier_delivery_updates.py`: immutable scoped delivery-update table, external-reference uniqueness, lineage indexes, and constrained update classification.

### Verification

| Command | Result |
| --- | --- |
| Supplier delivery + PO amendment + bounded-agent focused group | Pass: 35 tests, 1 upstream LangGraph warning. |
| Fresh SQLite migration | Pass through head `0034_supplier_delivery_updates`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| OpenAPI regeneration/check | Pass: current hash `79a7203c20c3`. |

## 2026-07-24 — Supplier invoice email convergence

### Completed vertical slice

- Extended the governed inbound supplier-email service from quotation-only processing to typed `quotation` and `invoice` evidence.
- Invoice email association requires an exact scoped PO reference and exactly one verified supplier contact matching that PO. Missing/wrong senders, forged PO references, cross-workspace documents, and unvalidated attachments fail before records change.
- Valid invoice attachments create the same canonical `InvoiceExtractionRun`, evidence, Purchase Manager review task, and notification used by portal/manual capture.
- Email intake stops before canonical invoice creation, deterministic matching, finance handoff, or payment. The source file remains mandatory human-review evidence.
- External message replay returns the existing extraction and creates neither a duplicate channel message nor duplicate review work.
- The Integration workbench now lets an operator choose quotation or invoice email evidence and presents the matching RFQ/PO context with business-facing language.

### Verification

| Command | Result |
| --- | --- |
| Supplier channel + invoice matching + supplier portal group | Pass: 16 tests, 1 upstream LangGraph warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| OpenAPI regeneration/check | Pass: current hash `817fccc715fb`. |

### Honest boundary

- This is a deterministic authenticated mailbox simulator and canonical processing service. Production IMAP/provider webhooks, domain authentication, bounce feedback, and customer retention acceptance remain environment-specific channel work.

## 2026-07-24 — Supplier email acknowledgement, ASN, and evidence parity

### Completed vertical slice

- Extended typed inbound supplier email to `po_acknowledgement` and `delivery_notice` in addition to quotation and invoice evidence.
- Refactored acknowledgement and ASN services so a validated portal token or a pre-resolved verified email supplier/PO context enters the same canonical authorization, quantity, state, idempotency, task, notification, case, and audit logic.
- Structured email acknowledgements support accepted, rejected, and change-requested states; rejected/changed responses create the same Purchase Manager review work as portal responses.
- Structured email delivery notices require an accepted acknowledgement, enforce remaining PO quantity, deduplicate dispatch references, and create the same canonical ASN and Store handoff.
- Optional already-validated dispatch documents or material certificates link through one shared ASN-document service. Cross-workspace or previously linked evidence fails safely.
- The Integration workbench exposes all four supported message types and only asks for fields relevant to the selected business operation.

### Verification

| Command | Result |
| --- | --- |
| Supplier channels + portal + PO amendments + invoice matching group | Pass: 21 tests, 1 upstream LangGraph warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| OpenAPI regeneration/check | Pass: current hash `b6f375a62287`. |

### Honest boundary

- Email body text is never trusted to authorize or infer a commercial/inventory consequence. The authenticated simulator supplies explicit structured fields after sender and record association; production provider ingestion still needs customer-specific mailbox acceptance and an operator review boundary for ambiguous messages.

## 2026-07-22 — Clean bootstrap, safety hardening, connector contract, and UI terminology

### Factual findings and completed work

- The golden workbook contained organization, plant, user, and reporting-line sheets, but the importer ignored them. The Excel connector now discovers, validates, imports, reconciles, and exports those entities with external-key lineage. Imported accounts are invited with unusable generated credentials; no password or credential data is exported.
- The golden demonstration now starts from a genuinely empty customer workspace and proves the lifecycle without manual database inserts. Business-number uniqueness is tenant scoped, so a clean tenant cannot collide with demo or another customer's sequence.
- The bounded-agent evaluation corpus now contains 150 explicit procurement scenarios plus runtime regressions, including misspellings, partial commands, exact/latest/page references, relative dates, attachments, missing-material continuation, topic changes, and conversational turns.
- Connector contracts now include approval references, reconciliation, ambiguous-result recovery, error classification, health, and capability reporting. Production-class write modes require an explicit acceptance reference, tested capabilities, the server write flag, and the existing emergency kill switch. SOAP and iPaaS are honest reference/conformance adapters only, not claimed customer-ready integrations.
- Uploaded files reject unsafe names, signature/MIME mismatches, EICAR test content, active PDF constructs, and known prompt-injection instruction patterns. Suspicious document text is isolated from model extraction and requires human evidence review.
- Retention enforcement now includes agent checkpoints, honors thread legal holds, is disabled by default, and runs through an audited daily worker only when explicitly enabled.
- Added operational metrics for agent runs/tool calls/latency, supplier email delivery, connector synchronization, and retention enforcement.
- Removed direct access to the legacy technical agent workspace, removed technical task terminology from user cards and search, and converted the old outbox presentation to business-facing controlled external delivery. Workbook mapping preview now recognizes organization and team sheets.

### Migration and contract changes

- `0026_retention_holds.py`: legal holds and retention evidence.
- `0027_tenant_scoped_business_numbers.py`: replaces global business-number uniqueness with `(tenant_id, business_number)` constraints.
- Shared OpenAPI client regenerated and verified at `fe32e971d480`.

### Verification

| Gate | Result |
| --- | --- |
| Agent evaluation + runtime regression | Pass: 175 tests. |
| Excel connector + clean golden lifecycle | Pass: 15 tests. |
| Connector conformance/control suite | Pass: 36 tests. |
| Focused agent/connector/retention suite | Pass: 62 tests. |
| Document hostile-input checks | Pass: selected 4 tests. |
| Fresh SQLite migrations | Pass through head `0027_tenant_scoped_business_numbers`. |
| OpenAPI regeneration/check | Pass: `fe32e971d480`. |
| Frontend typecheck | Pass. |
| Frontend production build | Pass: 26 routes. `/agent` is retained only as a redirect to My work. |
| Broad selected backend run | Progressed beyond 90% with no failure, then hit the previously reproduced environment-wide synchronous FastAPI `TestClient` deadlock; interrupted without claiming a pass. |
| Playwright client-demo screenshot flow | API and web servers started and migrated successfully; Chromium could not launch because the host lacks `libnspr4.so`. No browser pass or new screenshot is claimed. |
| Docker Compose | Not runnable in this WSL environment because the `docker` command is unavailable; Docker Desktop WSL integration must be enabled before this gate can be executed. |

### Honest limitations

- The local document denylist and structural checks are defense in depth, not a replacement for a customer-approved malware scanning service in production.
- Vendor-specific ERP adapters remain reference boundaries until tested against customer credentials, mappings, middleware, and acceptance environments.
- Full Playwright/browser and Docker Compose verification still require completion in an execution environment where those services can run reliably.

## 2026-07-22 — Versioned procurement policy engine

### Baseline finding

- Comparison, split-award, and invoice services enforced several safe invariants, but there was no customer-configurable procurement policy record or immutable evaluation. Minimum quote count, currency/validity rules, segregation, approval requirements, split-award permission, and invoice tolerances therefore could not be configured and evidenced as required by Phase 11.

### Completed vertical slice

- Added versioned draft/active/retired procurement policies and immutable, entity-version-bound policy evaluations.
- Added typed policy contracts for competitive-quote thresholds, allowed currencies, quote validity, split awards, requester/comparer segregation, approval roles, delivery tolerance, and invoice price/quantity tolerances.
- Activating a policy is Admin-only, explicit, retires the prior active version, and writes an audit event containing the approved rules.
- Comparison submission now deterministically evaluates the active policy before generating approval work. Blocking findings return exact business explanations; justified emergency/single-source exceptions remain visible in the persisted evaluation.
- Approval tasks are generated from the active policy's supported role matrix rather than a hard-coded pair.
- Split awards fail safely when the active policy disallows them.
- Invoice matching now applies active percentage tolerances and embeds the exact thresholds and policy version in match evidence.
- Added Admin workbench controls to create and activate human-readable policy versions.
- Added the role-scoped `explain_procurement_policy` assistant capability. It reads persisted rules/evaluation and never asks the model to calculate or override policy.

### Migration, contracts, and verification

- `0028_procurement_policy_engine.py`: procurement policies and immutable policy evaluations. It is additive/idempotent for this repository's compatibility migrations.
- Fresh SQLite migration passes through head `0028_procurement_policy_engine`.
- Policy, agent runtime, invoice, split-award, golden lifecycle, and 150-scenario evaluation group: **186 passed**, one upstream LangGraph warning.
- Focused policy/invoice/split/golden group: **10 passed**.
- Shared OpenAPI client regenerated and verified at `6d3b0c5103f5`.
- Frontend typecheck passes.
- Optimized frontend production build passes with 26 routes.

## 2026-07-22 — Supplier-requested PO changes

### Baseline finding and completed behavior

- Supplier PO acknowledgements only supported accept/reject, leaving the documented requested-change → amendment path disconnected.
- The supplier portal now accepts an explicit `change_requested` response with proposed confirmed quantity, delivery date, and rationale. The one-time scoped portal token, ordered-quantity cap, tenant isolation, and audit controls remain unchanged.
- A requested change creates an owned Purchase Manager task and notification and updates the linked exception timeline. It does not mutate the issued PO or permit inbound activity as an accepted acknowledgement.
- The PO workbench shows supplier-requested terms and can link the response while preparing the existing immutable amendment workflow.
- Linking marks the supplier response `change_prepared`, records reviewer/time/revision lineage, completes the review task, and preserves the currently issued version until the separately approved external change is acknowledged.
- The Purchase Manager/Admin role agent can pass the same acknowledgement reference to the existing typed `prepare_po_change` adapter.

### Migration and verification

- `0029_supplier_acknowledgement_changes.py`: requested-change evidence, review lineage, linked PO revision, and expanded acknowledgement states.
- Fresh SQLite migration passes through head `0029_supplier_acknowledgement_changes`.
- PO change + bounded-agent regression: **28 passed**, one upstream warning.
- Dedicated amendment suite: **4 passed**, including supplier request → assigned work → immutable linked amendment.
- Shared OpenAPI contract regenerated and verified at `a98d2a39b218`.
- Frontend typecheck and optimized 26-route production build pass.

## 2026-07-22 — Structured inbound exception control

### Baseline finding

- Gate, Stores, and Quality could record basic quantities, but the live records did not preserve structured wrong-material, certificate, damage, defect, or production-impact evidence. Exceptions therefore appeared as generic receipt/inspection states and could be closed without proving that material identity and certificate blockers were resolved.

### Completed vertical slice

- Extended the canonical Store receipt with exception types, observed item code, certificate review, business notes, and production-impact evidence.
- Extended the canonical Quality inspection with certificate review, defect codes, inspection notes, and production-impact evidence.
- Receipt processing now deterministically detects shortages/backorders, excess quantity against the active procurement-policy tolerance, damage, wrong material, and missing or invalid certificates.
- Inspection processing prevents wrong material or material with unresolved certificate evidence from entering usable inventory. Accepted, rejected, and held quantities continue through the existing canonical inventory-impact and replacement workflow.
- Each inbound exception appends structured evidence to the canonical case, creates semantically idempotent owned work, notifies the responsible procurement role, and alerts the Plant Manager when production impact is declared.
- Quality disposition creates a governed integration-outbox request; it does not claim an ERP update before connector acknowledgement and reconciliation.
- Case closure now fails safely while a receipt exception lacks inspection evidence or certificate evidence remains unresolved.
- Store and Quality assistant capabilities accept the same structured fields and invoke the same canonical services as their manual workbenches.
- Store and Quality workbenches expose business-facing evidence controls and display the resulting exception context without raw runtime terminology.
- Excel/CSV import and versioned exchange export now round-trip the same receipt and inspection exception evidence, including arrays and production-impact flags.

### Migration, contracts, and verification

- `0030_structured_inbound_exceptions.py`: additive Store receipt and Quality inspection evidence columns.
- Fresh SQLite migration passes from an empty database through head `0030_structured_inbound_exceptions`.
- Quality, Excel connector, golden procurement demo, bounded-agent runtime, procurement-policy, and PO-amendment regression group: **55 passed**, one upstream LangGraph warning.
- The golden Excel regression explicitly edits, imports, persists, exports, and re-imports structured receipt and inspection evidence without creating duplicate business records.
- Shared OpenAPI client regenerated and verified at `251f35d231b1`.
- Frontend typecheck passes.
- Optimized frontend production build passes with 26 routes.

## 2026-07-22 — Governed supplier-invoice document capture

### Baseline finding

- Canonical invoice entry, deterministic two/three-way matching, exception blocking, finance-review handoff, Excel synchronization, and read-only payment status existed. Supplier invoice documents, however, could only be referenced during manual data entry: there was no invoice-specific extraction record, evidence review queue, duplicate document protection, or assistant attachment tool.

### Completed vertical slice

- Added invoice-specific structured extraction for PDF, image/OCR, and XLSX documents while reusing the hardened document quarantine, MIME/signature, active-content, malware-marker, spreadsheet-formula, parser-limit, and prompt-injection isolation controls.
- Added an invoice-specific Groq structured schema. Document instructions remain untrusted data; deterministic canonical services still validate and persist the reviewed invoice.
- Added immutable extraction evidence, parser/model version, linked purchase-order context, human-verified values, reviewer identity/time, and resulting canonical invoice lineage.
- The manual Invoice workbench now supports purchase-order-scoped upload, safe background status polling, recoverable errors, and a human evidence-review form. Commercial fields do not enter matching until the Purchase Manager verifies them.
- The Purchase Manager/Admin role agent can classify a validated attachment against an exact purchase order and returns a compact evidence-review card. It creates one persisted action receipt and never claims that an unverified invoice was captured.
- Verification calls the existing canonical invoice service. Supplier/PO checks, order-line validation, total validation, duplicate supplier invoice number, and duplicate content-hash controls therefore apply equally to manual and assistant-originated documents.
- Successful extraction creates semantically idempotent Purchase Manager work and a notification; successful verification completes that work and links the source document to the canonical invoice.
- Matching and finance handoff remain unchanged: deterministic policy tolerances apply, exceptions block finance handoff, and no payment or journal operation is exposed.

### Migration, contracts, and verification

- `0031_invoice_document_extraction.py`: additive invoice extraction/evidence/reviewer lineage table; compatibility-safe when earlier baseline migrations create current mapped tables.
- Fresh SQLite migration passes from an empty database through head `0031_invoice_document_extraction`.
- Invoice document + bounded agent regression: **30 passed**, one upstream LangGraph warning.
- Quality, Excel connector, golden procurement demo, bounded-agent runtime, policy, PO amendment, and invoice group: **61 passed**, one upstream warning.
- The broader synchronous TestClient production group again deadlocked after 30 completed tests in the previously isolated environment-wide TestClient issue; it was interrupted and is not reported as a pass.
- Shared OpenAPI client regenerated and verified at `89bd12435131`.
- Frontend typecheck passes.
- Optimized frontend production build passes with 26 routes.

## 2026-07-22 — Source-versioned foreign-currency normalization

### Baseline finding and completed behavior

- Comparison previously multiplied foreign quotations by a bare `exchange_rate_to_inr` supplied with the quotation. That number had no authoritative source, observation timestamp, buyer identity, or immutable evidence and could distort the recommendation anchor.
- Added tenant/plant-scoped exchange-rate observations with source/target currencies, positive rate, source name/reference, observation timestamp, status, recorder, business number, and audit evidence.
- A supplier-declared rate is no longer recommendation evidence. Non-INR quotations are deterministically disqualified until a Purchase Manager/Admin links a verified observation whose currency pair matches the quotation.
- Cost anchors exclude foreign quotations lacking valid evidence, preventing an ungrounded low rate from depressing other suppliers' cost scores.
- Comparison rows now persist the source currency, applied INR rate, evidence source, and observation timestamp alongside the normalized landed-cost breakdown.
- The quotation upload workbench accepts a source currency; evidence review can record a customer treasury/reference rate and explicitly link it to the quotation. The comparison allocation view exposes the exact source used.
- Added separate bounded agent tools to record a sourced rate and apply an existing observation. They remain separate one-mutation turns, create receipts, and use the same currency service as the workbench.

### Migration, contracts, and verification

- `0032_exchange_rate_evidence.py`: exchange-rate observations plus optional quotation evidence linkage; compatibility-safe for current mapped-table bootstrap migrations.
- Fresh SQLite migration passes from an empty database through head `0032_exchange_rate_evidence`.
- Currency normalization, agent rate tools, split awards, and quote revisions: **9 passed** across their focused groups.
- Full currently affected procurement group: **68 passed**, one upstream LangGraph warning.
- Shared OpenAPI client regenerated and verified at `bf768bb83729`.
- Frontend typecheck and optimized 26-route production build pass.

## 2026-07-22 — Invoice-match exception ownership and closure

- Deterministic invoice-match exceptions now create one semantically idempotent, blocked Purchase Manager task and one notification containing the persisted invoice link and exact variance codes.
- Re-running an unchanged exception updates the existing blocker instead of creating duplicate work.
- After corrected supplier/source or receipt evidence produces a passing current match, the prior match is superseded and the exception task is completed with evidence identifying the passing match.
- The Invoice workbench now explains the concrete variance, identifies the source/receipt correction path, and exposes a single `Rerun after correction` action. Finance handoff remains blocked until the current deterministic result is matched.
- Invoice regression: **6 passed**, one upstream warning. Frontend typecheck and optimized 26-route build pass.

## 2026-07-22 — Phase 13 production-hardening increment

### Factual findings and changes

- Uniform response hardening was absent. Added CSP, frame denial, MIME sniffing protection, no-referrer, restricted browser permissions, no-store, and production HSTS headers through API middleware.
- Retention timestamps and prose existed but no enforceable operation or legal hold existed. Added `RetentionHold`, admin-only dry-run/enforcement/hold routes, explicit confirmation, CSRF/idempotency coverage, and audit evidence.
- Retention enforcement redacts expired private message content, citations, thread context, agent event/tool/run payloads, and checkpoints; it deletes expired personal memory and retired knowledge chunks. Business records, proposals, successful action receipts, and audit events are deliberately preserved.
- Fixed an agent runtime regression found by the full suite: a function-local import shadowed the canonical requirement resolver and broke exact RFQ generation by business number.
- Added a production pilot/recovery runbook covering staged modes, isolated restore reconciliation, emergency disable/manual continuity, ambiguous-write handling, retention/legal hold, incidents, rollback, and evidence required for Excel/read-only/shadow/limited-write acceptance.

### Migration and verification

- `0026_retention_holds.py`: governed tenant-scoped retention holds.
- Retention plus management tests: 7 passed.
- Fresh SQLite migration: pass from empty database through `0026_retention_holds`.
- Agent evaluation/runtime prefix: first 147 tests pass after the RFQ resolver fix. The next FastAPI `TestClient` case deadlocks in this runner; a single health test reproduces the environment issue and was terminated after 15 seconds. This is not recorded as a whole-suite pass.
- Frontend typecheck: pass.
- Optimized production build: pass, 26 routes.
- Shared OpenAPI client regenerated and contract check passes at `40d8f58c77cb`.
- `git diff --check`: pass; only existing CRLF normalization warnings were emitted.
- Live Uvicorn `/health` header check: pass; emitted correlation ID, CSP, frame denial, MIME-sniffing protection, no-referrer, restricted permissions, and no-store.

### Acceptance limitations

- No customer PostgreSQL backup/PITR restore was executed; the required drill and evidence format are documented, not falsely claimed.
- Live Groq, SMTP, vendor ERP, penetration, dependency/image/secret scans, Docker health, and customer limited-write acceptance remain environment/credential-dependent gates.
- `npm audit` was not run because approval to transmit the dependency manifest to the external npm advisory registry was denied; no substitute scan is claimed.
- Several broad pytest commands consistently pass their service/agent prefix and then deadlock on the first FastAPI `TestClient` request in this execution environment. Focused direct-service suites, fresh migrations, live Uvicorn, OpenAPI, typecheck, and production build are the verified gates; the entire 238-test suite is not claimed as passing.

## 2026-07-22 — Evaluation and clean Excel bootstrap corrections

### Factual gaps fixed

- The checked-in agent evaluation contained 100 suffix permutations across only ten base requests. Added 50 explicit workplace edge scenarios for misspellings, terse commands, exact/latest/page references, relative dates, material lookup, attachment language, missing-master continuation, and ordinary conversation. Common `genrate`, `requirment`, `reqirement`, and `comparision` phrasing now resolves safely in degraded mode.
- The golden workbook contained Organizations, Plants, Users, and ReportingLines, but all four sheets were silently ignored. Added canonical preview/validation/commit adapters, lineage, idempotent external state, invited-account creation with unusable random credentials, memberships, plant access, disabled agent profiles, reporting hierarchy, and credential-free round-trip export.
- The golden lifecycle previously ran against the transactionally seeded demo tenant. It now creates a fresh workspace, proves it has zero requirements/POs, imports the workbook, completes the lifecycle, exports, reconciles, and re-imports without duplicate records.
- Fresh workspace creation duplicated the creator when their account was also a standard demo seat. The creator account is now excluded from demo-seat reconciliation.
- Clean multi-workspace execution exposed global `business_number` uniqueness. Business references are now tenant-scoped in ORM metadata and migration `0027_tenant_scoped_business_numbers`; unrelated customers can safely have the same PR/RFQ/PO sequence values.

### Verification

- Agent evaluation plus runtime regressions: 175 passed.
- Excel connector plus clean golden lifecycle: 15 passed.
- Fresh SQLite migration from base through `0027_tenant_scoped_business_numbers`: passed.
- Golden lifecycle now proves clean-workspace bootstrap, external organizational/master/transaction import, requirement through replacement/reinspection and finance handoff, paid-status closure, versioned export, reconciliation, and duplicate-free re-import.
| `cd apps/api && .venv/bin/pytest -q tests/test_control_tower.py` outside restricted thread sandbox | Pass: 20 tests, 1 warning. A minimal Starlette blocking portal proved the in-sandbox hang is an execution restriction rather than application middleware. |
| `npm run test:api` outside restricted thread sandbox | Pass: 171 tests, 1 warning in 36.26 seconds. |

The full suite exposed and corrected obsolete legacy assertions that expected the removed `context_state.procurement` compatibility key. The regression now proves schema-v2 `draft_fields` are authoritative. It also exposed a false “created” response on idempotent requirement retries: retries now return an existing-record summary, emit no extra mutation receipt, and retain exactly one requirement, task, delegation, tool call, and mutation receipt.

## 2026-07-19 — Phase 7 completion and Phase 8/9 connector foundation

### Coordination and proactive procurement

- Added database-enforced semantic identity for active tasks and deduplicated notifications, including concurrent task-creation race handling.
- Added a five-minute proactive procurement sweep for missing supplier responses near deadline, extraction review, expiring quotation validity, overdue comparison approval, missing PO acknowledgement, quality exceptions, and failed external synchronization.
- Alerts are tenant/plant scoped, role routed, linked to canonical business workbenches, factual, and remain deduplicated after being read.
- Added a fixed-time regression for notification scope, links, recipient assignment, and repeat-run idempotency.

### Excel/CSV external-system connector

- Added persisted connector definition, mapping profile, import batch, row lineage, export batch, and external record-state contracts.
- Added safe XLSX, UTF-8 CSV, and ZIP-of-CSV discovery with sheet/row/archive limits, signature checks, path traversal protection, and formula rejection. Workbook formulas, macros, scripts, and links are never executed.
- Added dry-run preview with insert/update/unchanged/conflict/error counts and one-based source sheet/row/cell lineage.
- Added approved item/supplier commits using stable external keys, payload hashes, external record state, idempotent re-import, and stale local-version conflict protection.
- Added versioned XLSX export that never overwrites the source and neutralizes spreadsheet formula injection.
- Added API routes for manifest, preview, row detail, approval, and versioned export plus an Integration Centre preview/approval UI.
- Added focused tests covering multi-sheet commit, unchanged re-import, stale conflict, hostile formula input/output, and malicious ZIP members.

### Universal connector SDK foundation

- Added a provider-neutral manifest and adapter contract for connection test, pull, prepare, validate, dispatch, idempotency, read-after-write verification, and reconciliation evidence.
- Added explicit disconnected/read-only/simulation/shadow/UAT/limited-production/production modes, tested-capability enforcement, stable write keys, optimistic external versions, and an emergency write disable.
- Added conformance-tested reference connectors for Excel/CSV, generic REST/OpenAPI, generic OData, SFTP/file exchange, and a customer-hosted private bridge. These are reference/simulator adapters and are not claimed as customer-certified live implementations.
- Added connector discovery API and per-connection enabled-capability/write controls.

### Migrations

- `0014_excel_connector_contracts.py`: connector definitions, mapping profiles, import batches and row results, export batches, external record states.
- `0015_connector_controls.py`: provider version, enabled capabilities, connection configuration, and emergency write switch.

### Verification

| Command | Result |
| --- | --- |
| Focused Excel connector tests | Pass: 3 tests. |
| Connector conformance + Excel tests | Pass: 19 tests. |
| Fresh SQLite `alembic upgrade head` / `current` | Pass: head `0015_connector_controls`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 25 routes. |
| `npm run test:api` | Pass: 193 tests, 1 upstream LangGraph warning, 58.22 seconds. The first run exposed an undefined `/agent/home` response variable; it was corrected before this clean rerun. |

### Honest limitations / next work

- The canonical workbook currently commits Items and Suppliers; remaining procurement sheets have preview/lineage schemas but require canonical commit adapters as the next Phase 8 slice.
- Mapping profile editing, golden workbook fixtures, complete requirement-to-invoice round trip, assistant Excel capabilities, and downloadable reconciliation reports remain pending.
- Generic REST/OData/SFTP/private bridge connectors currently pass deterministic conformance simulation; no live customer system has been certified.

### Golden fixture evidence

- Added a reproducible generator and checked-in `genuinegigs_procurement_exchange_v1.xlsx`, stale-conflict workbook, hostile-formula workbook, mapping profile, and expected summary manifests under `apps/api/tests/fixtures/excel_erp/`.
- The workbook declares all 29 exchange sheets and includes two plants, seven operating roles, ten materials, six suppliers, inventory, requirements, open PO, partial receipt, quality hold, invoice, and payment-status examples.
- A clean import regression proves ten items, six suppliers, and one canonical requirement are created without manual database writes. Transaction sheets whose canonical adapters remain pending are explicitly isolated with row errors rather than reported as imported.

## 2026-07-19 — Versioned mappings, assistant spreadsheet operations, and invoice matching

### Excel mapping and assistant completion

- Added versioned customer mapping profiles with supersession, canonical required-field validation, and an allowlist of deterministic transforms (`strip`, `uppercase`, `lowercase`). Arbitrary code/expression transforms are rejected.
- Integration preview accepts an active mapping version and persists its version on every source-row result. The Integration Centre now loads and selects customer mappings.
- Added Admin assistant capabilities to preview an attached XLSX workbook and explain the latest/selected import errors. Both use the same connector service and persisted batches as the manual path; preview mutations create action receipts.
- Added regressions for custom-header mapping, transform enforcement, persisted mapping lineage, and assistant/manual connector equivalence.

### Invoice, matching, and finance review

- Added canonical supplier invoice, invoice line, match result, and finance handoff records.
- Invoice capture validates supplier/PO identity, line ownership, totals, non-negative amounts, and duplicate supplier invoice numbers.
- Matching deterministically compares invoice amount/quantity against PO lines and, when present, actual receipt quantities. It produces evidence and explicit variances for two-way or three-way matching.
- Match exceptions block finance handoff. A successful handoff is idempotent and records `payment_release: not_authorized`; no payment or accounting-post action was added.
- Added scoped APIs and a state-driven `Invoices & matching` Purchase Manager workbench.
- Added assistant matching and controlled finance-handoff preparation. The handoff remains absent until the owning employee confirms the proposal; confirmation creates the canonical handoff and action receipt.

### Migration

- `0016_invoice_matching.py`: supplier invoices and lines, deterministic match results, and finance-review handoffs.

### Verification

| Command | Result |
| --- | --- |
| Excel/mapping/assistant focused tests | Pass: 6 tests. |
| Invoice service and agent confirmation tests | Pass: 3 tests. |
| Fresh SQLite migration | Pass: head `0016_invoice_matching`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 26 routes including `/invoices`. |
| `npm run test:api` | Pass: 198 tests, 1 upstream LangGraph warning, 37.62 seconds. |

## 2026-07-19 — Transactional Excel round trip and connector control centre

### Transactional spreadsheet import

- Extended the dependency-ordered Excel commit path from master data/requirements through external-owned purchase orders and lines, partial receipts, quality dispositions, supplier invoices, and invoice lines.
- External-owned POs are canonical `PODraft` records with nullable local award provenance and explicit `external_owned` mapping metadata. No parallel PO model or workflow was introduced.
- Every committed row now persists stable external state, source sheet/row/hash lineage, canonical version, and an audit event.
- Same-batch duplicate external keys are isolated during preview. Invalid references, unsupported statuses, invalid inspection dispositions, duplicate invoice numbers, and invoice-total mismatches are row errors rather than partial silent writes.
- Missing source records use the explicit safe policy `retain_and_report`; imports never infer deletion or silently tombstone canonical records.

### Controlled export and reconciliation

- Versioned exchange exports now include externally keyed POs/lines, receipts, quality status, invoices/lines, `POExport`, `Reconciliation`, and `SyncLog` sheets.
- Platform-originated purchase orders are separated into `POExport` rather than emitted into an input sheet that could duplicate them on re-import.
- Export verification reopens the generated XLSX and proves every expected external identity survived. The API persists a `ReconciliationResult` with hashes and missing-key evidence and reports verification failure honestly.
- Golden export re-import leaves Item, Supplier, PO, Receipt, Inspection, and Invoice record counts unchanged.
- Golden stale PO input conflicts after a local version change and never overwrites the newer canonical state.

### Fixture and safety matrix

- Added reproducible invalid-required-field, partial-record, duplicate-key, hostile-formula, stale-version, incremental-revision, and 5,000-row fixture workbooks.
- Added focused assertions for each specific row error and bounded scale discovery.

### Connector Control Centre

- Added registry-backed connection creation for Excel/CSV, generic REST/OpenAPI, OData, SFTP/file, and private bridge reference adapters.
- New connections expose only contract-tested capabilities, start with writes disabled, accept only secret-manager references, and support disconnected/read-only/simulation/shadow/UAT modes.
- Added visible reference-vs-customer-verified status, per-connection write state, emergency write disable, and disconnect controls. Manual workflows remain independent of connector state.
- Generic connection tests now call the common connector SDK instead of falling through to the local ERP adapter.

### Migration

- `0017_external_owned_purchase_orders.py`: permits mirrored external POs without fabricating a local award.

### Verification

| Command | Result |
| --- | --- |
| Excel connector suite | Pass: 11 tests. |
| Excel + invoice + connector conformance | Pass: 25 tests. |
| Fresh SQLite migration | Pass: head `0017_external_owned_purchase_orders`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 26 routes. |
| `npm run test:api` | Pass: 203 tests, 1 upstream LangGraph warning, 56.87 seconds. |

### Golden RFQ and supplier-channel evidence

- Extended workbook ingestion to canonical item specifications, supplier contacts, and approved supplier-item capabilities.
- The golden regression now proves imported capability data is used by `create_rfq_from_requirement`; no supplier shortlist is fabricated or seeded outside the workbook.
- The same regression publishes that RFQ through the canonical governed workflow and proves the imported supplier email receives one idempotent `approved_pending_send` outbox message linked to the RFQ. Final-artifact object storage is isolated in this service test; artifact generation itself remains covered by its existing workflow tests.
- Corrected connection and mapping-profile creation so generated primary keys are flushed before their audit events are recorded.
- Replaced mutable Pydantic collection defaults in connector request contracts with per-request factories.

### Latest focused verification

| Command | Result |
| --- | --- |
| `cd apps/api && .venv/bin/pytest -q tests/test_excel_connector.py` | Pass: 11 tests, 1 upstream LangGraph warning, 9.29 seconds. |

## 2026-07-19 — Governed spreadsheet evidence, export, and approval

### Completed

- Added a downloadable row-level CSV reconciliation/error report for each scoped import batch. It contains source hash, sheet/row lineage, external key, action, canonical link, mapping version, and validation codes, with private/no-store response headers.
- Found and closed a CSV parser safety gap: formula-like values are now rejected consistently in CSV and ZIP-of-CSV inputs, matching the existing XLSX formula policy. Reports and workbook exports also neutralize formula-injection prefixes.
- Moved versioned exchange generation, private storage, read-after-write verification, persisted reconciliation, and audit into one canonical `create_exchange_export` service. Manual API and assistant now call this identical service.
- Added role-scoped `export_excel_exchange`; it returns only filename/status/count evidence to the model and persists an action receipt. Workbook bytes never enter model context.
- Added controlled `approve_excel_import_proposal`. A clean preview remains unchanged until the Admin confirms the persisted proposal; invalid/conflicting batches are refused before proposal creation. Confirmation calls the same canonical commit service as the manual workbench.
- Updated imported-PO detail assembly to support externally owned canonical POs without inventing a local award or quotation. Manual workbench payloads now state `external_system` provenance.

### Verification

| Command | Result |
| --- | --- |
| Excel connector suite after CSV/report work | Pass: 12 tests, 1 warning. |
| Excel + typed runtime focused suite after assistant export | Pass: 37 tests, 1 warning. |
| Controlled spreadsheet approval regression | Pass: no canonical row before confirmation; canonical item and completed batch after confirmation. |

## 2026-07-19 — Connector acceptance evidence and golden procurement cycle

### Connector orchestration

- Added an executable acceptance report across Excel/CSV, generic REST/OpenAPI, OData, SFTP/file, and private-bridge reference adapters.
- Each report run exercises connection availability, incremental-pull response shape, write preflight, simulation, semantic idempotency, UAT acknowledgement, read-after-write hash reconciliation, stale-version rejection, and emergency write disable.
- Added scoped JSON and downloadable CSV report endpoints and exposed the evidence download in the Integration Centre.
- The report explicitly marks all adapters as not live-customer-verified and states that customer credentials and UAT acceptance remain required.
- Sync-job creation now rejects disconnected connections and missing enabled capabilities. Registry-backed jobs execute through the common SDK and persist per-capability counts, cursors, and `has_more`; they no longer fall through a legacy ERP adapter.

### Golden lifecycle evidence

- Added `test_golden_procurement_demo.py`, which proves this single canonical flow without a live ERP:
  Excel import → requirement → RFQ → governed supplier publication → portal quotation → human field verification → deterministic comparison → Plant Manager and Purchase Executive approvals → PO → approved integration outbox → simulated external acknowledgement → supplier PO acceptance → ASN → Gate entry → Store receipt → Quality acceptance → three-way invoice match → finance-review handoff → versioned Excel export → read-after-write reconciliation → idempotent re-import.
- The finance handoff asserts `payment_release: not_authorized`; the test never releases payment or writes directly to an external database.
- Re-import proves no duplicate Item, Supplier, PO, Receipt, Inspection, or Invoice records, and the cycle produces a substantive audit trail.
- Object-storage artifact generation is isolated in this service-level golden test; artifact rendering/storage has separate coverage. Browser visual acceptance remains blocked by the documented WSL browser-library prerequisite.

### Verification

| Command | Result |
| --- | --- |
| Connector conformance suite | Pass: 18 tests. |
| Connector + Excel focused suites | Pass: 31 tests before sync orchestration addition. |
| Golden procurement lifecycle | Pass: 1 end-to-end service scenario, 1 warning, 1.75 seconds. |

### Remaining Phase 8/11 boundary

- The golden workbook configures procurement data inside an already-created workspace; organization/user invitation bootstrap from workbook is not yet a safe supported commit path.
- The golden lifecycle proves full accepted delivery. Rejected quantity → supplier replacement → reinspection and final exception closure remain Phase 11 work and are not claimed complete.

## 2026-07-19 — Honest vendor boundaries and inbound supplier email parity

### Vendor connector claims

- Added Oracle Fusion, SAP S/4HANA, Microsoft Dynamics 365, and Odoo contract boundaries to the shared registry.
- These manifests declare intended canonical scope but expose no tested capabilities, cannot pull or write, return `customer_validation_required`, and default new connections to that status.
- The executable conformance report lists them as skipped/customer-validation-required rather than counting them as passing reference adapters.

### Supplier email channel

- Added persisted `SupplierChannelMessage` records with tenant scope, external-message idempotency, sender, RFQ/supplier links, document IDs, canonical quote IDs, status, and failure evidence.
- Added an authenticated inbound-email simulator for customer demos and contract tests. It requires an exact RFQ business reference, exactly one selected supplier contact matching the sender, and validated same-workspace document IDs.
- Processing calls `attach_uploaded_quote_documents`, so email, assistant upload, and manual upload create the same canonical quote/extraction/verification records.
- Replaying the same external message or document is idempotent. Unknown senders and cross-workspace attachments are rejected before quote creation.
- Added an Integration Centre test-channel form and visible supplier-message history. This is explicitly not represented as a production IMAP/provider webhook until customer channel acceptance is performed.
- Fixed quality inspection for external-owned POs to resolve the canonical PO line directly rather than assuming a GenuineGigs award/quote exists.

### Migration and verification

- `0018_supplier_channel_messages.py`: persisted governed supplier-channel messages and external-message uniqueness.
- Connector/vendor plus inbound-email focused tests: 24 passed.
- Fresh disposable migration: pass, head `0018_supplier_channel_messages`.

## 2026-07-22 — Rejected-material return, replacement, and reinspection

### Completed vertical slice

- Added canonical supplier-return records linked to the originating PO, inspection, supplier, and existing procurement `Case`.
- Purchase Manager/Admin can prepare a bounded return only up to the remaining rejected quantity.
- Supplier replacement communication is idempotent and enters the governed `approved_pending_send` outbox; the assistant can only create it through a controlled proposal and human confirmation.
- Stores records replacement arrival against the return, with challan/vehicle evidence and a dedicated replacement `StoreReceipt`; Quality receives a canonical reinspection task.
- Reinspection writes the normal `InspectionResult` and `InventoryImpact`, updates the return to accepted/rejected/partial state, and appends visible case history.
- Case closure now distinguishes original receipts from replacement receipts and requires accepted replacement coverage for original rejected quantity.
- Three-way matching excludes replacement receipts from payable received quantity, preventing replacement stock from being counted twice financially.
- Added a state-driven Return → Replacement → Reinspection manual panel on Store, Quality, and Case workbenches plus role-scoped assistant tools.
- Removed a cyclic receipt/return database FK while retaining the indexed scoped reference and service validation; authoritative Return → Inspection and Inspection → Receipt FKs remain.
- Hardened test database initialization by disabling SQLite FK enforcement only during metadata teardown/recreation, allowing recovery from partial local test schemas.

### Migration

- `0019_supplier_returns_replacements.py`: supplier-return transaction records and indexed replacement-receipt linkage.

### Golden-demo extension

- The Excel-driven golden lifecycle now records a 10-unit quality rejection, prepares and sends a governed replacement request, receives replacement stock, reinspects and accepts it, closes the exception case, and still proves a 200-unit three-way invoice match rather than incorrectly counting 210 units.

### Verification

| Command | Result |
| --- | --- |
| Replacement + typed-agent focused suite | Pass: 27 tests. |
| Replacement + golden demo + invoice suite | Pass: 7 tests. |
| Fresh SQLite migration | Pass: head `0019_supplier_returns_replacements`. |
| Complete API suite | Pass: 218 tests, 1 upstream LangGraph warning, 42.22 seconds. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 26 routes. |
| OpenAPI regeneration/check | Pass: current hash `b098780e248d`. |

## 2026-07-22 — Multi-line partial bids and immutable quote revisions

### Runtime findings and completed slice

- Confirmed that RFQs and quotes had line tables, but supplier ingestion filled every omitted RFQ line with defaults. A supplier therefore could not submit a truthful partial bid.
- Confirmed that the secure supplier link was consumed after its first submission, so a supplier could not submit a revision through the canonical portal path.
- Quote ingestion now accepts only explicitly submitted lines, validates every RFQ-line/material reference, rejects duplicate line participation, and caps offered quantities at the requested quantity.
- Each supplier/RFQ submission creates an immutable revision with a monotonically increasing revision number and `supersedes_quote_id`; the prior current revision is marked `superseded` without deleting or editing its quote lines or evidence.
- Supplier links remain scoped and expiring but can submit later immutable revisions. First/last use remains observable through `used_at`; acknowledgement tokens retain their one-time behavior.
- Added `participation_status` so omitted lines and partial quantities are visible rather than silently treated as complete bids.
- Added quote currency and an explicit positive exchange rate to INR. Comparison normalizes landed-cost values before anchoring and scoring, while retaining original commercial values on the quote.
- Comparison and readiness gates ignore superseded revisions and evaluate only current verified supplier revisions.

### Migration and tests

- `0020_quote_revisions_partial_bids.py`: adds quote revision lineage, participation status, currency, and dated-rate input storage (rate date/source remain a later policy slice).
- Focused revision/partial-bid tests: pass, 2 tests.
- Existing golden lifecycle and control-tower tests were exercised alongside the new tests; the long combined runner streamed beyond the command wrapper, so the complete API suite is being rerun in bounded groups before this phase is marked complete.
- Fresh SQLite migration: pass through head `0020_quote_revisions_partial_bids`.
- Shared OpenAPI client regenerated and contract check passes at `ec0d0fdab815`.
- Frontend typecheck passes.
- Optimized production build passes with 26 routes.
- The full API command reached 65% with no reported failure, but its process did not return a terminal summary through the execution wrapper. It is therefore recorded as incomplete verification, not a pass; the last fully completed whole-suite result remains the 218-test pass before migration 0020.

## 2026-07-22 — Split and partial supplier awards

### Completed vertical slice

- Added immutable `AwardBatch` records bound to an approved comparison version and canonical allocation hash.
- Purchase Managers can allocate each supplier-request line across one or more current, verified supplier quote lines. Service validation caps totals by both requested quantity and each supplier's offered quantity.
- Replaying the identical allocation is idempotent and returns the same batch and POs. A different allocation against the same approved comparison version is rejected; changing the commercial decision requires a new comparison version.
- Existing `AwardDecision`, `AwardLine`, `PODraft`, artifact generation, and integration outbox services remain canonical. One award/PO is created per supplier quote, with line-level allocation lineage.
- The comparison workbench now shows every eligible supplier line, offered/requested quantities, recommended defaults, editable awarded quantities, and one explicit confirmation that creates separate unsent supplier orders.
- The Purchase Manager agent prepares the same explicit recommended allocation in its controlled proposal. Human confirmation calls the same split-award service as the manual workbench.
- Added offered and requested quantities to comparison rows so business users can understand and safely edit allocation decisions.
- Corrected `/health/ready` migration validation: readiness now compares the database revision with the actual Alembic script head instead of the obsolete hard-coded `0007` revision.

### Migration and verification

- `0021_split_award_batches.py`: immutable award batch and award-decision batch lineage.
- Split-award tests: 2 passed, covering two-supplier allocation, two canonical POs/outbox events, exact replay, changed replay rejection, and over-allocation rejection.
- Split + quote revision + golden lifecycle focused group: 5 passed.
- Split + bounded-agent runtime group: 26 passed.
- Fresh SQLite migration: pass through head `0021_split_award_batches`.
- Live Uvicorn `/health`: pass with simulation safety modes reported.
- Shared OpenAPI contract regenerated and current at `d98c9d5161f0`.
- Frontend typecheck: pass.
- Optimized production build: pass, 26 routes.
- FastAPI/Starlette `TestClient` requests hang in this execution sandbox even for a two-line standalone FastAPI application and with both AnyIO 4.9 and 4.14. The dependency experiment was reverted. TestClient-dependent files therefore remain an explicit environment-runner verification gap; service tests and live Uvicorn verification pass.

## 2026-07-22 — Immutable PO amendments, cancellations, and supplier reissue

### Completed vertical slice

- Issued purchase orders are no longer candidates for in-place commercial edits. An amendment or cancellation creates a new immutable `PODraft` version with root/previous lineage, revision number/kind, reason, structured change summary, cloned lines, and a versioned business reference.
- Amendment validation requires at least one known source line, positive quantities, and prevents reducing total ordered quantity below stock already received.
- Cancellation is rejected once an ASN or receipt exists; users must use quantity amendment/return flows instead.
- Only one change per PO root may be awaiting approval or dispatch. New inbound ASN, Gate, and Store activity is paused while that uncertainty exists.
- Approval freezes a final versioned artifact and creates a distinct `amend_purchase_order` or `cancel_purchase_order` integration event. It does not mutate the current issued version.
- Simulation dispatch produces explicit change acknowledgement, then marks the old version `superseded` or `cancelled`. The new amendment becomes the issued version; cancellation versions and the previous version become cancelled.
- Live connectors without verified amendment/cancellation support fail safely rather than reusing create-PO semantics or claiming success.
- Supplier acknowledgement delivery is regenerated for the new version with amendment/cancellation wording and version metadata.
- The manual PO workbench now exposes a business-facing change/cancel flow, revision review, and separate approval action. It explains that the current order remains effective until external acknowledgement.
- Purchase Manager/Admin agents can prepare an immutable PO change and create a controlled approval proposal. Proposal confirmation calls the same canonical approval/integration service as the manual workbench.

### Migration and verification

- `0022_po_versions_amendments.py`: PO root/version lineage, revision metadata, change evidence, issued/superseded timestamps, and expanded terminal states.
- PO version tests: 3 passed, covering immutable amendment, controlled dispatch, supplier reissue, cancellation, delivery guard, and inbound pause.
- PO + split award + bounded-agent + golden focused group: 30 passed.
- Fresh SQLite migration: pass through head `0022_po_versions_amendments`.
- Live Uvicorn `/health`: pass in simulation mode.
- Shared OpenAPI contract regenerated and current at `a2da10d70bfa`.
- Frontend typecheck: pass.
- Optimized production build: pass, 26 routes.

## 2026-07-19 — Phase 5/6/7 progress: recoverability, proposal UI, coordination identity

### Completed in this increment

- Manual requirement entry now preserves title, reason, assignee, and line details locally across recoverable failures or navigation, validates restored material selections, and provides an explicit Clear draft action.
- Agent-home actions now come from the live role capability registry rather than legacy seeded action strings. Empty-state suggestions are therefore role-authorized.
- Fixed a critical proposal UI defect: Confirm/Reject buttons no longer send `confirm_proposal` as an assistant capability. They call the governed proposal APIs directly, require a rejection rationale, show the recorded decision, and refresh workspace records, tasks, notifications, and badges.
- Normal assistant record cards now use a business-field whitelist and hide internal UUIDs, proposal IDs, artifact IDs, action names, and other runtime fields.
- Proposal creation and confirmation now update the sole typed thread-state gateway consistently: pending proposal is set centrally, cleared after decision, and the successful receipt reference is retained.
- Added database-enforced partial unique indexes for active task semantic identity and unread notification deduplication. `create_task` also handles concurrent uniqueness races through a savepoint and returns the canonical existing task.
- Added a regression proving repeated active delegation returns one task while a completed work cycle permits a new task with the same semantic identity.
- Repaired migrations 0011 and 0012 to be additive/idempotent when earlier baseline migrations created tables from current ORM metadata. Migration history remains intact.

### Migration

- `0013_coordination_idempotency.py`: partial unique indexes on `(tenant_id, semantic_key)` for active tasks and `(tenant_id, dedupe_key)` for unread notifications.

### Verification

| Command | Result |
| --- | --- |
| Fresh SQLite `alembic upgrade head` then `alembic current` | Pass: all revisions applied; current head `0013_coordination_idempotency`. |
| `cd apps/api && .venv/bin/pytest -q tests/test_agent_intent_runtime.py` | Pass: 23 tests, 1 warning. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 25 routes. |
## 2026-07-24 — Agent clarification and direct-action grounding audit

### Runtime correction

- Confirmed that the live message boundary invokes the bounded tool loop and validates every selected capability against the role-scoped registry.
- Removed active user-facing clarification language inherited from the command-router era. Requirement clarification now names a uniquely resolved approved material and asks a direct question containing only the missing business fields.
- Removed the internal phrase `approved material master match` from live requirement responses.
- Fixed a shared-path defect where an explicit assistant action (`requested_capability`) discarded material, quantity, date, and catalog entities extracted from the accompanying natural-language message. Button-triggered and model-triggered capabilities now use the same grounded argument merge.
- Added a regression for a partial, natural-language requirement invoked through an explicit capability action.

### Verification

- Agent natural-language evaluation: 151 passed.
- Bounded intent/runtime suite after the correction: 25 passed.
- Lifecycle, connector, invoice, quality, supplier-channel, policy, retention, and golden-demo service group: 101 passed.
- ERP adapter contract group: 4 passed.
- The monolithic suite and all `TestClient`-based HTTP files cannot produce a terminal result in this execution sandbox because even a two-line standalone FastAPI `TestClient` request blocks until externally terminated. This is isolated from application startup and service tests; HTTP route verification remains required in an environment where the AnyIO test portal can create its worker thread.

## 2026-07-24 — Incremental SQLite migration and browser-harness audit

- Playwright application startup exposed that revision `0032_exchange_rate_evidence` used a plain foreign-key `ALTER TABLE`, which SQLite cannot perform. Fresh-schema tests had not exercised an upgrade beginning at revision 0031.
- Changed the additive, not-yet-released revision to use Alembic batch alteration for the quotation exchange-rate evidence column and index.
- Proved a real incremental SQLite upgrade from `0031_invoice_document_extraction` through head `0034_supplier_delivery_updates`.
- Frontend typecheck passes.
- Optimized production build passes with 27 routes.
- Playwright discovers 45 desktop/tablet/mobile tests. With localhost binding permitted, the API and Next servers start successfully and migrations complete. Chromium then fails before page creation because the host lacks `libnspr4.so`; no browser assertion has been claimed as passing.

## 2026-07-24 — Golden Excel conflict and management evidence

- Strengthened the clean-workspace Excel lifecycle to mutate an externally owned PO after synchronization, preview an older/conflicting workbook, prove the PO row is classified as `conflict`, commit the batch, and prove the newer local status and external-state version remain unchanged.
- Added factual morning-brief and manager-metric evidence to the same end-to-end lifecycle and asserted that no opaque employee score is produced.
- The stronger scenario exposed a SQLite/PostgreSQL timestamp portability bug in management cycle-time analytics. Both stored timestamps are now normalized before subtraction.
- Updated `README.md` with deterministic fixture-generation, golden-demo, and connector-safety commands and an explicit statement of vendor-adapter limitations.
- Replaced the obsolete runtime-truth document that incorrectly said the bounded loop was inactive and Excel was CSV-only. The document now traces the live request, typed state, registry/adapters, manual convergence, spreadsheet, connector, ERP, supplier-channel, and verification paths plus honest host limitations.

### Verification

- Golden lifecycle plus management insights: 6 passed.
- Excel, connector conformance, golden lifecycle, and management group: 57 passed.
- Document MIME, malware, active-content, prompt-injection, formula, and landed-cost safety subset: 5 passed.

## 2026-07-24 — Governed negotiation counteroffer completion

- Added an executable negotiation lifecycle from buyer draft through submission, explicit manager approval, approved-pending-send supplier communication, inbound supplier counteroffer, acceptance, mandatory commercial-field re-verification, and regenerated comparison.
- The regression proves that no supplier message exists before approval, that accepting a revised price invalidates the prior quote verification, that comparison remains blocked until every eligible quotation is verified, and that the comparison cost basis uses the revised price.
- Negotiation service plus assistant proposal regressions: 2 passed.
- Complete non-`TestClient` backend matrix, including agent evaluation/runtime and document safety subsets: 287 passed, 6 intentionally deselected HTTP-dependent tests.

## 2026-07-24 — Complete API regression and provider isolation

- Confirmed the earlier FastAPI `TestClient` hang was caused by sandbox thread isolation: the representative authorization test passes outside the sandbox.
- The first complete run with the developer Groq key exposed that grounded-response narration could replace ASCII hyphens inside persisted business numbers with Unicode non-breaking hyphens. Added deterministic identifier preservation after narration and a direct regression covering RFQ and requirement numbers.
- Test configuration now clears `GROQ_API_KEY`, just as it already clears object-storage credentials. Unit/service/API tests never consume a developer model account or depend on network availability; provider tests mock the typed boundary. Live Groq remains an explicit environment acceptance check.
- Aligned the inbound over-receipt conflict with the established API contract while retaining the active-policy limit in the business-facing detail.
- Added ZIP-of-CSV fanout and path-traversal regressions to the spreadsheet safety matrix.

### Verification

- Complete API suite, including TestClient routes, authorization/isolation, agent evaluation/runtime, lifecycle, Excel, connectors, security, supplier channels, and golden demo: **331 passed**, 1 dependency warning, 75.62 seconds.

## 2026-07-24 — Final migration, browser, and responsive-workspace verification

### Schema compatibility correction

- Browser startup against an incrementally upgraded database exposed eight
  scoped tables that were created before `ScopedMixin.public_id` became part
  of the current ORM contract.
- Added additive migration `0035_scoped_public_ids.py` to backfill UUID public
  identifiers, enforce non-null values, and create unique indexes for those
  tables. Existing migration history was not rewritten.
- Audited mapped ORM columns against the upgraded schema and found no remaining
  missing schema contracts.

### Browser and workspace correction

- Removed duplicate Admin navigation entries at both API composition and
  frontend rendering boundaries.
- Prevented arbitrary task metadata objects from rendering as raw `{}` in
  business cards.
- Clarified the RFQ screen title and removed an accessible-name collision in
  the purchase-order workflow stepper.
- Tightened desktop assistant width, intermediate responsive breakpoints, and
  the canonical 1440×900 client-demo capture.
- Screenshot capture now waits for the role assistant to reach its settled
  available state.

### Final verified gates

| Command | Result |
| --- | --- |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: optimized production build, 27 routes. |
| `apps/api/.venv/bin/python apps/api/scripts/check_openapi_contract.py` | Pass: current hash `b6f375a62287`. |
| Fresh SQLite `alembic upgrade head` / `alembic current` | Pass: `0035_scoped_public_ids (head)`. |
| `apps/api/.venv/bin/pytest -q` | Pass: 331 tests, 1 upstream warning, 79.14 seconds. |
| `npx playwright test` with locally extracted NSS/NSPR libraries | Pass: 43 tests; 2 intentionally skipped duplicate screenshot-project cases. |

### Remaining host gate

- Docker is not installed or integrated in this WSL distribution. Docker
  Compose startup and container health are not claimed and must be executed on
  a Docker-capable host before a production release.

## 2026-07-24 — Live-provider gate and dependency hardening

### Live Groq evidence

- Replaced the previous readiness-only helper with a read-only 20-scenario
  scorecard that invokes the same `provider_response` tool-selection boundary
  as the live message path.
- The scorecard executes no capability adapter, creates no procurement record,
  and keeps external writes disabled.
- Tightened tool descriptions for latest requirements, specific-material
  approval questions, complete requirement facts, and quotation attachments.
- Final post-upgrade live result: **18/20 (90%)**, model
  `openai/gpt-oss-120b`, prompt `role-playbook@2`, above the 85% pilot
  threshold. One Groq 429 used safe deterministic fallback and was counted as
  a failed live-provider scenario.

### Dependency remediation

- Upgraded Next.js to 16.2.11 and pinned patched PostCSS 8.5.22 and Sharp
  0.35.3 after the first npm audit found high-severity advisories.
- Upgraded to FastAPI 0.139.2, Starlette 1.3.1, LangGraph 1.2.9,
  LangChain Core 1.5.1, and LangChain Groq 1.1.3 after `pip-audit` found
  advisories in the previous framework ranges.
- Regenerated the shared OpenAPI client from the upgraded live API and stamped
  contract hash `19529b40f71b`.

### Post-upgrade verification

| Command | Result |
| --- | --- |
| `apps/api/.venv/bin/pytest -q` | Pass: 331 tests, one upstream TestClient deprecation warning, 60.78 seconds. |
| Live Groq scorecard | Pass: 18/20 (90%); external writes disabled. |
| `apps/api/.venv/bin/pip-audit` | Pass: no known third-party vulnerabilities. |
| `apps/api/.venv/bin/pip check` | Pass: no broken requirements. |
| `npm audit --omit=dev --audit-level=high` | Pass: zero vulnerabilities. |
| `npm run check:api-contract` | Pass: `19529b40f71b`. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: Next.js 16.2.11, 27 routes. |
| Full Playwright suite | Pass: 43 tests, two intentional duplicate screenshot skips. |
| Required viewport evidence | Captured at 1440×900, 1280×800, 1024×768, 768×1024, and 390×844. |

## 2026-07-24 — Docker Compose and PostgreSQL recovery gate

- Reached Docker Desktop's Linux engine through the Windows Docker CLI despite
  the WSL `docker` shim reporting that integration was disabled.
- The first real PostgreSQL migration exposed that Alembic's default
  `alembic_version.version_num` was `VARCHAR(32)` while revision
  `0017_external_owned_purchase_orders` is longer.
- Updated the not-yet-successfully-applied 0017 migration to widen the Alembic
  control column to 128 characters before Alembic records that revision.
- Rebuilt and started the stack successfully. PostgreSQL, Redis, MinIO,
  Mailpit, API, and web report healthy; migration, MinIO initialization, and
  seed jobs exit zero; Celery worker and beat start cleanly.
- API `/health/ready` reports database, migration, object storage, Redis, and
  agent provider healthy. PostgreSQL reports migration head
  `0035_scoped_public_ids`.
- Performed an isolated `pg_dump`/restore into
  `genuinegigs_restore_drill`. Source and restore reconcile exactly:
  `10 users | 27 purchase requirements | 0035_scoped_public_ids`.
- Migrated a second empty PostgreSQL database from revision 0001 through
  `0035_scoped_public_ids`, proving the fresh PostgreSQL chain independently
  of the existing upgraded volume.
- Fixed MinIO initialization to create the primary documents bucket in
  addition to quarantine/evidence, keep all buckets private, and enable
  versioning on all three. A two-version object recovery check restored and
  read back `recovery-v2` and proved both source version IDs remained.
- Added a root `.dockerignore`; the web build context fell from approximately
  612 MB to 4 KB while the containerized 27-route production build continued
  to pass.
- Docker Scout is installed, but scanning would transmit locally built image
  package metadata to Docker's external service. That scan requires explicit
  user authorization and has not been claimed.

### Final container browser verification

- The first Compose-backed responsive run exposed a tablet-only navigation
  race in the test harness: the assistant was opened while the authenticated
  `/login` shell was still redirecting to the role workspace, and the route
  transition remounted the drawer.
- Updated both role-workflow and screenshot helpers to wait for the completed
  post-login route and to treat drawer-open, conversation-loaded, and composer
  enabled as one retryable readiness boundary.
- Repeated the affected tablet natural-language requirement scenario three
  times against the running Compose application: **3/3 passed**.
- Re-ran the complete suite against the healthy PostgreSQL/Redis/MinIO/API/web
  Compose stack: **43 passed, 2 intentionally skipped screenshot duplicates,
  0 failed** in 2.7 minutes.
- Final static closeout after the browser correction:
  `npm run typecheck` passed, OpenAPI contract hash `19529b40f71b` is current,
  and `git diff --check` reported no whitespace errors.

### Controlled-pilot acceptance pack

- Added `docs/runbooks/customer-pilot-acceptance.md` as the fillable
  customer-environment evidence contract for Phase 13.
- It records deployment versions, data flows, role and supplier-token
  permissions, accepted connector capabilities, mapping lineage, Excel,
  read-only, shadow/UAT and limited-write stages, incident/manual-continuity
  drills, penetration-test preparation, support/SLA ownership, and sign-off.
- Blank or customer-unverified rows remain explicitly unaccepted; the template
  does not turn reference adapters or local simulations into customer ERP,
  security, privacy, SMTP, recovery, or production-write claims.

## 2026-07-24 — Clean customer workspace and Admin-owned team onboarding

### Runtime findings

- The fresh-workspace service assigned the creator the `plant_manager` role,
  although employee-account administration is correctly protected by the
  `admin` role.
- Local development also attached six existing Apex demo accounts to every new
  tenant. A nominally fresh customer workspace therefore depended on demo
  identities and could not be managed by its creator through the Admin UI.
- Canonical account creation already persisted `Account`, `User`,
  `WorkspaceMembership`, `UserPlantAccess`, and `AgentProfile`, so this phase
  repaired that path instead of introducing a second identity or agent system.

### Implemented behavior

- Workspace creation is now Admin-only. The creator becomes the new tenant's
  Admin owner and receives the governed Admin agent profile.
- Fresh tenants no longer inherit any Apex account or transaction. They start
  with one Admin membership, one plant, and the standard department structure.
- The Admin account form now collects employee name, work email, temporary
  password, business role, department, plant access, and reporting manager.
- Server-side account creation validates department/plant/manager tenant scope,
  creates the reporting line, and provisions the correct role-specific tool
  allowlist, restricted-action policy, model configuration, and escalation
  manager.
- Invitation acceptance now provisions the same role-specific agent policy as
  direct Admin account creation.
- Workspace readiness requires all six operational roles in addition to the
  Admin owner before reporting that the tenant is ready for master-data import.
- The setup experience explicitly describes a clean workspace, redirects its
  Admin owner into setup, and links to the canonical account-management page.

### Verification

| Command | Result |
| --- | --- |
| Focused onboarding regression selection | Pass: 6 tests. |
| `apps/api/.venv/bin/pytest -q tests/test_role_agents.py` | Pass: 18 tests. |
| `npm run typecheck` | Pass. |
| `npm run build:web` | Pass: Next.js 16.2.11, 27 routes. |
| Docker Compose rebuild | Pass; API and web healthy, jobs exited zero. |
| `npm run generate:api` | Pass; contract hash `bf9f8a3a14ed`. |

### Product limitation

- An account currently has one primary governed role per workspace. Supporting
  simultaneous multi-role memberships would require an explicit authorization
  and role-switching contract and is not represented as complete.

## 2026-08-11 — GenuineGigs V2 Phase 0 and operational-core increment

### Implemented

- Added the code-aligned V2 technical audit and V1 reuse/migration map.
- Added migration `0045_v2_operational_core` with plant hierarchy, shifts,
  work orders, plan/actual points, downtime/quality events, operational
  deviations, V1-linked Operational Actions, evidence references and Value
  Ledger entries.
- Added the explainable baseline forecast and idempotent
  `production_behind_plan` detector. A new deviation creates one V1 task, one
  Operational Action, one estimated value entry and one canonical outbox event.
- Added tenant-scoped `/api/v2` context, plant, area, Command Center and actual
  ingestion endpoints.
- Added the API-backed Pune Plant demonstration slice with four machining lines,
  Shift B and the Line 3/CNC-04 recovery incident.
- Added the first V2 application shell and `/v2/home` Command Center using
  TanStack Query, Recharts, semantic design tokens, responsive layouts and
  loading/degraded/empty states.

### Verification

| Check | Result |
| --- | --- |
| Operational core scenarios | Pass: 2 tests |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| TypeScript typecheck | Pass |

## 2026-08-12 — Evidence-recorded V2 objective-agent runtime

### Implemented

- Replaced the placeholder V2 agent worker event with a deterministic bounded
  context pipeline over canonical deviations, actions, material risks and
  connector health.
- Persisted each objective-agent run, its hydrated context hash, three explicit
  read-tool records, structured observation events and a structured grounded
  recommendation. Free-form output is never interpreted as an executable side
  effect and the runtime records zero mutations.
- Connected `gigi.activity.created` to the objective-agent runtime through the
  transactional outbox consumer with correlation-based idempotency.
- Surfaced persisted `gigi.recommendation.created` records through the existing
  Gigi activity history while preserving explicit-confirmation prepared actions.

### Verification

| Check | Result |
| --- | --- |
| Objective-agent context/tool/evidence scenario | Pass |
| Duplicate trigger idempotency | Pass: one run and one recommendation |

## 2026-08-12 — Canonical V2 connector ingestion

### Implemented

- Added persistent source-record lineage receipts with connection, capability,
  cursor, payload hash and canonical target identity.
- Implemented idempotent normalizers for production plans and actuals,
  downtime, inventory, supplier commitments, inspections/quality, machine
  alarms/counts and maintenance work.
- Connector sync now reports received/applied/duplicate/error reconciliation,
  mapping version and target-table counts, and automatically re-evaluates
  production, downtime, quality and material-readiness consequences.
- Added an administrator connector catalog and audited, read-only-by-default
  setup flow using secret-manager references and contract-tested capability
  selection.

### Verification

| Check | Result |
| --- | --- |
| Fresh SQLite migration | Pass: `0052_v2_integration_ingestion` |
| Complete connector conformance suite | Pass: 47 tests |
| Operational capability normalization | Pass: 7/7 canonical target scenarios |
| Sync-to-deviation reconciliation | Pass |
| Connector setup TypeScript and backend scenario | Pass |

## 2026-08-12 — Persona shell and readiness contract closure

### Implemented

- Made primary navigation role-aware for Quality, Maintenance, Procurement,
  Stores and Gate personas while preserving the broader plant-leadership view.
- Replaced the hard-coded “Live data” shell claim with connector-derived live,
  stale/degraded or unknown source state.
- Made Today, Tomorrow and 7 Days readiness horizons functional and server
  backed; added biggest risk, risky-material count, owning function and explicit
  next action to each affected material.
- Added visible stale-input suppression messaging instead of displaying false
  readiness precision.

### Verification

| Check | Result |
| --- | --- |
| Operational + connector + performance suite | Pass: 77 tests |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 42 routes |
| Production asset budget | Pass: 2.67 MB JS / 385 KB largest chunk / 256 KB CSS |
| Next.js production build | Pass: 28 routes including `/v2/home` |
| npm production audit | Pass: 0 vulnerabilities after compatible updates |

### Remaining Phase 1 work

- Add downtime, rejection-rate and material-readiness detectors.
- Complete deviation/action lifecycle commands, SLA evaluation and verified
  recovery/value transitions.
- Add Operations Overview, Line Workspace, Deviation Workspace, My Work V2,
  Gigi grounding, SSE delivery and screenshot/E2E acceptance coverage.

## 2026-08-11 — V2 Phase 1 coherent recovery loop

### Implemented

- Added deterministic downtime-threshold, rejection-rate and material-readiness
  detectors alongside the behind-plan detector.
- Added material-readiness snapshots and reproducible readiness states.
- Added explicit action commands and deviation acknowledgement, resolution and
  verification; action completion advances the linked deviation and verified
  recovery creates a separate verified Value Ledger entry.
- Added Operations Overview, Line Workspace, Deviation Workspace and My Work V2
  APIs and responsive product surfaces.
- Added loss attribution, real recovery progression, tenant/plant-scoped queries,
  SSE event delivery and TanStack Query invalidation.
- Added grounded Gigi briefing and query responses over canonical plant,
  deviation and work-order records, with confidence and evidence references.

### Verification

| Check | Result |
| --- | --- |
| Four-detector and recovery lifecycle scenarios | Pass: 3 tests |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 30 routes |
| npm audit | Pass: 0 vulnerabilities |

### Remaining programme work

- Add screenshot/E2E acceptance for all Phase 1 breakpoints and complete the
  remaining evidence/timeline APIs.
- Implement full Material Readiness persistence and Procurement V2 linkage.
- Continue through live connector UX, OT edge, Quality, Maintenance,
  Improvement, predictive/prescriptive intelligence and multi-plant phases.

## 2026-08-11 — Material Readiness and Procurement V2 linkage

### Implemented

- Added canonical work-order material requirements, inventory positions and
  supplier commitments with explicit links to V1 requirement lines, purchase
  orders and supplier acknowledgements.
- Added freshness-aware readiness recomputation using usable inventory,
  confirmed inbound and unconfirmed inbound. A recovered material position
  automatically moves the associated production-risk deviation to monitoring.
- Added material board, work-order readiness, material risk, recomputation and
  Procurement V2 lifecycle APIs.
- Added API-backed Material Readiness and Procurement V2 routes with visual
  readiness meters, production need times, risk states and the complete
  Requirement-to-Ready lifecycle.
- Kept V1 workbenches as canonical detail surfaces and linked to them rather
  than copying RFQ, comparison, PO, acknowledgement, receipt or inspection
  records.

### Verification

| Check | Result |
| --- | --- |
| Operational/material scenarios | Pass: 4 tests |
| Fresh migration to `0045_v2_operational_core` | Pass |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 33 routes |

## 2026-08-11 — Quality and Maintenance operating workspaces

### Implemented

- Added quality-containment, asset-fault and maintenance-recovery records linked
  to canonical quality events, assets, work orders and operational deviations.
- Added a value-weighted defect Pareto, first-pass-yield and rejection pulse,
  active lot containment, and direct paths into quality recovery deviations.
- Added asset consequence cards with current fault, repeat-fault count, lost
  production, spare availability and linked maintenance recovery work.
- Added tenant/plant-scoped Quality and Maintenance APIs and responsive V2
  routes without duplicating a full QMS or CMMS.
- Seeded the CNC-04 recurring fault and held quality lot so the complete
  consequence-to-recovery flow is demonstrable and testable.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 43 tests |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 36 routes |
| Diff whitespace validation | Pass |

### Remaining programme work

- Implement Improvement Studio experiments and benefits tracking.
- Add predictive/prescriptive intelligence, notification grouping, universal
  search, end-of-shift and daily briefing workflows.
- Complete OT edge adapters, onboarding/setup, multi-plant rollups, permissions,
  internationalization, accessibility and performance acceptance coverage.

## 2026-08-11 — Continuous Improvement Studio

### Implemented

- Added persistent improvement experiments with hypothesis, baseline,
  intervention, target, timebox, outcome, statistical confidence and evidence.
- Added separate benefit measurements so opportunity estimates cannot be
  presented as verified GenuineGigs-caused savings.
- Added an evidence-derived opportunity projection covering recurring asset
  faults, quality loss and material-readiness disruption, ranked by annualized
  addressable value.
- Added experiment creation authority, lifecycle outbox event, workspace API,
  seeded CNC-04 bearing experiment and responsive analytical Studio UI.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 44 tests |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 37 routes |

## 2026-08-11 — Predictive risks and daily operating briefing

### Implemented

- Added evidence-linked end-of-shift output and material-shortage risk
  projections with explicit probability, time horizon, confidence and action.
- Added grouped operational notifications by reusing the governed V1
  notification primitive instead of introducing a parallel inbox.
- Added operational command search across lines, assets, work orders, materials
  and fault codes with entity-grouped results.
- Added persistent, supervisor-verifiable shift briefings with priorities,
  metrics, losses, carry-over and evidence.
- Added the responsive `/v2/briefing` workspace combining shift priorities,
  predictive risk, grouped attention and operational search.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 45 tests |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 38 routes |

## 2026-08-11 — Operational setup, plant edge boundary and multi-plant context

### Implemented

- Added staged plant/data/use-case activation profiles with calendars, KPI
  targets, loss categories, escalation rules, value formulas and action policy.
- Added edge gateway identity, signed configuration version, canonical source
  mapping, health and idempotent ingest receipts. Edge ingress accepts only an
  allowlisted canonical event contract and rejects incorrect identity/config.
- Added a Go edge-agent source/container implementing local SQLite
  store-and-forward tables, OPC UA/MQTT mapping allowlists, outbound HTTPS and
  no inbound listener or downstream machine-write implementation.
- Added contextual multi-plant projections, systemic-loss patterns and explicit
  data-coverage context without simplistic plant ranking.
- Added responsive admin setup/edge-health and corporate operations workspaces.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 46 tests |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 40 routes |
| Edge-agent source/container contract | Present; binary build unverified because Go is unavailable in this runner |

### Explicit limitations

- Seeded edge sources are representative adapter heartbeats, not customer PLC
  connectivity. Phase 4's live-machine gate therefore remains unproven.
- Nashik is a context-only second site with deliberately absent operating data;
  it demonstrates honest multi-plant missing-data behavior, not a live rollout.

## 2026-08-11 — Named V2 API and scheduled-work contract

### Implemented

- Completed deviation assignment, timeline and evidence APIs plus action detail
  evidence capture without exposing arbitrary state mutation.
- Completed authority-scoped Value Ledger summary, deviation detail and explicit
  verification APIs while retaining calculation inputs and confidence state.
- Added expiring Gigi prepared actions for bounded deviation acknowledgement and
  action start. Execution requires explicit human confirmation and writes an
  immutable audit event; query never mutates directly.
- Added Gigi activity projection and canonical SSE activity events.
- Added the named V2 connector/outbox, line reconciliation, material readiness,
  open-deviation, action-SLA, value, shift briefing/handover and bounded-agent
  Celery tasks with one-, five- and fifteen-minute reconciliation cadences.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 49 tests |
| Focused named-contract scenarios | Pass: 13 tests |
| Required OpenAPI paths | Pass: 10/10 present with expected methods |
| Fresh SQLite migration to head | Pass: `0045_v2_operational_core` |
| Worker registry and beat cadence assertions | Pass |

## 2026-08-11 — Governed Plant Knowledge

### Implemented

- Extended the existing V1 KnowledgeDocument/Chunk primitives with document
  type, business revision, effective dates, asset/product/process scope,
  approval provenance and page/section citations.
- Preserved the existing admin draft/approve/retire workflow; approving a new
  revision retires the previous approved revision.
- Added active-approved-only retrieval with role/plant ACL, validity checks,
  structured scope and deterministic lexical ranking. Retired/draft revisions
  are visibly excluded rather than silently merged.
- Added seeded conflicting CNC-04 R1/R2 instructions and proved that retrieval
  returns approved R2/BR-28 with page and section citations while excluding R1.
- Added the responsive `/v2/knowledge` investigation and revision-guard UI.

### Verification

| Check | Result |
| --- | --- |
| Operational and connector scenarios | Pass: 50 tests |
| Focused V2 scenarios | Pass: 14 tests |
| Fresh/partially-applied migration recovery | Pass: `0046_v2_knowledge_metadata` |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 41 routes |

## 2026-08-11 — V2 completion hardening and final local gates

### Implemented

- Added governed SPC quality detection and NCR/CAPA recovery, multi-plant KPI
  definitions and practice transfers, plant locale/timezone/currency contracts,
  role-scoped financial redaction, guided setup mutations, and durable shift
  handover governance.
- Hardened the edge agent with separately provisioned Ed25519 verification,
  durable replay identity and checked-in outage/restart/exactly-once tests.
- Completed the exact required V2 HTTP contract, including named action
  transitions and line timeline/loss-tree projections; no arbitrary action
  state route is exposed.
- Added skip navigation, labelled mobile navigation, keyboard focus/touch
  treatment, reduced-motion handling and contextual keyboard-operable Gigi.
- Added completion, performance, accessibility, API-process and deployment-gate
  evidence without representing customer/live gates as locally complete.

### Verification

| Check | Result |
| --- | --- |
| Operational, connector and performance scenarios | Pass: 58 tests |
| Fresh SQLite migration to head | Pass: `0049_v2_plant_locale` |
| Required V2 OpenAPI contract | Pass; explicit named routes |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 41 routes |
| Production asset budget | Pass: 2.00 MB JS / 352 KB largest chunk / 228 KB CSS |
| Browser acceptance | Checked in; host Chromium libraries unavailable |
| Go edge tests | Checked in; Go toolchain unavailable in this runner |

## 2026-08-12 — V2 product-depth implementation

### Implemented

- Made V2 the default product landing while preserving V1 procurement as a
  linked canonical module.
- Added global operational search and grouped attention drawers with SSE cache
  invalidation throughout the V2 shell.
- Replaced thin line progress decoration with persisted multi-point
  plan/actual/forecast trajectories and interactive shift-event investigation.
- Added canonical cross-functional recovery dependencies, a causal-action
  projection that separates facts/hypotheses/confirmed causes, and corresponding
  premium deviation-workspace visualization.
- Added server-calculated production, quality, reliability, material, execution
  and value KPI groups plus the current-shift operating strip.
- Added versioned integration-mapping editing, source reconciliation receipts,
  maintenance asset drill-down, quality deviation detail and the governed V2
  administration hub required by the UI route contract.
- Added event-driven, role-aware proactive Gigi coordination and transparent
  rolling forecast evaluation against the simple line-rate baseline.

### Verification

| Check | Result |
| --- | --- |
| Fresh SQLite migration | Pass: `0050_v2_action_dependencies` |
| Focused operational/KPI/forecast tests | Pass: 25 tests |
| Operational + connector + performance suite | Pass: 60 tests |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 42 routes |
| Production asset budget | Pass: 2.66 MB JS / 385 KB largest chunk / 246 KB CSS |

## 2026-08-12 — Governed detection and operational connector alignment

### Implemented

- Persisted the four Phase 1 detector policies as versioned plant configuration,
  including thresholds, severity bands and owning roles; configuration changes
  are audited and emitted through the transactional outbox.
- Made the Command Center role-aware while retaining the canonical plant pulse,
  so production, quality, maintenance, stores and procurement users receive a
  sourced focus question and relevant operational highlights.
- Extended the connector capability contract for production plans/actuals,
  downtime, inventory, commitments, quality, machine events and maintenance.
- Added capability-derived dataset selection to the integrations workspace and
  matching server-side rejection for disabled, unknown or unauthorized syncs.
- Added connector conformance coverage proving that every V2 sync dataset is
  declared by the reference adapters and that the seeded connection is valid.

### Verification

| Check | Result |
| --- | --- |
| Connector conformance suite | Pass: 38 tests |
| TypeScript typecheck | Pass |
| Fresh SQLite migration | Pass: `0051_v2_detector_rules` |

## 2026-08-12 — Maintenance recovery and accountable material flow

### Implemented

- Converted Maintenance from a read-only consequence view into a governed
  recovery lifecycle with named start, blocker and completion commands.
- Maintenance completion clears the linked fault and active downtime window,
  advances the operational deviation into monitoring, and emits immutable
  audit and transactional-outbox evidence.
- Added operational work notes and explicit recovery controls to the responsive
  asset workspace while retaining the external CMMS as the canonical boundary.
- Replaced hard-coded procurement attention totals with lifecycle-derived
  current stage, responsible party, elapsed wait, dependency and next action.
- Added dependency context to My Work so upstream delays are visibly attributed
  to the blocking function instead of being presented as employee failure.

### Verification

| Check | Result |
| --- | --- |
| Maintenance recovery lifecycle | Pass: fault/downtime closure, monitoring, audit and outbox |
| V1-linked procurement/readiness scenario | Pass |
| TypeScript typecheck | Pass |

## 2026-08-12 — Integration ingestion, agent runtime and release audit

### Implemented

- Added canonical normalization and lineage receipts for production plan and
  actuals, downtime, inventory, supplier commitments, quality, machine events
  and maintenance-work ingestion, with cursor/hash idempotency and downstream
  deviation/readiness recalculation.
- Added the objective-agent runtime with canonical context snapshots, durable
  tool-call evidence, structured recommendations, idempotent event consumption
  and transactional-outbox coordination.
- Added the administrator connector catalog and governed read-only connection
  setup, plus capability-derived freshness and readiness projections in the UI.
- Fixed fresh-workspace ERP onboarding so the first authoritative plant hydrates
  the placeholder plant rather than separating imported roles from active scope.
- Repaired V1 quotation extraction compatibility, negotiation version capture,
  missing default connector creation and invalid RFQ-reference recovery found by
  the strict legacy-plus-V2 audit.
- Corrected the action-dependency migration to include the scoped public and
  business identifiers required by the mapped domain model.

### Verification

| Check | Result |
| --- | --- |
| Connector conformance suite | Pass: 47 tests |
| Operational, connector and performance suite | Pass: 77 tests |
| Remaining procurement, policy, quality, supplier and retention regression slice | Pass: 52 tests |
| Golden Excel-to-payment procurement lifecycle | Pass |
| Fresh SQLite migration | Pass: all 52 migrations; E2E server seeded successfully |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 42 routes and asset budget |
| Browser acceptance | Blocked by runner host library `libnspr4.so`; application servers pass startup |
| Legacy synchronous HTTP tests | Superseded below: runner cause identified and complete suite executed successfully |

### Full compatibility closure

- Declared Starlette's `httpx2` test transport and proved the earlier HTTP
  stall was caused by the managed sandbox blocking AnyIO's thread portal, not
  by the application server.
- Extended the stable V1 presentation contract to safely represent V2 roles,
  workflow states and operational priority bands in shared work queues.
- Preserved canonical material identity and provider-normalized facts through
  multi-turn delegation, with one read-only post-mutation synthesis turn and
  immutable action-receipt evidence.
- Removed duplicate Gigi creation-event projections that could obscure a later
  human-confirmed execution state.

| Check | Result |
| --- | --- |
| Complete API suite, no exclusions | Pass: 421 tests |
| HTTP/TestClient role, CSRF, idempotency and V2 API contracts | Pass inside complete suite |

## 2026-08-12 — Frontend state-contract closure

- Added explicit operational loading, empty and recoverable error treatments to
  Knowledge, Integrations and Corporate Operations instead of allowing blank
  panels or silent failures.
- Knowledge failures now prevent superseded instructions being mistaken for
  current truth; integration failures explicitly degrade forecast/readiness;
  corporate comparison is suppressed when plant context cannot be reconciled.
- Preserved the professional, dense industrial visual language and existing
  responsive component system without introducing decorative dashboard filler.

| Check | Result |
| --- | --- |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 42 routes |
| V2 production asset budget | Pass: 2.67 MB JS / 385 KB largest chunk / 256 KB CSS |

## 2026-08-12 — Responsive browser acceptance and cycle-race closure

- Executed the V2 operating-system acceptance suite in the official Playwright
  container at desktop, tablet and mobile breakpoints. The suite covers all
  flagship workspaces, critical axe violations, mobile overflow, governed shift
  handover and administrator-only infrastructure boundaries.
- Hardened lazy procurement-cycle synchronization after concurrent browser reads
  exposed uniqueness races. Evaluation and commit now share one process-local
  critical section, while database uniqueness constraints remain authoritative.
- Corrected the mobile My Work assertion to use the UI plan's exact H1,
  “What should I do now?”, rather than requiring the navigation label in the H1.

| Check | Result |
| --- | --- |
| Desktop V2 browser acceptance | Pass: 3 tests, 1 mobile-only skip |
| Tablet V2 browser acceptance | Pass: 3 tests, 1 mobile-only skip |
| Mobile V2 browser acceptance | Pass: 4 tests |
| Focused post-race HTTP regression | Pass: 22 tests |

## 2026-08-12 — Strict plan audit: screen states and edge reproducibility

- Re-audited the implementation against the hard backend/UI execution contracts
  after the broad suite passed; passing routes alone were not treated as proof of
  each screen's state contract.
- Added explicit loading, empty, failure and retry treatments to My Work,
  Procurement V2, Operations and operational setup. Failure copy avoids
  presenting missing source data as healthy or empty operation.
- Made Gigi visibly refuse to invent an answer when grounded context is
  unavailable and exposed recoverable query/action errors in its side panel.
- Built the Phase 4 edge agent in the official Go 1.23 container. This exposed
  the missing module checksum lock; generated `go.sum`, then proved signed-config
  tamper rejection and durable outage → restart → replay-once behavior.

| Check | Result |
| --- | --- |
| TypeScript typecheck after state-contract changes | Pass |
| Edge agent Go 1.23 build/tests | Pass |

## 2026-08-12 — Hard-contract and final regression closure

- Added an executable hard-plan contract covering all 43 required V2 API
  method/path pairs, the prohibition on generic Action/Deviation PATCH routes,
  and every canonical worker identity.
- Added canonical `recompute_material_readiness`, `index_knowledge_document`
  and `run_agent` tasks while retaining rollout aliases for already-enqueued
  task names. Knowledge indexing now rebuilds derived chunks idempotently.
- Replaced the nominal Value Ledger worker count with deterministic estimated
  impact reconciliation. Human-verified recovery is never rewritten.
- Made the Command Center Units/Time/Value loss selector and Operations status
  filters functional over API-backed measures instead of decorative controls.
- Wired My Work and Deviation “Ask Gigi” controls into the governed shell panel
  with contextual, prefilled questions and visible mutation/query failures.
- Added reusable status/severity/entity/evidence and degraded/empty operational
  primitives, and completed missing state handling in briefing, search, alerts,
  administration, setup, procurement and work surfaces.
- Made SSE disconnect cleanup idempotent when a test/deployment connection has
  already been disposed; final browser runs contain no generator teardown error.
- Added `V2_REQUIREMENTS_TRACEABILITY.md` to map the hard implementation and UI
  contracts to direct code/test evidence and keep external gates explicit.

| Check | Result |
| --- | --- |
| Complete API suite, no exclusions | Pass: 425 tests |
| Hard V2 API/worker contract | Pass |
| Fresh Alembic upgrade | Pass: 0001 → 0052 in a new SQLite database |
| Edge agent Go 1.23 suite | Pass |
| TypeScript typecheck | Pass |
| Next.js production build | Pass: 42 routes |
| V2 production asset budget | Pass: 2.67 MB JS / 385 KB largest JS / 256 KB CSS |
| Desktop V2 acceptance | Pass: 3 applicable tests |
| Tablet V2 acceptance | Pass: 3 applicable tests |
| Mobile V2 acceptance | Pass: 4 tests, including contextual Gigi and overflow |
