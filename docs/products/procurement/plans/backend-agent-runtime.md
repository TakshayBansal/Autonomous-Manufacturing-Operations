# GenuineGigs Backend and Agent Runtime Upgrade — Codex Execution Contract

> **Purpose:** Turn the existing procurement backend into a reliable, role-aware agentic operating layer without replacing the working procurement domain.
>
> **Repository:** `C:\Users\Takshay\Desktop\Important\GenuineGigs`
>
> **Read first:** latest `HANDOFF.md`, then this file.
>
> **Execution order:** Complete phases in order. Commit is not required. Do not begin frontend redesign while executing this plan.
>
> **Primary outcome:** Every demo workspace is usable by all configured plant roles, and each role assistant can understand ordinary requests, use uploaded documents, execute canonical procurement services, return persisted results, create visible tasks/notifications, and coordinate governed handoffs.

---

## 0. Product behavior required after this plan

The backend must support this experience without phrase-specific hardcoding:

1. A Plant Manager creates a new demo workspace.
2. The same workspace appears for the standard Purchase Manager, Purchase Executive, Gate Operator, Store Manager, Quality Inspector, and Admin demo accounts.
3. Each account enters the same tenant and plant with its own role, permissions, reporting line, tasks, notifications, and assistant profile.
4. A user speaks naturally to their assistant. The assistant identifies the requested business outcome, resolves records and attachments, asks only for genuinely missing information, and invokes canonical services.
5. The assistant never claims success from generated prose. It returns the persisted entity ID, status, owner, artifact, and next action from a service result or action receipt.
6. A Purchase Manager can upload supplier quotations to the assistant, ask for a comparison, verify uncertain fields, generate the same canonical comparison that the manual workbench generates, and submit the frozen version for upstream approval.
7. Managers can delegate work, request updates, see overdue tasks, and receive structured upward summaries. Agent-to-agent coordination occurs through governed tasks and handoffs, not unrestricted hidden conversations.
8. Manual screens continue to work when Groq is unavailable. Supported common actions use deterministic server workflows after the user intent and entities are resolved.

---

# 1. Non-negotiable implementation rules

1. **Patch the existing repository. Do not rewrite it.**
2. Preserve FastAPI, SQLAlchemy, LangGraph, PostgreSQL, Redis, Celery, MinIO, existing authentication, generated OpenAPI contracts, and current test conventions.
3. `PurchaseRequirement` remains the only active demand object.
4. Manual and assistant actions must call the same canonical requirement, RFQ, quotation, comparison, approval, PO, inbound, task, and document services.
5. Do not restore Objective creation or create any agent-only procurement record.
6. Do not introduce CrewAI, AutoGen, another orchestration framework, a new database, or a second agent runtime.
7. Do not implement a large list of exact prompt-to-action regular expressions. Natural-language understanding must be model-assisted and schema-constrained; deterministic code validates and executes business actions.
8. Do not let the LLM select arbitrary Python functions or route names. It may select only a capability ID from the server-provided role capability registry.
9. Do not let model output broaden tenant, plant, role, reporting, document, or entity scope.
10. Never state that an action completed unless the canonical service returned a persisted result and an `AgentActionReceipt` was created or reused idempotently.
11. Never reply with “I will provide it shortly,” “I am checking,” or equivalent unless a real background job exists and the response includes the job identifier and current status.
12. Preserve explicit human confirmation for RFQ publication, comparison submission/approval, PO confirmation, supplier email dispatch, ERP posting, quality disposition, and other controlled actions.
13. Do not expose prompts, chain-of-thought, graph nodes, checkpoints, raw tool calls, or provider payloads to users.
14. Do not hand-edit `packages/shared/src/api.generated.ts`. Regenerate after stable API changes.
15. Do not upgrade dependencies unless an existing dependency cannot implement a required behavior.
16. Do not reformat or rename unrelated modules.
17. Preserve the dirty worktree and never use destructive Git commands.
18. Add tests before changing behavior for each regression addressed below.
19. If a named symbol has moved, locate its equivalent with `rg` and patch the smallest relevant area.
20. Finish all verification commands before reporting success.

---

# 2. Fixed architecture — do not redesign

## 2.1 Role assistant model

Use the existing `AgentProfile`, `AgentThread`, `AgentMessage`, `AgentRun`, `AgentEvent`, `AgentCheckpoint`, `AgentProposal`, `AgentActionReceipt`, `AgentDelegation`, `AgentMemory`, `Task`, and `Notification` models.

Each active `WorkspaceMembership` may have one role assistant profile. The assistant receives authority from the membership, never from model output.

The runtime consists of these fixed server stages:

```text
request received
-> resolve authenticated membership and current page/work-item context
-> load compact conversation state and recent persisted entity references
-> build allowed role capability registry
-> LLM produces structured IntentEnvelope
-> server validates intent, entities, scope, and required fields
-> ask one concise clarification OR build controlled proposal OR execute canonical service
-> persist receipt, entity references, task/notification effects
-> generate user response from persisted results
```

Do not add autonomous recursive planning. Maximum one business capability execution per user turn, except tightly coupled read/resolve operations required before that execution.

## 2.2 LLM responsibility

Use Groq for:

- natural-language intent classification;
- extracting business fields from conversation;
- resolving references such as “this RFQ,” “the ingot requirement,” or “the quotes I uploaded” using server-provided candidates;
- summarizing persisted data;
- explaining tasks, comparisons, risks, and missing information;
- drafting text such as RFQ notes or supplier follow-up messages.

Do **not** use Groq for:

- authorization;
- tenant/plant scoping;
- inventing entity IDs;
- calculating final landed cost when deterministic code exists;
- deciding whether a controlled action can bypass confirmation;
- directly writing database records;
- selecting unrestricted functions;
- determining whether a service succeeded.

## 2.3 Weak model/tool-selection mitigation

Do not rely on the model to emit raw tool calls. Implement a two-step constrained decision:

### Step A — `IntentEnvelope`

Add or reuse a Pydantic schema with this exact conceptual shape:

```python
class IntentEnvelope(BaseModel):
    intent: str
    requested_outcome: str
    entities: dict[str, Any]
    referenced_entity_ids: list[str]
    attachment_ids: list[str]
    missing_fields: list[str]
    confidence: float
    is_topic_change: bool
    requires_confirmation: bool
```

`intent` must be one capability ID from the server-provided allowed list. Reject unknown IDs.

### Step B — server capability handler

The server maps the validated capability ID to one existing service adapter. It resolves and validates records before invocation. The model never sees or chooses route/function names.

This is not phrase hardcoding. The model interprets natural language; deterministic code constrains authority and execution.

## 2.4 Capability registry

Create or consolidate one server-side registry. Each entry includes:

```text
capability_id
allowed roles/capabilities
required fields
optional fields
controlled-action flag
attachment types
canonical service adapter
response-card type
```

Required capability IDs for this release:

```text
answer_work_context
list_my_tasks
list_team_tasks
get_record
search_approved_material
create_material_master_request
create_purchase_requirement
prepare_rfq_draft
publish_rfq_proposal
upload_supplier_quotes
review_quote_extraction
prepare_supplier_comparison
submit_comparison_proposal
record_comparison_decision_proposal
confirm_purchase_order_proposal
prepare_supplier_followup
request_task_update
delegate_task
summarize_procurement_risks
summarize_team_status
```

Do not expose capabilities that the current membership cannot perform.

---

# 3. Demo workspace access for all roles

## 3.1 Required behavior

Creating a workspace in development/demo mode must create or reconcile access for all standard demo role accounts in the **same** tenant and plant.

Standard accounts:

```text
plant.manager@genuinegigs.local
purchase.manager@genuinegigs.local
purchase.exec@genuinegigs.local
gate.operator@genuinegigs.local
store.manager@genuinegigs.local
quality.inspector@genuinegigs.local
admin@genuinegigs.local
```

All use the existing development password configuration.

After workspace creation:

- each account has one `WorkspaceMembership` in the new workspace;
- each membership has the expected role and plant access;
- Purchase Executive reports to Purchase Manager;
- Purchase Manager, Gate, Store, Quality, and Admin report to Plant Manager unless the current model requires another valid line;
- an `AgentProfile` exists or is idempotently enabled for every role membership when workspace agents are enabled;
- the workspace appears in login membership selection for every account;
- no sample transactional procurement data is copied;
- master data is only created when the existing development bootstrap explicitly does so;
- repeated bootstrap calls do not create duplicate memberships, reporting lines, users, profiles, or plant access.

## 3.2 Production safety

Automatic demo-seat creation must run only when the existing development/demo bootstrap flag is enabled. In production:

- workspace creation adds only the creator;
- other employees join through invitations or admin membership creation;
- no known demo password or demo account behavior is enabled.

## 3.3 APIs

Reuse existing workspace setup endpoints where possible. Add only missing additive fields/endpoints:

```text
GET /workspaces/{workspace_id}/demo-access
POST /workspaces/{workspace_id}/demo-access/reconcile
```

These endpoints must be owner/Admin-only and disabled outside demo mode.

The read response returns role, display name, masked email or full demo email, membership readiness, and workspace selection availability. Do not return passwords from the API. The frontend may display the documented development password only when the server explicitly returns `demo_mode=true`.

## 3.4 Tests

Add tests proving:

- a newly created demo workspace is selectable by every standard role account;
- each role is scoped to the same tenant/plant;
- permissions differ correctly by role;
- reporting lines are correct;
- bootstrap is idempotent;
- production mode does not add demo memberships;
- one role cannot read another role’s private agent thread;
- Plant Manager can view formal descendant task status but not private transcripts.

---

# 4. Conversation state and continuity repair

## 4.1 Compact state contract

Store compact business state in `AgentThread.context_state`. Use this shape or migrate existing equivalent fields without creating another table:

```json
{
  "active_intent": "create_purchase_requirement",
  "draft_fields": {
    "material_query": "Aluminium ingot",
    "item_id": "...",
    "quantity": 100,
    "uom": "KG",
    "need_by": "2026-08-16",
    "reason": "raw material",
    "assignee_membership_id": "..."
  },
  "field_provenance": {
    "quantity": {"message_id": "...", "source": "user"}
  },
  "recent_entities": [
    {"type": "purchase_requirement", "id": "...", "display_id": "PR-2026-0042"}
  ],
  "last_action_receipt_id": "...",
  "current_work_item": {"type": "purchase_requirement", "id": "..."},
  "updated_at": "..."
}
```

Keep only a bounded number of recent references.

## 4.2 Topic changes

Use the structured `is_topic_change` signal plus entity comparison. When the user changes from Copper Ingot to Aluminium Ingot:

- clear fields that belong to the old material/entity;
- retain globally valid fields only when clearly repeated or still applicable, such as quantity and reason if the new request includes them;
- clear the old material-master validation error;
- resolve the new material from the approved master;
- never force the user to explicitly cancel an abandoned draft.

Do not implement a phrase list such as “leave this” or “forget that” as the primary solution. Such phrases may be supporting signals only.

## 4.3 Recent entity references

After every successful mutation or important read, persist a compact recent entity reference. Follow-ups such as:

- “What is its ID?”
- “Open that requirement.”
- “Prepare the RFQ for it.”
- “Send this upstream.”

must resolve from `current_work_item`, `recent_entities`, and the last receipt before asking the model to guess.

## 4.4 Date and quantity normalization

Use existing parsing libraries or standard Python utilities. Support ordinary expressions including:

- `100KG`, `100 kg`, `100 kilograms`;
- `in one month`, `a month from now`, `next Friday`, `end of this month`;
- common date formats used in India.

The server must return the exact normalized date in the confirmation/created card. Relative dates are resolved using the workspace/user timezone.

## 4.5 Material resolution

Resolve approved materials in this order:

1. exact item code;
2. case-insensitive exact normalized name;
3. token-normalized name/description;
4. safe close matches from approved items in the same tenant/plant.

The model may rank server-provided candidates but cannot invent a material. Behavior:

- one high-confidence match: select it;
- several plausible matches: show at most five choices;
- no approved match: offer to create a material-master request in the same conversation;
- never repeat a stale “not in approved master” error after the material changes.

---

# 5. Requirement assistant workflow

## 5.1 Required fields

Use the current canonical requirement service and existing domain rules. The assistant collects:

```text
approved item
positive quantity
UOM
need-by date
reason/purpose
named Purchase Executive assignee when not uniquely derivable
optional specification
inspection requirement
```

Do not ask for item code when a unique approved name match exists. Do not ask the user for fields already present in the selected item or current workspace context.

## 5.2 Execution behavior

When all required fields resolve and the role is authorized:

1. show a compact confirmation only if the current service/policy requires confirmation;
2. call the same canonical creation service as the manual form;
3. create/reuse the named Purchase Executive task and audit records;
4. create an `AgentActionReceipt` containing entity type, database ID, display ID, status, owner, and correlation ID;
5. update thread recent entities/current work item;
6. return the exact created requirement ID in the same response;
7. expose next actions such as `Open requirement` and `Prepare RFQ` according to role.

A valid response is:

```text
Created requirement PR-2026-0042.
Aluminium Ingot · 100 KG · Need by 16 Aug 2026
Assigned to Meera Iyer. Status: Approved.
```

## 5.3 Failure behavior

- validation error: explain the exact field and retain valid fields;
- duplicate/idempotent replay: return the original requirement and receipt;
- material missing: offer material-master request;
- no Purchase Executive: explain workspace setup problem and link the setup action;
- provider outage after intent is obvious from context/UI: use deterministic capability workflow;
- service failure: never claim creation; include correlation ID and safe retry action.

## 5.4 Regression tests

Cover the user’s reported flow and variations without hardcoding one sentence:

1. create Copper request, missing need-by date;
2. provide item code and relative date;
3. switch to Aluminium and confirm approved-master match;
4. create requirement;
5. ask for “its ID,” “the ingot requirement ID,” and a misspelled follow-up;
6. confirm all answers return the persisted ID;
7. confirm no “shortly” or stale material error appears;
8. repeat with reordered wording and different capitalization.

---

# 6. Supplier quotation and comparison assistant workflow

This is the flagship agent capability and must use the canonical quotation/comparison records.

## 6.1 User experience supported by the backend

A Purchase Manager can:

1. select or mention an RFQ;
2. attach multiple PDF/PNG/JPG/XLSX quotation files in the assistant;
3. optionally identify suppliers when filenames/content do not resolve uniquely;
4. say naturally: “Compare these quotations and prepare the supplier comparison.”

The assistant then:

- stores documents privately using existing upload validation;
- associates each document with the selected RFQ and supplier;
- launches/reuses extraction jobs;
- returns extraction progress through existing run/events or job status;
- presents uncertain/missing fields for human verification;
- prevents unverified quotations from entering the comparison;
- invokes the canonical comparison generator after all eligible quotations are verified;
- returns the comparison ID/version, recommendation, principal risks, and artifact preview;
- exposes `Review comparison` and `Submit for approval` actions;
- never submits/finalizes automatically without the existing confirmation.

## 6.2 Attachment context

Extend existing assistant message APIs to accept existing `Document` IDs or upload references. Do not store file bytes in agent messages.

Each attachment must retain:

```text
document_id
filename
MIME/type
validation status
linked RFQ/supplier when resolved
extraction job/status
```

Assistant context includes only metadata and extracted fields/evidence, not unrestricted raw bytes.

## 6.3 Supplier/RFQ resolution

Resolution order:

- selected page/work-item context;
- explicit RFQ ID or supplier name/code;
- recent entities;
- allowed server candidates;
- one concise clarification when ambiguous.

Never invent a supplier. Only approved/capable suppliers valid for the RFQ may be used according to existing rules.

## 6.4 Comparison response

Return business content, not runtime language:

```text
Comparison BC-2026-0018 is ready for review.
Recommended: Bharat Metals
Lowest landed total: ₹18.4 lakh
Risks: payment terms differ; one delivery commitment is tight.
3 quotations verified · Version 1
```

Include persisted comparison ID/version and artifact/document references.

## 6.5 Tests

Add API/integration tests for:

- multiple assistant attachments;
- RFQ resolution from context and explicit ID;
- ambiguous supplier mapping;
- extraction requiring verification;
- verified-only comparison generation;
- same comparison produced by manual and assistant paths;
- idempotent repeated command;
- controlled submit proposal;
- provider outage after documents and RFQ are selected;
- tenant/document isolation.

---

# 7. Hierarchical tasks, follow-ups, and notifications

## 7.1 Structured hierarchy only

Agents coordinate through `Task`, `AgentDelegation`, `Notification`, proposals, receipts, and linked records. Do not implement hidden free-form conversations between agents.

A manager request such as:

> Ask Meera to collect updated quotations from approved suppliers by tomorrow afternoon.

must create a governed task with:

```text
requested outcome
assignee membership
creator/delegator
priority
due date
linked RFQ/requirement/suppliers
expected output
follow-up policy
source thread/run
```

The assignee’s assistant receives the task in its context. Completion or blocking creates an upward notification and a compact manager summary.

## 7.2 Follow-up engine

Use Celery/beat or the existing scheduler. Implement bounded follow-up policies:

- due soon;
- overdue;
- waiting for supplier;
- approval pending;
- blocked task;
- extraction/verification waiting;
- PO acknowledgement waiting.

Do not send external messages automatically unless the existing external-email confirmation policy allows it. Internal notifications may be automatic.

## 7.3 Notification categories

Use or extend existing `Notification` data. Required categories:

```text
action_required
approval_required
task_assigned
task_due_soon
task_overdue
task_blocked
team_update
assistant_prepared
supplier_response
extraction_review
quality_exception
system_warning
```

Each notification includes membership scope, linked record/task, severity, read state, created time, and a safe navigation target.

## 7.4 Badge counts API

Provide one compact endpoint, preferably by extending existing My Work/home API:

```text
GET /workspace/home
```

Response sections:

```json
{
  "badge_counts": {
    "my_work": 4,
    "approvals": 1,
    "quotations": 2,
    "inbound": 0,
    "notifications": 5
  },
  "attention_items": [],
  "assistant_prepared": [],
  "my_tasks": [],
  "waiting_on_others": [],
  "team_followups": [],
  "recent_notifications": []
}
```

Counts must be role-scoped and derived from canonical records. Do not expose `outbox` or runtime counts as primary business badges.

## 7.5 Tests

Test:

- assignment notification;
- due/overdue transitions;
- manager follow-up authorization;
- descendant-only delegation;
- completion summary upward notification;
- unread/read badge changes;
- cross-workspace isolation;
- exact home counts for each demo role.

---

# 8. Assistant response contract

## 8.1 User-facing response blocks

Keep typed blocks but map them to business concepts:

```text
message
clarification
record_created
record_summary
action_required
approval_request
prepared_artifact
missing_information
warning
task_update
team_summary
```

Do not show labels such as tool call, checkpoint, run, receipt, role queue, or outbox to normal users.

## 8.2 Grounded response generation

The final response generator receives:

- persisted service result;
- receipt;
- safe record summary;
- allowed next actions;
- warnings/missing fields;
- attachment/extraction status.

It must not receive authority to alter the result. Add a final server validator that rejects or replaces responses when:

- a mutation claim has no receipt/entity;
- a displayed ID differs from the persisted result;
- future-tense retrieval is used without a job;
- unauthorized next actions are shown.

## 8.3 Concise conversational style

Remove repeated boilerplate headings such as “Answer,” “Role ownership,” “Not delegated yet,” and “Still needed.”

Ask at most one grouped clarification per turn:

> “I found two approved Aluminium Ingot items. Choose ALI-101 or ALI-204; everything else is ready.”

When several fields are missing, present one compact list or structured form card rather than repeated turns.

---

# 9. APIs required by the frontend plan

Prefer extending existing endpoints. Add only if missing:

```text
GET  /workspace/home
GET  /notifications
POST /notifications/{id}/read
POST /notifications/read-all
GET  /workspaces/{id}/demo-access
POST /workspaces/{id}/demo-access/reconcile
POST /agent/threads/{id}/messages          # supports attachment document IDs
GET  /agent/threads/{id}/context-summary
POST /agent/proposals/{id}/confirm
POST /agent/proposals/{id}/reject
POST /tasks/{id}/request-update
```

The assistant message response should include:

```json
{
  "message": {},
  "blocks": [],
  "current_work_item": {},
  "allowed_actions": [],
  "created_or_updated_records": [],
  "job_status": null,
  "badge_counts": {}
}
```

Unsafe mutations require current CSRF and idempotency behavior.

---

# 10. File-level implementation map

Inspect and patch these existing areas first:

```text
apps/api/app/agent_service.py
apps/api/app/agent_schemas.py
apps/api/app/routers/agents.py
apps/api/app/task_service.py
apps/api/app/domains/workflows.py
apps/api/app/procurement_v2.py
apps/api/app/documents.py
apps/api/app/main.py
apps/api/app/db/models.py
apps/api/app/db/seed.py
apps/api/app/models.py
apps/api/app/api_schemas.py
apps/api/app/core/permissions.py
apps/api/app/workers.py
apps/api/app/celery_app.py
```

Create at most these small focused modules when existing files would become materially harder to maintain:

```text
apps/api/app/agent_capabilities.py
apps/api/app/agent_context.py
apps/api/app/agent_response.py
```

Do not create another service layer for procurement. Capability adapters call existing services.

Database changes:

- prefer existing JSON/context fields and `Notification`/`Task` models;
- add one Alembic migration only if required fields/indexes genuinely do not exist;
- use the next migration number;
- make migration forward-only, tenant-safe, and SQLite-test-compatible where current migrations require it.

---

# 11. Phased execution

## Phase B0 — Baseline and failing regression tests

1. Run Git/Docker status and existing tests.
2. Add tests reproducing stale material state, false creation claim, missing ID follow-up, and inaccessible new workspace roles.
3. Add a test fixture for assistant quotation attachments and comparison preparation.
4. Confirm the new tests fail for the intended reasons.

**Gate:** Existing baseline remains understood; new regressions fail before fixes.

## Phase B1 — Demo workspace accessibility

1. Repair development workspace bootstrap.
2. Reconcile all demo role memberships, plant access, reporting lines, and profiles.
3. Make workspace selection available to each account.
4. Add demo-access read/reconcile APIs if missing.
5. Pass workspace and isolation tests.

**Gate:** The same newly created workspace is usable through every demo role account.

## Phase B2 — Runtime decision and conversation state

1. Implement/consolidate capability registry.
2. Implement structured `IntentEnvelope` validation.
3. Repair topic changes, recent entities, field provenance, dates, quantities, and material resolution.
4. Add grounded final-response validation.
5. Remove unsupported future promises and stale boilerplate from API response blocks.

**Gate:** Reported requirement conversation and variants pass.

## Phase B3 — Canonical procurement capabilities

1. Complete requirement creation and follow-up retrieval.
2. Implement assistant attachment linkage.
3. Complete quotation upload/extraction/verification orchestration.
4. Complete canonical comparison preparation and controlled submit proposal.
5. Preserve manual equivalence and idempotency.

**Gate:** Assistant and manual paths produce the same persisted business records.

## Phase B4 — Tasks, hierarchy, follow-ups, and notifications

1. Complete governed delegation and request-update behavior.
2. Implement scheduled internal follow-ups.
3. Add role-scoped notification categories and home/badge aggregation.
4. Add upward summaries and waiting-on-others data.

**Gate:** Each role has correct tasks, badges, and notifications; managers see formal descendant status only.

## Phase B5 — Full verification and demo seed

1. Ensure demo master contains clearly named approved Copper Ingot and Aluminium Ingot items with unique item codes, or update the deterministic demo fixture without modifying fresh customer workspaces.
2. Seed at least three supplier quotations suitable for comparison demo, including one uncertain field requiring verification.
3. Run all tests and the exact demo script.
4. Regenerate/check OpenAPI contract only after APIs stabilize.

**Gate:** All commands below pass and the demo script returns persisted IDs/artifacts.

---

# 12. Required verification

Run the repository-equivalent commands:

```powershell
git diff --check
docker compose up --build -d
docker compose ps -a
cd apps/api
python -m pytest -q
cd ../..
npm run generate:api
npm run check:api-contract
npm run typecheck
npm run build:web
npm run test:e2e
```

Also run targeted tests for:

```text
demo workspace role access
membership and private-thread isolation
requirement conversation continuity
recent entity ID retrieval
provider failure fallback
assistant quote attachments
verified-only comparison generation
manual/assistant record equivalence
notification badge counts
delegation/follow-up hierarchy
```

Do not report a test as passing unless it was run.

---

# 13. Backend acceptance demo

Execute through real APIs/services, not mocked prose:

### Demo A — workspace roles

1. Plant Manager creates `Client Demo Plant`.
2. Sign out.
3. Sign in as Purchase Manager and select `Client Demo Plant`.
4. Repeat for Purchase Executive, Gate, Store, Quality, and Admin.
5. Confirm role-specific navigation/home data and tenant isolation.

### Demo B — requirement conversation

```text
User: Create a raw-material requirement for 100 kg of Aluminium Ingot, needed one month from today.
Assistant: [asks only if item/assignee is genuinely ambiguous, otherwise creates]
Assistant: Created requirement PR-... [exact persisted ID and details]
User: What is its ID?
Assistant: PR-... [same exact ID]
User: Prepare the RFQ for it.
Assistant: [canonical RFQ draft result or controlled action]
```

Repeat with spelling variation and a topic switch from Copper to Aluminium.

### Demo C — quotation comparison

1. Sign in as Purchase Manager.
2. Select an RFQ.
3. Upload three quotation files in the assistant.
4. Ask: “Compare these quotations and prepare the supplier comparison.”
5. Verify one uncertain field in the returned review UI/API.
6. Generate canonical comparison.
7. Confirm persisted comparison ID/version, recommendation, risks, and PDF artifact.
8. Submit through controlled proposal.
9. Confirm Plant Manager and Purchase Executive receive approval notifications.

### Demo D — provider failure

Disable/unavailable Groq after the RFQ and attachments are resolved. Confirm manual screens remain functional and supported deterministic continuation does not fabricate results.

---

# 14. Completion report format

Codex must finish with exactly these sections:

```text
Implemented
- ...

Files changed
- ...

Migrations and API contract
- ...

Tests run
- command: result

Demo scenarios
- Workspace roles: PASS/FAIL
- Requirement and ID follow-up: PASS/FAIL
- Quote upload and comparison: PASS/FAIL
- Hierarchical tasks/notifications: PASS/FAIL
- Provider failure/manual fallback: PASS/FAIL

Remaining blockers
- None
```

If any gate fails, state the exact blocker and do not call the release complete.
