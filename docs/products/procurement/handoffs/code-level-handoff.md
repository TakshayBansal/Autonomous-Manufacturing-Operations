# GenuineGigs Procurement UX and Agent Runtime — Code-Level Handoff

## 0. Purpose and status

This document is the source-of-truth engineering dossier for GenuineGigs. It was originally written around two connected failures and has been expanded into a repository-level handoff for planning future product, architecture, UX, security, integration, and agent improvements.

The original two failures were:

1. The manual procurement experience exposes backend lifecycle operations as unrelated buttons. A user sees **Generate RFQ**, **Preview draft PDF**, **Save RFQ**, **Download RFQ PDF**, and **Publish RFQ** without understanding which one advances the business process, which one merely persists edits, and which one has an external consequence.
2. The assistant uses Groq, but it still behaves like a brittle command router. Earlier code rejected an exact request such as `Generate RFQ for REQ-2026-0033` unless the conversation was opened from a task, even though the advertised tool accepts a `requirement_id`.

This is not a generic product plan. It records the implemented code path, its data model, routes, state transitions, failure modes, and the target replacement. An engineer or LLM should be able to use it to navigate the relevant codebase without rediscovering the architecture.

### Snapshot correction — 19 July 2026

The direct RFQ failure described above has since been partially corrected in the checked-in code:

- `agent_resolution.py::resolve_requirement_reference` resolves exact scoped IDs/business numbers, recent context, selected context, or the latest eligible requirement.
- `agent_service.py::process_intent_envelope` now has a direct `prepare_rfq_draft` branch that calls `workflows.create_rfq_from_requirement`, creates a preview artifact, persists an `AgentActionReceipt`, and records recent entities. It no longer needs a task-bound thread for an explicit requirement reference.
- Own-task output is now filtered to `open`, `in_progress`, and `blocked`, capped at five, and adds limited linked business context.

However, the live agent remains primarily a one-shot Groq capability selector plus handwritten dispatcher. `agent_runtime.py` contains a bounded LangGraph tool/observation loop, and `agent_state.py` contains a versioned state schema, but neither is integrated into `run_message`. The legacy `AgentTurnDecision` path remains active for several capabilities. The central product diagnosis therefore remains valid: Groq is live, but the runtime is not yet a compositional, iterative tool agent.

---

## 1. Executive diagnosis

### 1.1 Why the manual workflow feels confusing

The backend correctly distinguishes draft creation, editing, document rendering, and external release. The frontend displays those implementation concepts as equal actions in one panel.

The business user is trying to do one thing: **request quotations from suitable suppliers**. The system asks the user to understand five technical operations:

| Current label | What the code actually does | Business meaning | Should the normal user see it? |
|---|---|---|---|
| Generate RFQ | Creates an RFQ database draft from a requirement | Start a supplier enquiry | Yes, but call it **Prepare supplier request** |
| Save RFQ | PATCHes deadline and supplier IDs | Save edits to the draft | Prefer autosave; otherwise **Save changes** |
| Preview draft PDF | Persists a non-final generated artifact and opens it | Review exactly what suppliers would receive | Yes, inside the review step, not as a peer workflow action |
| Publish RFQ | Makes the RFQ immutable, creates a final artifact, supplier portal invitations, and email outbox records | Send/release the request to suppliers | Yes: **Send to suppliers**, with consequence confirmation |
| Download RFQ PDF | Finds the final artifact | Download the issued record | Only after sending, under **More** or the sent-state card |

The operations are technically distinct for auditability. They do not need to be visually distinct at all times.

### 1.2 Why the assistant feels deterministic even while Groq is used

The current assistant is a single-capability classifier followed by a large deterministic dispatcher:

```text
user message
  -> Groq chooses at most one allowed capability
  -> server converts the tool call to IntentEnvelope
  -> registry validates role/capability
  -> deterministic process_intent_envelope dispatcher
  -> canonical service or legacy AgentTurnDecision path
  -> optional Groq narration of the already-computed result
  -> grounded-response validator
```

Groq is used at the beginning and often at the end, but it cannot iteratively inspect tool results, revise its plan, resolve an entity with one tool, and then call the mutation tool. Several new capabilities are translated back into old task-bound handlers. Therefore the user experiences old chatbot constraints wrapped in fluent prose.

The target is a bounded ReAct-style runtime:

```text
user request
  -> LLM receives role-scoped tools and compact conversation state
  -> resolve/search/read tool calls
  -> LLM evaluates observations
  -> one canonical mutation or one controlled proposal
  -> persisted receipt
  -> grounded business response and authorized next actions
```

“Agentic” must mean flexible reasoning and tool composition. It must not mean bypassing authority, fabricating records, or directly writing business tables.

---

## 2. Repository map

### Backend

- `apps/api/app/agent_service.py`
  - Main assistant runtime.
  - Builds context, calls Groq, merges deterministic facts, dispatches capabilities, persists runs/events/messages, and validates grounded mutation claims.
  - Also contains legacy `AgentTurnDecision` code and task-bound procurement execution.
- `apps/api/app/agent_capabilities.py`
  - Static capability registry and role authorization.
- `apps/api/app/agent_schemas.py`
  - `IntentEnvelope`, assistant request/response blocks, task and proposal API schemas.
- `apps/api/app/routers/agents.py`
  - Workspace selection, home, threads, messages, runs, events, activity, proposals, delegations, tasks, notifications, knowledge, feedback, agent policy, and emergency-stop endpoints.
- `apps/api/app/domains/workflows.py`
  - Canonical procurement services and state transitions. Manual and assistant flows should converge here.
- `apps/api/app/procurement_v2.py`
  - Document/artifact generation, comparisons, purchase order and later controlled procurement operations.
- `apps/api/app/task_service.py`
  - Task creation, hierarchy authorization, transitions, follow-ups, notifications.
- `apps/api/app/db/models.py`
  - Business, workflow, assistant, task, proposal, receipt, delegation, and memory persistence.
- `apps/api/app/main.py`
  - Manual procurement, document, integration, inbound, and compatibility endpoints.
- `apps/api/app/core/config.py`
  - Provider/model/runtime configuration.
- `apps/api/app/db/seed.py`
  - Demo workspace, roles, master data, transactions, tasks, and agent profiles.

### Frontend

- `apps/web/components/features/WorkflowForms.tsx`
  - Current manual forms for RFQ, evidence review, comparison, approval, negotiation, inbound, PO, and administrative workflows.
- `apps/web/components/features/IndustrialConsole.tsx`
  - Shell/workflow routing, page composition, record tables, action labels, and workbench selection.
- `apps/web/components/features/AgentDrawer.tsx`
  - Conversation UI, suggestion/action buttons, attachments, typed blocks, proposals, and thread interaction.
- `apps/web/app/globals.css`
  - Global shell and workflow presentation.
- `apps/web/lib/api.ts` and generated API types
  - Browser API access and contracts.

---

## 3. Current procurement process, end to end

### 3.1 Business lifecycle

```text
Material master / approved item
  -> Purchase requirement
  -> RFQ draft
  -> supplier shortlist + deadline + document review
  -> published RFQ / supplier invitations
  -> supplier quotations and source documents
  -> extraction and human verification
  -> line-level comparison and recommendation
  -> submission and approval decision
  -> purchase order draft and confirmation
  -> supplier communication / ERP posting
  -> acknowledgement / ASN
  -> gate entry
  -> store receipt
  -> quality inspection and disposition
  -> inventory impact / case closure
```

The separation is necessary because different roles own different consequences and because supplier communication, award approval, PO confirmation, ERP posting, and quality disposition require audit trails.

### 3.2 Role ownership

| Stage | Normal owner | Key authority boundary |
|---|---|---|
| Create requirement | Plant Manager, Purchase Executive, Admin | Must use an approved scoped item or an approved material request result |
| Prepare and issue RFQ | Purchase Executive, Admin | Issue is externally consequential and makes the version immutable |
| Upload quotations | Purchase Executive / Purchase Manager / Admin | Documents must be tenant/plant scoped and linked to an RFQ and supplier |
| Verify extracted evidence | Purchase Manager, Admin | Comparison cannot rely on unverified uncertain fields |
| Prepare comparison | Purchase Manager, Admin | Deterministic calculation from eligible verified quotes |
| Supplier/award decision | Role-specific approval policy | Controlled action with explicit confirmation |
| Confirm PO | Purchase Manager, Admin | Controlled action; later ERP/email consequences remain governed |
| Gate/store/quality | Operational role for that stage | Quantity and disposition events are persisted and auditable |

### 3.3 Requirement creation

Canonical service: `domains/workflows.py::create_requirement`.

It:

1. Authorizes Plant Manager, Purchase Executive, or Admin.
2. Resolves every item in tenant/plant scope.
3. Rejects non-positive quantities.
4. Resolves or validates an active Purchase Executive assignee.
5. Creates a linked `Case`.
6. Creates an approved `PurchaseRequirement` and its line records.
7. Creates an open task titled `Prepare and publish supplier RFQ`, linked with `entity_type="purchase_requirements"` and `entity_id=<requirement.id>`.
8. Writes transition and audit records.

The identical task title is a major display problem. The task row contains the linked entity, but the task list shown by the agent does not present the requirement business number/material as the primary context.

### 3.4 RFQ draft creation: what “Generate RFQ” means

Frontend: `WorkflowForms.tsx::SelectableRfqPanel`.

Route:

```http
POST /procurement/requirements/{requirement_id}/rfqs
```

Canonical service: `domains/workflows.py::create_rfq_from_requirement`.

The service:

1. Authorizes Purchase Executive or Admin.
2. Resolves the requirement inside the current tenant and plant.
3. Returns the existing RFQ if one already exists for the requirement. This is the current idempotency protection.
4. Loads requirement lines, with a compatibility fallback for legacy single-line requirements.
5. Finds approved or conditional suppliers whose approved item capabilities cover every requirement line.
6. Fails when no approved capable supplier exists.
7. Creates an `RFQ` with status `draft`, a business number, calculated deadline, and default supplier shortlist.
8. Copies requirement lines/specifications/certificates into RFQ lines.
9. Creates pending `RFQSupplierInvitation` rows.
10. Links the case to the RFQ and changes the requirement to `rfq_drafted`.
11. Completes tasks linked to the purchase requirement.
12. Creates a new open `Review PDF and publish RFQ` task linked to the RFQ.
13. Writes transition and audit records.

This action does not send anything. The better product label is **Prepare supplier request**.

### 3.5 Draft editing: what “Save RFQ” means

Route:

```http
PATCH /procurement/rfqs/{rfq_id}
If-Match: <record version>
```

The current form sends deadline and selected supplier IDs. `domains/workflows.py::update_rfq` enforces scope, versioning, supplier eligibility, and draft mutability. A published RFQ cannot be edited as if it were still a draft.

This is ordinary draft persistence, not a lifecycle transition. It should autosave after deliberate field changes or use the unambiguous label **Save changes**. It should not compete visually with the send action.

### 3.6 Preview: what “Preview draft PDF” means

Route:

```http
POST /procurement/rfqs/{rfq_id}/pdf-preview
```

It calls `procurement_v2.generate_artifact(db, user, "rfq", rfq_id, final=False)`. A preview artifact/document is persisted and labelled as a review copy that has not been issued. Preview is evidence of what will be sent; it does not publish the RFQ and does not contact suppliers.

The UI should generate/show this inside the **Review** step. If rendering can be cheap and reliable, entering Review should create or refresh the preview automatically.

### 3.7 Publish: what “Publish RFQ” means

Route:

```http
POST /procurement/rfqs/{rfq_id}/publish
If-Match: <record version>
```

Canonical service: `domains/workflows.py::publish_rfq`.

It:

1. Authorizes Purchase Executive or Admin.
2. Is idempotent for an already-published RFQ and returns existing outbox IDs.
3. Requires the RFQ to be a draft.
4. Changes status to `published` and records `published_at`.
5. Generates the final controlled PDF artifact.
6. For each shortlisted supplier with a contact, creates a secure supplier portal token, marks the invitation sent, and creates an idempotent email outbox record with the artifact attached.
7. Completes RFQ-linked tasks and writes transition/audit state.

Important wording: the code creates approved/pending-send outbox messages. “Published” does not necessarily prove that an SMTP provider delivered the email. UI copy must distinguish **prepared for sending**, **dispatched**, and **delivered/failed** if those states are available.

The business label should be **Send to suppliers**. The confirmation should summarize suppliers, deadline, attachment/version, immutability, and the exact communication consequence.

### 3.8 Why “Publish RFQ” appears in more than one place

`SelectableRfqPanel` exposes it in the RFQ builder. `ApprovalReviewPanel` also exposes a publish action as a human-authority decision. Generic workflow action labels can expose it again through `IndustrialConsole.tsx`.

This duplicates a single transition across surfaces without a clear ownership rule. The fix is not merely renaming every button. There must be one canonical action component and a deep link into it. Other pages should show status and a **Review and send** link, not independently reconstruct the mutation control.

### 3.9 Quotations through inbound

- Supplier quotation upload routes create/link documents and asynchronous extraction work.
- Evidence review routes store accept/correct/reject decisions for uncertain fields.
- Comparison generation must use eligible, verified quotation data and persist its own version/artifact.
- Comparison submission and decision are separate because preparation is not authority to award.
- PO preparation, preview, approval, supplier email, and ERP posting are separate controlled consequences.
- ASN, gate entry, receipt, and inspection are factual operational events and must not be collapsed into procurement approval.

The same UX principle applies throughout: show the current state, explain the consequence, and present one primary next action. Keep audit transitions in the backend; do not teach users backend verbs.

---

## 4. Manual UX problem inventory and replacement

### 4.1 RFQ target interaction

When opened from a requirement, do not ask the user to select the requirement and then separately select an RFQ. Preserve the originating record context.

```text
REQ-2026-0033 · Aluminium Ingot · 132 KG · needed 01 Aug

Step 1  Request details       complete
Step 2  Suppliers             3 eligible selected
Step 3  Review                preview available
Step 4  Send                  ready

[Back]                                      [Review and send]
```

State-dependent primary action:

| State | Primary action | Secondary actions |
|---|---|---|
| Approved requirement, no RFQ | Prepare supplier request | View requirement |
| Draft with missing/invalid data | Complete supplier request | Save and exit |
| Complete draft | Review and send | Save and exit |
| Review screen | Send to 3 suppliers | Back to edit, download preview |
| Published/pending dispatch | View sent request | Download issued PDF, view delivery status |
| Published/dispatched | Track quotations | Download issued PDF |

### 4.2 Global language system

Use business verbs consistently:

| Avoid | Use |
|---|---|
| Generate RFQ | Prepare supplier request |
| Publish RFQ | Send to suppliers |
| Save RFQ | Save changes |
| Generate comparison | Compare verified quotations |
| Submit comparison | Send recommendation for approval |
| Confirm PO | Create purchase order after approval |
| Supplier email | Send purchase order to supplier |
| Record decision | Approve / Reject / Request changes |
| Entity, artifact, outbox, run, receipt | Record name, document, delivery status; hide runtime nouns |

### 4.3 Other confusing surfaces to audit

The same issue is visible in `WorkflowForms.tsx` beyond RFQ:

- **Comparison:** “Generate,” “preview,” “submit,” and “decision” need a visible state sequence: Verify quotes -> Compare -> Review recommendation -> Request approval -> Decision.
- **Awards/approvals:** distinguish recommendation from authorized award. Never display multiple controls that cause the same decision.
- **PO:** “draft,” “preview,” “approve,” “supplier email,” and “ERP post” need business copy and consequence summaries. Approval is not dispatch; dispatch is not ERP acknowledgement.
- **Negotiation:** “Create draft,” “Submit,” “Approve,” “Counteroffer,” and “Accept” currently require the user to infer who authored each state and what leaves the system. Show a conversation/round timeline and one next action.
- **Quotation verification:** “accept,” “correct,” and “reject” need source evidence, confidence, units, and an explanation of whether rejection blocks comparison.
- **Inbound:** ASN, gate entry, receipt, and inspection must show the selected PO/material/supplier context; never make users choose raw IDs from disconnected dropdowns.
- **Generic tables:** hide raw UUIDs, JSON objects, empty `{}`, technical status strings, counts, versions, and internal relation names.

### 4.4 Interaction rules

1. One visually dominant action per state.
2. A destructive/external/immutable action gets a consequence confirmation; ordinary saving does not.
3. Disabled controls must say why and what resolves the blocker.
4. Preserve selected requirement/RFQ across routes and refreshes.
5. Display business numbers, material, quantity, supplier, owner, due date, and status—not raw IDs.
6. Autosave ordinary draft fields with explicit saved/error feedback.
7. Keep manual and assistant execution equivalent by calling the same canonical service.
8. After a successful mutation, update page records, tasks, badges, notifications, and assistant context together.

---

## 5. Current assistant architecture

### 5.1 Persistent objects

Important models in `db/models.py`:

- `AgentProfile`: role agent identity, allowed/blocked actions, provider/model profile, token budgets, prompt/policy versions, enabled state, escalation policy.
- `AgentThread`: membership/profile, thread type, optional `work_item_id`, participant scope, and JSON `context_state`.
- `AgentMessage`: user/assistant messages, structured blocks, citations, visibility, correlation ID.
- `AgentRun`: provider/model, intent, state, latency/tokens, policy trace, errors, active context, correlation ID.
- `AgentEvent`: ordered execution events.
- `AgentCheckpoint`: persisted orchestration state snapshots.
- `AgentToolCall`: tool arguments, target, authorization decision, result hash, latency.
- `AgentProposal`: controlled action preview, authority, state, expiry, version, risk, rationale, idempotency.
- `AgentActionReceipt`: proof that a tool mutation succeeded or failed, including target entity and result summary.
- `AgentDelegation`: sender/recipient agent and membership, work item/objective, context packet, due date, response, depth.
- `Task`: assignee, creator/delegator, entity link, objective/delegation, status, due/follow-up/escalation fields.
- `AgentMemory` and knowledge models: governed persisted context/knowledge support.

`AgentThread.context_state` carries draft fields, active intent/current work item, recent entities, attachment metadata, last execution/receipt, candidate state, and timestamps. It is useful, but its schema is implicit JSON and different handlers interpret it differently.

### 5.2 Public assistant API

Core endpoints in `routers/agents.py`:

- `GET/POST /agent/threads`
- `GET /agent/threads/{thread_id}`
- `GET /agent/threads/{thread_id}/context`
- `POST /agent/threads/{thread_id}/messages`
- `GET /agent/runs/{run_id}` and `/events` and `/activity`
- `POST /agent/runs/{run_id}/cancel`
- proposal list/create/confirm/reject
- delegation list/create/respond
- task create/team/detail/transition/request-update
- notifications, knowledge, feedback
- admin agent policy and emergency stop

Message request fields are content, attachment IDs, and optional `requested_capability`. A clicked action can therefore bypass natural-language tool selection and directly request a capability; it still must pass registry authorization.

The message response includes the assistant message/blocks plus current work item, allowed actions, created/updated records, job state, and badge counts.

### 5.3 Capability registry

`agent_capabilities.py` declares:

- General: answer work context, list own tasks, get record.
- Manager: list team tasks, request updates, delegate, summarize team status.
- Procurement: list/search materials, create material request, create requirement, risk summary.
- Purchase Executive/Admin: prepare RFQ draft, controlled RFQ publication, quote operations.
- Purchase Manager/Admin: verify extraction, prepare comparison, controlled comparison submission, controlled PO.
- Role-specific comparison decisions and supplier follow-up.

Each capability declares allowed roles, required/optional fields, controlled status, allowed attachment types, adapter name, and response card. `validate_intent` rejects unknown capabilities with `422 Unknown assistant capability`, rejects unauthorized role selection with 403, and forces confirmation on controlled capabilities.

This registry is a good policy boundary. It is not an execution engine. Required fields are not consistently enforced through one generic validated adapter layer; some legacy handlers impose unrelated requirements.

### 5.4 `run_message` execution flow

`agent_service.py::run_message` currently performs the following:

1. Resolve membership, enforce token/run limits, ensure the role agent is enabled, and resolve the thread.
2. Validate every attachment against tenant, plant, and user scope; store bounded attachment context.
3. Allocate a correlation ID.
4. Build an `AgentContextEnvelope` containing workspace/plant/membership/role, reporting scope, thread/work-item identity, entity ACL, tools/restrictions, knowledge, budgets, and policy.
5. Load authorized tasks/records/knowledge/citations into a compact context payload.
6. Add role-allowed capability IDs, bounded context state, material candidates, and attachments.
7. Persist the user message and new `AgentRun`; record events/checkpoints.
8. If the client requested a capability, create its envelope directly. Otherwise call Groq.
9. Groq uses native tool calling (`ChatGroq.bind_tools(..., tool_choice="auto")`) with only role-allowed capability definitions. The prompt says to retain supplied facts, choose a suitable tool, and not invent records.
10. Convert the selected tool call to `IntentEnvelope`. If Groq emits no tool call, fall back to `answer_work_context`.
11. On provider failure, optionally use deterministic fallback parsing.
12. Merge parsed facts, catalog matches, recent state, and candidates. Explicit mutation wording may override a weak model search/context selection.
13. Validate the capability and role in `CAPABILITY_REGISTRY`.
14. Merge envelope facts into thread context.
15. Call `process_intent_envelope`.
16. The adapter calls a canonical service, creates a controlled proposal, or translates back to legacy `AgentTurnDecision` processing.
17. Optionally ask Groq to narrate the grounded result. Clarification blocks are generally kept deterministic.
18. `validate_grounded_response` prevents mutation claims unless a matching successful `AgentActionReceipt` exists and replaces unsupported future promises.
19. Persist assistant message, run completion/error, events, checkpoints, tool calls, receipts, recent entities, and context.

### 5.5 What is genuinely LLM-driven

- Natural language interpretation and initial capability/tool selection.
- Extraction of arguments into the tool schema.
- Some response narration after execution.
- Semantic flexibility when the selected adapter supports the supplied entities.

### 5.6 What remains deterministic or legacy

- Exactly one capability is normally selected per turn.
- No iterative observation/tool/reason/tool loop exists.
- Catalog matching and dates still include deterministic normalization/regex paths.
- `process_intent_envelope` is a large handwritten switch.
- Several registry capabilities are mapped into old `AgentTurnDecision` intents.
- Old handlers assume the conversation was opened from a task.
- Some declared capabilities end in `This assistant capability is not implemented yet`.
- Typed suggestion actions bypass model selection.
- Response cards and missing-field prompts are server templates.

This is why changing only the Groq model will not fix the product. A stronger model cannot use a requirement ID that the adapter discards.

---

## 6. Exact RFQ assistant failure — historical incident and current correction

### 6.1 Transcript one

User:

> Can you generate the RFQ for the latest requirement

Observed result: a list of 34 tasks, including many rows titled `Prepare and publish supplier RFQ`, followed by raw `count 34`.

Likely execution:

1. Groq sees a large task-heavy context and chooses `list_my_tasks` instead of `prepare_rfq_draft`.
2. “latest requirement” is not resolved deterministically into the latest accessible eligible requirement before capability execution.
3. The task adapter returns all visible tasks without an active-only default, useful limit, semantic grouping, or deduplication.
4. The response block exposes every task item and raw record fields, so the UI prints an operational dump instead of answering the request.

Why titles repeat:

- Every requirement created by `workflows.create_requirement` generates a task with the same title.
- Creating its RFQ completes the requirement task and creates another task titled `Review PDF and publish RFQ`.
- Different requirements therefore look identical if the UI omits their business number/material.
- Completed rows are included with active rows.
- Repeated demo/reconciliation or non-idempotent creation paths may add genuine duplicates; that must be verified in data rather than assumed from titles alone.

Required diagnostic query:

```sql
SELECT title, entity_type, entity_id, owner_membership_id, status, count(*)
FROM tasks
WHERE title IN ('Prepare and publish supplier RFQ', 'Review PDF and publish RFQ')
GROUP BY title, entity_type, entity_id, owner_membership_id, status
HAVING count(*) > 1;
```

Even legitimate separate tasks must render as, for example:

```text
Prepare supplier request
REQ-2026-0033 · Aluminium Ingot · 132 KG · due today
```

They must not render as 34 identical commands.

### 6.2 Transcript two (historical root cause)

User:

> Generate RFQ for REQ-2026-0033

Observed result:

> Task context required. Open the assigned task before asking me to prepare this procurement step.

The following was the architectural cause in the prior implementation:

1. `CAPABILITY_REGISTRY['prepare_rfq_draft']` correctly declares required field `requirement_id`.
2. `process_intent_envelope` maps `prepare_rfq_draft` to the legacy intent `prepare_rfq`.
3. `process_agent_decision` calls `execute_contextual_procurement_workflow`.
4. That function first requires `thread.work_item_id`, `context_state.current_work_item`, or attachments. With none, it emits the task-context warning.
5. It loads `task` only from `thread.work_item_id`.
6. The `prepare_rfq` branch ignores the `requirement_id` extracted from the user message and insists that `task.entity_type == 'purchase_requirements'`.
7. A normal personal agent thread has no bound task, so an exact valid business number cannot execute.

There is also a null-safety risk: `has_resolved_context` can be true because `current_work_item` exists while `task` remains `None`, but the RFQ branch directly reads `task.entity_type`.

This was the central bug: the public tool contract was entity-driven while the implementation was task-driven. Task context should help resolution and authorization, never be an unrelated prerequisite when the user supplies an authorized exact record.

**Current correction:** the checked-in `prepare_rfq_draft` capability now resolves an explicit/reference/latest requirement with `resolve_requirement_reference`, then calls the canonical RFQ and artifact services directly. It records a tool call and `AgentActionReceipt`. Regression tests still need to verify the literal user transcript against the running stack; the code change alone is not acceptance evidence.

### 6.3 Correct behavior

For “Generate RFQ for REQ-2026-0033” the agent should:

1. Resolve `REQ-2026-0033` in the current tenant/plant.
2. Check Purchase Executive/Admin capability authorization.
3. Verify requirement eligibility and existing RFQ.
4. Call `workflows.create_rfq_from_requirement` directly.
5. Generate the draft preview artifact.
6. Persist a receipt and recent entity state.
7. Return a compact card:

```text
Supplier request RFQ-2026-00xx is ready for review.
REQ-2026-0033 · Aluminium Ingot · 132 KG
3 approved capable suppliers · deadline 01 Aug 2026

[Review draft] [Edit suppliers]
```

The send action remains separate and controlled:

```text
[Send to 3 suppliers]
```

For “latest requirement,” use this resolution order:

1. Recent requirement entity in thread state if still eligible.
2. Selected page/work-item requirement.
3. Latest accessible requirement owned by/assigned to the user that has no published RFQ, ordered by creation time.
4. If multiple records are meaningfully tied or “latest” could cause a risky wrong action, show at most three business-labelled candidates and ask once.

Do not list every task.

---

## 7. Target agent architecture

### 7.1 Bounded ReAct loop

Replace single-shot selection with a server-controlled loop, maximum 4–6 tool observations per turn. A generic implementation already exists in `agent_runtime.py`; the work remaining is integration into the live `run_message` path, typed adapters, observations, persistence and regressions:

```text
initialize role-scoped context
repeat within step/time/token budgets:
  LLM chooses one authorized tool or final response
  validate schema + role + entity scope
  execute read/resolution tool OR prepare one mutation
  append compact observation
  if mutation succeeded: stop further mutations
  if controlled action prepared: stop and request confirmation
  if sufficient answer: stop
otherwise return a bounded safe clarification/error
```

Rules:

- Unlimited reads are not allowed; enforce budgets.
- At most one business mutation per user turn.
- Controlled consequences create proposals and stop until explicit confirmation.
- The LLM never receives unrestricted database/HTTP/shell tools.
- The LLM never declares success; the receipt-backed response layer does.
- Tool observations contain business summaries, not giant raw row dumps.

### 7.2 Tool families

Keep tools small and composable:

**Resolution/read tools**

- `resolve_record(reference, allowed_types)` — accepts business number, exact ID, recent reference, “latest,” selected page record.
- `search_records(type, query, status, limit)` — tenant/plant and role scoped.
- `get_record_summary(entity_type, entity_id)`.
- `list_actionable_work(status='active', limit=5)` — grouped/deduplicated, with linked business context.
- `resolve_material(query)`.
- `resolve_assignee(role, query)`.
- `get_workflow_state(entity_type, entity_id)` — current state, blockers, allowed next actions.

**Canonical business tools**

- create material master request proposal.
- create requirement.
- prepare RFQ draft.
- prepare quotation upload/extraction.
- verify evidence.
- prepare comparison.
- prepare controlled publish/submit/decision/PO actions.
- task delegation and follow-up.

**Communication tools**

- Ask an employee agent for a task update by creating a governed follow-up/delegation event.
- Read recorded response/status.
- Summarize it to the manager with source, timestamp, blocker, and next commitment.

Agent-to-agent behavior must be persisted workflow communication, not hidden LLM roleplay. The employee agent acts inside that employee membership’s scope and cannot disclose unrelated work.

### 7.3 Adapter contract

Every capability adapter should accept the same context shape:

```text
(db, actor, membership, thread, run, validated_args, correlation_id)
  -> ToolResult
```

`ToolResult` should contain:

```text
status
business_summary
records
observations
missing_fields
allowed_next_actions
proposal (optional)
receipt (required for mutation)
citations
```

Remove the remaining mappings from new capability IDs back to `AgentTurnDecision`. `prepare_rfq_draft` now has a direct adapter consuming a requirement reference; use it as the template. Task context is one input to `resolve_record`, not an execution gate.

### 7.4 Entity resolution contract

Resolution order:

1. Exact scoped database ID.
2. Exact scoped business number, case-insensitive and punctuation-normalized.
3. Explicit selected record/page context.
4. Recent entity references (“it,” “that requirement,” “its ID”).
5. Safe semantic qualifiers (“latest eligible requirement”).
6. Search candidates, bounded to three.

Never ask the model to invent or remember database IDs. Return canonical business numbers and persist resolved IDs in thread state.

### 7.5 Conversation memory

Define and version the `context_state` schema rather than allowing ad hoc keys:

```json
{
  "schema_version": 2,
  "active_goal": {"capability": "prepare_rfq_draft", "status": "resolving"},
  "draft_fields": {},
  "selected_context": {"type": "purchase_requirement", "id": "..."},
  "recent_entities": [],
  "pending_proposal_id": null,
  "last_receipt": {},
  "attachments": [],
  "blocked_on": null,
  "updated_at": "..."
}
```

On topic change, clear incompatible candidate/error state but retain explicitly reusable facts. After mutation, store the actual record and receipt. Never let a stale prompt card override a newer user instruction.

### 7.6 Agent-to-agent progress flow

Desired manager conversation:

```text
Manager: What is blocking the supplier request for REQ-2026-0033?
Manager agent: resolves the requirement and assigned active task
Manager agent: creates a follow-up to the Purchase Executive's agent
Employee agent: reads authorized task/workflow state and requests human input only if needed
Employee/agent response: "RFQ draft is ready; waiting for supplier shortlist approval"
Manager agent: returns sourced status, timestamp, owner, blocker, and action
```

Persistence:

- `AgentDelegation` records sender, recipient, work item, outcome, context, due date, status, response, and bounded depth.
- `Task.last_follow_up_at`, `next_follow_up_at`, escalation fields, notifications, and events show the operational consequence.
- A manager may only contact descendants allowed by the reporting tree.
- No recursive uncontrolled agent chat. Limit delegation depth and cycle detection.
- Human-owned decisions remain human-owned.

### 7.7 Response policy

Responses should answer first and expose only useful business context:

- Maximum five task items unless user asks for more.
- Default task query means active/actionable; completed work belongs in a summary.
- No raw UUID unless explicitly requested.
- No raw JSON, `{}`, `count`, run/checkpoint/tool/receipt terminology.
- Mutation language only with a matching receipt.
- Provide next actions that the membership can actually perform.
- A clarification asks only for genuinely missing information and retains prior facts.

---

## 8. Required implementation sequence

### Phase 1 — Fix the demonstrated RFQ failures

1. Add regressions for both exact transcripts before changing runtime behavior.
2. **Implemented in source, needs running regression proof:** `resolve_requirement_reference` supports exact business number and latest eligible requirement.
3. **Implemented in source, needs running regression proof:** direct `prepare_rfq_draft` calls canonical RFQ/artifact services and persists a receipt.
4. Verify receipt, RFQ/requirement recent entities, selected context and response card through API/UI tests.
5. **Partially implemented:** own-task listing is active-by-default and capped at five; add grouping, material context and duplicate reconciliation.
8. Audit and reconcile genuine duplicate tasks. Add idempotency protection for active workflow tasks by semantic key.
9. Never expose raw task count/objects in prose blocks.

### Phase 2 — Introduce the bounded tool loop

1. Extract every capability into a typed adapter map.
2. Add read/resolution tools and compact observation schemas.
3. Implement bounded iterative Groq tool execution.
4. Enforce one mutation, role scope, entity scope, controlled actions, timeout, token and step budgets at every iteration.
5. Retire active use of `AgentTurnDecision`, legacy regex intent routing, and task-context gates.
6. Retain deterministic parsing only for normalization and provider-outage continuation when context is unambiguous.
7. Keep grounded receipt validation as the final hard boundary.

### Phase 3 — Rebuild manual workflow presentation

1. Replace `SelectableRfqPanel` with a requirement-scoped RFQ stepper.
2. Rename actions using the global language table.
3. Autosave draft edits and centralize immutable send confirmation.
4. Remove duplicate publish controls; deep-link all surfaces to the canonical Review and send step.
5. Apply the same state/next-action pattern to quotation verification, comparison, approvals, PO, negotiation, and inbound.
6. Replace generic raw tables with business cards/tables and meaningful empty states.
7. Refresh home/tasks/badges after every transition.

### Phase 4 — Agent/manual convergence and agent-to-agent work

1. Make UI and assistant call identical canonical services.
2. Let assistant actions open the same selected record and stateful workbench.
3. Implement manager follow-up as persisted delegation/task communication.
4. Add notifications and team-status aggregation sourced from real responses.
5. Enforce reporting-tree and workspace isolation in services and tests.

---

## 9. Acceptance tests

### 9.1 RFQ assistant

- `Can you generate the RFQ for the latest requirement` resolves one eligible requirement or asks one bounded ambiguity question; it never dumps all tasks.
- `Generate RFQ for REQ-2026-0033` works from a normal personal assistant thread without opening a task.
- Exact internal ID and exact business number resolve equivalently within scope.
- An unauthorized role cannot prepare or publish.
- An out-of-plant or out-of-tenant requirement is not revealed.
- If an RFQ already exists, return it idempotently and explain its current state.
- If no capable supplier exists, state that blocker and offer the authorized remediation; do not create an invalid draft.
- RFQ creation returns a persisted RFQ number and preview artifact backed by a receipt.
- Publication remains a separate proposal/confirmation and does not occur from “generate.”
- Provider outage uses fallback only when requirement/action are unambiguous.

### 9.2 Tasks

- Own tasks default to open/blocked/in-progress actionable states.
- Output is ordered by urgency and limited.
- Each row includes linked business number/material, owner, status and due state.
- Completed rows appear only when requested or summarized.
- Task creation/reconciliation is idempotent for the same workflow/entity/owner active state.
- Different requirements with identical task types remain distinguishable.

### 9.3 Manual RFQ UX

- Opening from a requirement retains that context and does not require two selectors.
- Only one primary next action is visible per state.
- Draft changes persist with clear save status.
- Review shows the unissued preview and selected suppliers/deadline.
- Send confirmation explains immutability, recipients, and communication consequence.
- After send, the screen shows final document and delivery/outbox status, not draft controls.
- The same publish mutation cannot be independently triggered from several unrelated panels.
- Keyboard, mobile, focus, loading, error recovery, and 44px control targets are verified.

### 9.4 Agent-to-agent

- Manager can request an update only from authorized descendants.
- The follow-up is persisted, visible to the recipient, and linked to the task/entity.
- The answer quotes real workflow/task state and includes timestamp/owner/blocker.
- Workspace and private-thread isolation hold.
- Depth/cycle limits prevent recursive agent chatter.
- No employee agent can approve on behalf of a human authority.

### 9.5 Required gates

- API unit/integration tests and exact transcript regressions.
- Migrations and schema checks.
- OpenAPI regeneration/check and frontend typecheck.
- Production frontend build.
- Docker Compose health.
- Playwright at desktop/tablet/mobile for requirement -> RFQ -> send and assistant exact-number/latest flows.
- Screenshot comparison for home, assistant, RFQ review/send, quotation verification, comparison, and approval.

---

## 10. Non-negotiable invariants

1. Groq/LLM interprets and plans; canonical services authorize, calculate, and persist.
2. The model never writes business tables directly.
3. Unknown and unauthorized tools are rejected server-side.
4. One business mutation per turn.
5. Supplier release, comparison submission/decision, PO confirmation, external communication, ERP posting, and quality disposition retain explicit authority boundaries.
6. Mutation claims require persisted receipts.
7. All reads and writes are tenant, workspace, plant, membership, and reporting-scope aware.
8. Agent-to-agent interaction is persisted, inspectable, bounded, and authorized—not simulated hidden conversation.
9. Manual and assistant paths use the same canonical services and state machine.
10. Internal lifecycle precision remains in code and audit records; the interface uses clear business language.

---

## 11. Definition of done

This work is not complete because Groq appears in `agent_runs`, because the prose sounds natural, or because buttons were recolored.

It is complete when a Purchase Executive can type either of the demonstrated RFQ requests in an ordinary conversation, the assistant resolves the correct authorized requirement, uses tools across observations when necessary, prepares the real RFQ through the canonical service, returns its persisted business identity, and offers the correct governed next action. It is complete when the same user can perform that workflow manually without needing to understand the words generate, artifact, publish, outbox, or record version. It is complete when a manager’s request for progress becomes a real, authorized, persisted follow-up to the responsible employee and the answer is grounded in the resulting work state.

---

## 12. Complete repository inventory

This section lists every meaningful source area in the repository and states its responsibility. Files omitted from the detailed tables are generated metadata, `__init__.py`, operating-system metadata (`*.Zone.Identifier`), local screenshots, or standard build configuration.

### 12.1 Repository root

| Path | Role | Notes for future work |
|---|---|---|
| `README.md` | Main getting-started and architecture summary | Good high-level orientation; it describes intended safety controls, not proof of enterprise certification. |
| `.env.example` | Local configuration template | Never add customer credentials or live production secrets to source control. |
| `docker-compose.yml` | Full local topology | PostgreSQL, Redis, MinIO, Mailpit, migrations, seed, API, worker, beat, web. Local defaults deliberately simulate SMTP/ERP. |
| `package.json` / `package-lock.json` | Monorepo root scripts/dependencies | Defines build, typecheck, API tests, OpenAPI check, and Playwright test commands. |
| `playwright.config.ts` | Browser test setup | Uses Playwright and axe package dependencies. |
| `BACKEND_PLAN.md`, `FRONTEND_PLAN.md`, `PLAN*.md`, `CHANGE_REVIEW_REPORT.md`, `HANDOFF.md` | Historic planning/review material | Useful context, but this `HANDOFF2.md` is the consolidated current engineering handoff. Resolve conflicts in favor of checked-in source. |
| `GG_OnePager.pdf`, `deliverables/` | Sales collateral | Not runtime code. Keep claims aligned with actual production controls. |
| `ssss1.png`, `ui.png`, `test-results/client-demo/` | Current and target/reference screenshots | Useful visual benchmark; not product assets. |
| `tools/generate_*.py` | One-pager generation scripts | Non-runtime collateral tooling. |

### 12.2 Backend application file catalog

| Path | Primary responsibility | Current status / planning implications |
|---|---|---|
| `apps/api/app/main.py` | FastAPI application, CORS, middleware wiring, exception handling, legacy/manual HTTP routes | Large route file. It mixes old and V2 endpoints; future work should progressively move route bodies into routers/services without breaking contracts. |
| `apps/api/app/models.py` | Pydantic API/view models such as workspace overview, work items, control tower, legacy procurement records | Separate from SQLAlchemy `db/models.py`. Preserve that distinction. |
| `apps/api/app/api_schemas.py` | Typed request schemas for manual procurement, org, integration, inbound and document routes | Add schema validation before adding a write route. |
| `apps/api/app/repositories.py` | Data-access helpers | Audit usage before adding new direct queries; the codebase currently still has many direct query paths. |
| `apps/api/app/identifiers.py` | Identifier utilities | Business numbers and stable references should use a unified policy. |
| `apps/api/app/e2e_server.py` | Test server helper | Used for browser/integration test execution. |
| `apps/api/app/celery_app.py` | Celery configuration/queues/schedules | Queues include agents, documents, integrations, email and sync. |
| `apps/api/app/workers.py` | Celery task entry points | Document processing/recovery, integration dispatch, email, sync/import, internal follow-ups. |
| `apps/api/app/storage.py` | S3/MinIO client and object storage access | Local Compose uses private MinIO buckets; production needs managed S3-compatible storage and lifecycle policy. |
| `apps/api/app/documents.py` | File validation, quarantine, extraction, evidence, download URLs | Supports PDF/image/XLSX extraction, OCR fallback, optional Groq structured extraction, verification states. Uploaded text must remain untrusted. |
| `apps/api/app/integrations.py` | Outbox dispatch, SMTP send, sync jobs, master-data import | Critical ERP safety boundary. Uses attempts, external references, payload hashes and retry state. |
| `apps/api/app/erp.py` | ERP adapter protocol and Local/Oracle/SAP adapters | Local fully simulates; Oracle has an OAuth/REST write path gated by live flags; SAP is currently contract-only. Do not market SAP live write support. |
| `apps/api/app/task_service.py` | Task authority, reporting descendants, lifecycle, follow-up and manager summary | Canonical coordination service; duplicate task semantics need explicit idempotency policy. |
| `apps/api/app/agent_capabilities.py` | Capability allowlist by role | Server-side policy boundary. Must remain authoritative even if model/prompt changes. |
| `apps/api/app/agent_schemas.py` | Agent context/envelopes, intent, state V2, tool result, blocks, proposals, tasks, identity schemas | Contains both modern schemas and legacy `AgentTurnDecision`; eliminate legacy only after full migration. |
| `apps/api/app/agent_service.py` | Live agent orchestration and most adapter behavior | Largest architectural risk: it combines provider calls, parsing, context, capability dispatch, receipts, proposals, delegation, seed/fresh-workspace helpers. Split into modules only after tests lock behavior. |
| `apps/api/app/agent_resolution.py` | Scoped business record/material/assignee/requirement resolution | Newer foundation. Resolver currently has simple matching; extend normalization/candidate explanations safely. |
| `apps/api/app/agent_state.py` | `AgentThreadStateV2` loading, merging and entity memory | Exists but is not the sole live state writer. Make it the only thread-state mutation gateway. |
| `apps/api/app/agent_runtime.py` | Generic bounded LangGraph decision/execution loop | Exists but is not called from `run_message`; this is a high-value integration target, not evidence that ReAct is live. |
| `apps/api/app/procurement_v2.py` | V2 feature-gated artifacts, material requests, comparison approval, PO confirmation/email | Canonical V2 service layer; overlaps older `workflows.py` functionality. Clarify which is authoritative per stage. |
| `apps/api/app/domains/workflows.py` | Main canonical workflow transitions, scope helpers, records, requirements, RFQs, quotes, comparison, negotiation, PO, inbound, control tower | Core business source of truth. It is large and contains both V1 and V2 compatibility logic. |
| `apps/api/app/domains/state_machine.py` | Allowed lifecycle transitions | Enforces invalid transitions with 409. Expand it whenever a new state is added. |
| `apps/api/app/core/config.py` | Typed environment settings and production safety validation | Production validation is useful but does not replace cloud/network/secrets controls. |
| `apps/api/app/core/security.py` | Argon2, opaque sessions, MFA, token sealing, session selection, CSRF, login lockout | Enterprise hardening needs independent security review. |
| `apps/api/app/core/permissions.py` | Role and scope checks | Use this/service-level checks; do not rely on frontend navigation restrictions. |
| `apps/api/app/core/middleware.py` | Idempotency and request logging | Unsafe request replay uses actor-scoped idempotency records. Ensure external adapters share the same semantic idempotency key. |
| `apps/api/app/core/rate_limit.py` | Rate-limit support | Used around login/agent controls as applicable. |
| `apps/api/app/core/metrics.py` | Prometheus metric definitions | Wire dashboards/alerts before production. |
| `apps/api/app/db/models.py` | SQLAlchemy persistence model | The definitive physical data model. |
| `apps/api/app/db/session.py` | Database engine/session lifecycle | PostgreSQL in Compose; fallback SQLite for directly started local API. |
| `apps/api/app/db/seed.py` | Demo data and idempotent seed/reconciliation | It must never seed transactional demo data into fresh customer workspaces. |
| `apps/api/app/db/seed_cli.py` | Seed command entry point | Invoked by Compose seed one-shot job. |
| `apps/api/app/routers/agents.py` | Agent/workspace/task/delegation/proposal/knowledge routes | Distinct router mounted by main app. |
| `apps/api/app/routers/identity.py` | Sessions, MFA, password recovery, invitations, setup | Identity surface; high security sensitivity. |
| `apps/api/app/routers/health.py` | Liveness/readiness/metrics | Readiness should gate deployment. |
| `apps/api/app/routers/backend_plan.py` | Workspace home, demo access/reconcile, notification-read helpers, context summary | Name is historical and misleading; consider renaming after clients migrate. |
| `apps/api/app/migrations/versions/*.py` | Alembic history 0001–0012 | Never edit already-applied migration history; add a new migration for schema change. |
| `apps/api/app/scripts/check_openapi_contract.py` | OpenAPI contract drift check | Run after API type changes. |
| `apps/api/app/scripts/stamp_openapi_contract.py` | Stores checked contract metadata | Used by root API generation command. |
| `apps/api/app/tests/*.py` | API, production-contract, ERP, role-agent, control tower, intent runtime tests | Expand regressions around exact user transcripts and true ERP failure/reconciliation behavior. |
| `apps/api/app/tests/agent_eval/live_groq_scorecard.py` | Optional live provider evaluation | Must never run live ERP writes; pin a dataset and record model/prompt version. |

### 12.3 Frontend application file catalog

| Path | Primary responsibility | Current status / planning implications |
|---|---|---|
| `apps/web/app/layout.tsx` | Global Next.js layout/font metadata | Keep global accessibility/language metadata here. |
| `apps/web/app/globals.css` | Whole visual system | Large global stylesheet; current UI needs consolidation into a deliberate token/component system. |
| `apps/web/app/page.tsx` | Root application entry | Redirects/composes the default console route. |
| `apps/web/app/login/page.tsx` | Login | Auth UI uses `IndustrialConsole` flow rather than a separate design system. |
| `apps/web/app/accept-invitation/page.tsx` | Invitation acceptance | Identity onboarding surface. |
| `apps/web/app/workspace/setup/page.tsx` | Workspace/bootstrap UI | Needs clear customer onboarding path: organization, plant, people, reporting tree, master data, policies. |
| `apps/web/app/agent/page.tsx` | Dedicated agent workspace | Should become a useful advanced agent/work register, not an escape hatch for normal workflows. |
| `apps/web/app/control-centre/page.tsx` | Control tower | System/process monitoring view. |
| `apps/web/app/procurement/page.tsx` | Requirement/material procurement view | Main entry for procurement users. |
| `apps/web/app/rfq-builder/page.tsx` | RFQ workbench | Current manual RFQ UI is the principal UX remediation target. |
| `apps/web/app/quotes/page.tsx` | Quote upload/list | Needs workbench-level context and evidence status. |
| `apps/web/app/evidence/page.tsx` | Extraction verification | Uses side-by-side source/review model. |
| `apps/web/app/comparison/page.tsx` | Comparison workbench | Needs clear reviewed vs submitted vs approved state. |
| `apps/web/app/approvals/page.tsx` | Approval work | Must not duplicate mutation controls found elsewhere. |
| `apps/web/app/negotiations/page.tsx` | Negotiation work | Needs a user-readable conversation/timeline model. |
| `apps/web/app/po-drafts/page.tsx` | PO preparation/review | Keep PO creation separate from supplier send and ERP post. |
| `apps/web/app/gate/page.tsx`, `store/page.tsx`, `quality/page.tsx`, `inbound/page.tsx` | Inbound operational views | Preserve ordered dependency: PO -> ASN/gate -> receipt -> inspection. |
| `apps/web/app/cases/page.tsx` | Exception/case view | Exception recovery should never obscure the primary cycle stage. |
| `apps/web/app/outbox/page.tsx`, `integrations/page.tsx` | External delivery/integration views | Enterprise operators need clear pending/sent/failed/reconciled states. |
| `apps/web/app/audit/page.tsx` | Audit view | Security/admin role restricted. |
| `apps/web/app/admin/page.tsx` | Admin/workspace management | Avoid mixing general operations workflow with high-risk admin controls. |
| `apps/web/components/industrial/IndustrialConsole.tsx` | Main shell, auth load, data loading, nav, content routing, generic tables and workflows | Current UI’s largest frontend file and primary refactor candidate. It mixes data orchestration, navigation, page body, generic tables and formatting. |
| `apps/web/components/industrial/AgentDrawer.tsx` | Persistent right-side assistant, blocks, attachments, messages | Renders server blocks. Must hide legacy/internal block headings and make actions/business cards polished. |
| `apps/web/components/industrial/AgentWorkspace.tsx` | Agent queue, activity, follow-ups, delegation register, role workspace | Useful for agent operations but currently has overlapping conversation component concepts. |
| `apps/web/components/industrial/WorkspaceCommandPalette.tsx` | Search/command UI | Candidate for unified record/action navigation. |
| `apps/web/components/features/WorkflowForms.tsx` | All focused manual workflow forms | Contains too many unrelated panels in one file. Split by domain after preserving behavior. |
| `apps/web/lib/api.ts` | Browser API base selection, API calls and manually maintained view types | Generated shared client exists separately; converge to one typed contract after backend stabilizes. |
| `apps/web/lib/format.ts` | Role/money/general formatting | Expand locale-aware formatting deliberately. |
| `apps/web/lib/useRouteSelection.ts` | Query-parameter selected-record hook | Important for deep links from assistant/tasks into manual workbenches. |
| `apps/web/e2e/role-workflows.spec.ts` | Role workflow browser tests | Extend with exact workflow language and error-recovery assertions. |
| `apps/web/e2e/client-demo-screenshots.spec.ts` | Screenshot/demo scenes | Keep as visual regression evidence at multiple required viewports. |

### 12.4 Shared packages and deployment catalog

| Path | Purpose |
|---|---|
| `packages/shared/src/api.generated.ts` | Generated TypeScript OpenAPI schema; regenerate only when backend contract is stable. |
| `packages/shared/src/index.ts` | Shared package exports. |
| `deploy/helm/genuinegigs/Chart.yaml` | Helm chart metadata. |
| `deploy/helm/genuinegigs/values.yaml` | Helm defaults; production should use a separate non-secret values file plus Kubernetes Secret references. |
| `deploy/helm/genuinegigs/templates/api.yaml` | API deployment/service. |
| `deploy/helm/genuinegigs/templates/web.yaml` | Web deployment/service. |
| `deploy/helm/genuinegigs/templates/workers.yaml` | Worker/beat deployment. |
| `deploy/helm/genuinegigs/templates/migrate-job.yaml` | Migration job before rollout. |
| `deploy/helm/genuinegigs/templates/configmap.yaml` | Non-secret runtime configuration. |
| `deploy/helm/genuinegigs/templates/ingress.yaml` | HTTP ingress. Must be reviewed for TLS, headers, CORS, rate limiting, and private network requirements. |
| `infra/README.md` | Infrastructure notes. |

---

## 13. Runtime topology and request/data flows

### 13.1 Local service topology

```text
Browser (Next.js :3000)
  -> FastAPI (:8000), session cookie + CSRF token
       -> PostgreSQL / pgvector: durable business, auth, agent, audit state
       -> Redis: Celery broker/backend and rate-limit support
       -> MinIO: quarantine/evidence/document objects
       -> Celery worker: documents, integrations, email, sync, agents
       -> Celery Beat: recovery/follow-up schedules
       -> Mailpit: local simulated email sink
       -> ERP adapter: local simulation by default
```

Compose sequencing is PostgreSQL -> migration -> seed -> API -> worker/beat/web. The API never executes database schema creation/migration on startup. This is correct operationally and must remain so.

### 13.2 Browser write contract

For authenticated mutable operations the intended contract is:

```text
Browser request
  + HttpOnly opaque session cookie
  + x-csrf-token
  + Idempotency-Key
  + If-Match for versioned records
  -> role/membership/scope check
  -> domain transition
  -> audit + transition + response ETag/correlation
```

The server uses `IdempotencyMiddleware` for unsafe requests and version checks on selected mutable records. Not every business record/route has identical optimistic concurrency coverage; this must be audited when extending write paths.

### 13.3 Document ingestion flow

```text
Upload -> filename/MIME/signature/size validation
       -> private quarantine object storage
       -> Document + DocumentJob + audit
       -> Celery job
       -> PDF text / OCR / XLSX extraction
       -> optional Groq structured extraction
       -> QuoteExtractionRun + field evidence + verification records
       -> buyer accepts/corrects/rejects fields
       -> only eligible verified quote can drive comparison
```

Important implementation facts:

- `documents.validate_document_bytes` validates signatures based on extension/content head.
- Object keys include tenant and plant prefixes.
- `DocumentValidationResult`, `QuoteExtractionRun`, and `QuoteFieldVerification` retain processing/evidence state.
- Generated/download links are signed and time limited by settings.
- Do not let document text alter system instructions, role access, or tool availability.

### 13.4 ERP/integration write flow

```text
Approved workflow action
  -> IntegrationOutboxEvent (payload hash, idempotency key, approval state)
  -> explicit approve/dispatch route or worker task
  -> ERPAdapter push call
  -> IntegrationAttempt
  -> IntegrationExternalReference
  -> ReconciliationResult and audit
```

Current adapters:

| Adapter | Current maturity | Write safety |
|---|---|---|
| Local ERP | Full simulated local behavior | Default; no external ERP effect. |
| Oracle Fusion | OAuth client-credential REST path for PO/receipt operations | Writes only if both `ERP_WRITE_MODE=live` and `ERP_LIVE_ENABLED=true`; still needs customer-specific connector acceptance and contract tests. |
| SAP S/4HANA | OData endpoint/contract placeholders | Not a completed live integration. |

Never describe a local simulation or outbox creation as a completed customer ERP post. The UI/agent should distinguish: drafted -> approved for dispatch -> dispatched -> external acknowledgement/reconciled -> failed/retryable.

### 13.5 LLM/provider flow

`provider_response` in `agent_service.py` uses LangChain Groq models, normally configured as:

- primary: `openai/gpt-oss-120b`
- fast/routing: `llama-3.1-8b-instant`

The model receives a compact server-generated context and only role-authorized tool schemas. It does not receive database credentials, generic SQL, shell, raw unrestricted HTTP, or ERP credentials. With no Groq key in Compose, deterministic fallback can preserve demo/manual flow. Production should default `AGENT_ALLOW_DETERMINISTIC_FALLBACK=false` unless that degraded behavior has been explicitly accepted and tested.

### 13.6 Current versus intended agent loop

| Concern | Current live `run_message` | Intended architecture | Existing building block |
|---|---|---|---|
| Model decisions | One native-tool/capability selection per message | Multi-step bounded read/observe/decide loop | `agent_runtime.run_bounded_tool_loop` |
| Record resolution | Deterministic parse and ad hoc adapter resolution | Dedicated typed resolution tools | `agent_resolution.py` |
| State | JSON dict mutations in several handlers | One schema-versioned merge/write path | `agent_state.py`, `AgentThreadStateV2` |
| Mutation proof | `AgentActionReceipt` in important adapters | Required for every mutation | `ToolResult` validator + receipts |
| Controlled actions | Proposals/confirm/reject routes | Same, stop loop on proposal | `AgentProposal` and `confirm_proposal` |
| Response | Deterministic blocks plus optional Groq narration | Grounded summarizer from compact observations | `compose_grounded_answer`, response validator |

This table is the key architectural planning context. Do not assume files merely existing means they are wired into production execution.

---

## 14. Data model and lifecycle reference

All operational records inherit or carry tenant/plant scope. `ScopedMixin` and `workflows.user_scope_query` are fundamental isolation primitives; every new query must use equivalent scope enforcement.

### 14.1 Identity, organization and feature control

| Models | Purpose |
|---|---|
| `Tenant`, `Company`, `Plant`, `Department` | Customer/workspace organizational hierarchy. |
| `Account` | Global authentication identity: email, password/MFA-related state. |
| `User` | Tenant/plant operational user record. |
| `WorkspaceMembership`, `UserPlantAccess`, `ReportingLine` | Selected workspace role, plants and hierarchy authorization. |
| `WorkspaceInvitation`, `IdentityToken`, `AuthSession`, `LoginAttempt` | Invitation, verification/reset/MFA/session and lockout lifecycle. |
| `RoleDefinition`, `TenantFeatureFlag`, `BusinessNumberSequence` | Role/capability configuration, per-tenant gates, and business-number counters. |

### 14.2 Agent and coordination models

| Models | Purpose |
|---|---|
| `AgentProfile` | Role agent configuration, budgets, allowed/blocked actions, provider/model, enabled state, policy/prompt versions. |
| `Task` | Canonical work coordination record: owner, entity link, status, due date, priority, delegation/objective parent, follow-up and escalation fields. |
| `Objective` | Legacy/transitionary goal model; objective creation route is intended to be retired/returns 410 in the role-agent design. Audit usage before removal. |
| `AgentThread`, `AgentMessage` | Private/thread-scoped conversations and typed response blocks/citations. |
| `AgentRun`, `AgentEvent`, `AgentCheckpoint`, `AgentToolCall` | Run metadata, durable activity, resumable state snapshots, tool audit. |
| `AgentProposal`, `AgentActionReceipt` | Controlled-action confirmation and successful mutation evidence. |
| `AgentDelegation` | Structured manager-to-recipient agent/human work packet and response. |
| `AgentMemory`, `KnowledgeDocument`, `KnowledgeChunk`, `AgentFeedback` | Persistent agent memory/approved knowledge/feedback. |
| `Notification`, `AuditEvent` | User alerts and immutable-ish product traceability. |

### 14.3 Master data and procurement models

| Models | Purpose |
|---|---|
| `Supplier`, `SupplierSite`, `SupplierContact`, `SupplierItemCapability` | Supplier master, contacts/sites, approved material capabilities. |
| `Uom`, `Item`, `ItemSpecification`, `TaxPolicy`, `MaterialMasterRequest` | Material and procurement master data. A master-request approval adds a material; it does not automatically create a requirement. |
| `PurchaseRequirement`, `PurchaseRequirementLine` | Demand/requisition record and lines. |
| `RFQ`, `RFQLine`, `RFQSupplierInvitation` | Supplier enquiry, immutable finalization, line detail and invitation status. |
| `SupplierQuote`, `QuoteLine`, `QuoteExtractionRun`, `QuoteFieldVerification` | Supplier commercial response, extraction and verification. |
| `BidComparison`, `ComparisonApprovalRequest` | Comparison version/recommendation and named approvals. |
| `NegotiationRound`, `NegotiationMessage` | Optional commercial negotiation lifecycle. |
| `AwardDecision`, `AwardLine` | Selected supplier decision. |
| `PODraft`, `PODraftLine`, `SupplierAcknowledgement` | PO preparation/approval and supplier acknowledgement. |

### 14.4 Inbound, evidence, integration and governance models

| Models | Purpose |
|---|---|
| `ASN`, `GateEntry`, `StoreReceipt`, `InspectionResult`, `InventoryImpact` | Dependent inbound physical/quality records. |
| `Document`, `GeneratedArtifact`, `DocumentJob`, `DocumentValidationResult` | Original evidence, final/draft documents, work and validation. |
| `WorkflowTransition`, `ApprovalDecision` | Domain lifecycle and decision history. |
| `SupplierPortalToken` | Hashed supplier portal token, expiry/purpose/entity. |
| `OutboxMessage` | Supplier/email operational outbox, separate from ERP integration outbox. |
| `IntegrationConnection`, `IntegrationSyncJob`, `IntegrationExternalReference`, `IntegrationOutboxEvent`, `IntegrationAttempt`, `ReconciliationResult` | ERP connector config, read syncs, external identity mapping, write dispatch/attempt/reconciliation. |
| `IdempotencyRecord` | HTTP request replay protection. |

### 14.5 Procurement statuses and critical rules

The exact allowable transitions live in `domains/state_machine.py`; update it before inventing a new status in UI code. High-level intended rules:

- Requirement is created against an approved scoped item and assigned to an active Purchase Executive.
- RFQ `draft` can be edited; `published` is immutable. Published RFQs have final artifact/invitations/outbox state.
- Quote extraction is candidate evidence. Quote values become usable only after verification policy is satisfied.
- Comparison uses verified eligible quotes; submitting freezes a version and makes named approval requests.
- PO confirmation requires the required approval state and creates controlled external action preparation; it is not proof of supplier delivery or ERP posting.
- Store receipt follows gate/PO constraints; inspection follows receipt; inventory impact follows inspection disposition.
- Every externally consequential transition should create audit and a durable outbox/attempt trail.

---

## 15. HTTP API map

This is a functional route map, not a substitute for generated OpenAPI. Use `GET /openapi.json`, `packages/shared/src/api.generated.ts`, and the request schema files for exact payloads.

### 15.1 Auth, identity and workspace

| Route group | Operations |
|---|---|
| `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/csrf` | Session start/end/current user/CSRF retrieval. |
| `/auth/sessions/*` | List/revoke active sessions. |
| `/auth/mfa/*` | Enroll, confirm, disable MFA. |
| `/auth/password-reset/*` | Password recovery request/confirmation. |
| `/workspace/invitations/*`, `/workspace/setup`, `/workspace/invitations/accept` | Invite/onboard users and bootstrap workspace. |
| `/workspaces`, `/workspaces/select` | Create/list/select fresh/demo workspace memberships. |
| `/org/users`, `/org/agents`, `/org/roles`, `/org/plants`, `/org/departments`, `/org/plant-access` | Organization/role/agent configuration. |
| `/admin/workspace/agent-policy`, `/admin/agents/*`, `/admin/reset-workspace` | Tenant/profile agent policy, emergency stop, demo reset. |

### 15.2 Overview, tasks, cases and audit

| Route group | Operations |
|---|---|
| `/workspace/overview`, `/workspace/home` | Main shell content, navigation, metrics, work items, badges. |
| `/workspace/work-items/{id}/context` | Selected task/work-item context. |
| `/procurement/control-tower`, `/procurement/cycles*`, `/procurement/active-cycle` | Process monitoring/cycle view. |
| `/tasks`, `/tasks/team`, `/tasks/{id}`, `/tasks/{id}/transition`, `/tasks/{id}/request-update` | Task list, hierarchy-safe team visibility, lifecycle and follow-ups. |
| `/cases`, `/cases/{id}/close` | Exception cases. |
| `/audit` | Role-controlled audit view. |
| `/notifications*` | Notification listing/read/read-all. |

### 15.3 Procurement and supplier master

| Route group | Operations |
|---|---|
| `/procurement/suppliers`, `/procurement/items`, `/procurement/assignees` | Supplier/master data and active assignees. |
| `/procurement/material-requests*` | Request/decision for absent material master. |
| `/procurement/requirements*` | Requirement listing/detail/create. |
| `/procurement/requirements/{id}/rfqs` | Idempotent RFQ draft creation from requirement. |
| `/procurement/rfqs*` | List/detail/update, draft preview, artifact list, publication. |
| `/procurement/quotes*`, `/supplier/rfqs/{token}/quotes*` | Buyer/supplier quote upload/receipt/detail/verification. |
| `/procurement/comparisons*`, `/procurement/comparison-records*` | Legacy/V2 comparison generation, preview/artifacts, submit/decision/PO confirmation. |
| `/procurement/awards*` | Create/approve/reject supplier award. |
| `/procurement/negotiations*` | Create/submit/approve/counter/accept negotiation. |
| `/procurement/po-drafts*` | List/detail/create/preview/artifacts/email/approve PO. |

### 15.4 Inbound, documents and integrations

| Route group | Operations |
|---|---|
| `/inbound/asns`, `/inbound/gate-entries`, `/inbound/receipts`, `/inbound/inspections`, `/inbound/inventory-impact`, `/inbound/acknowledgements` | Inbound logistics and quality actions/listing. |
| `/supplier/pos/{token}/acknowledgements` | Supplier portal acknowledgement. |
| `/documents/*` | Upload/list/detail/validation/download URL/content/reprocess. |
| `/integrations/outbox*`, `/integrations/email/*` | ERP/email outbox visibility/approval/dispatch/retry/send. |
| `/integrations/imports/*`, `/integrations/sync-jobs*`, `/integrations/connections*`, `/integrations/reconciliation` | Data imports, connector testing/config, sync and reconciliation. |

### 15.5 Agent routes

| Route group | Operations |
|---|---|
| `/agent/home` | Agent-specific home/work/register. |
| `/agent/threads*` | Create/list/detail/context/message posting. |
| `/agent/runs/{id}`, `/events`, `/activity`, `/cancel`, `/feedback` | Run inspection, activity, cancellation, feedback. |
| `/agent/proposals*` | List/create/confirm/reject controlled actions. |
| `/agent/delegations*`, `/agent/team-status` | Structured delegation and formal team status. |
| `/agent/knowledge*` | Approved knowledge lifecycle. |
| `/objectives*` | Legacy objective surface; planning should decide whether to fully retire it. |

### 15.6 Compatibility warning

The API includes V1, V2, and compatibility endpoints. Do not add a third parallel path. Before changing a route, identify which UI, test, worker, and generated-contract client use it. Prefer a canonical V2 service behind stable aliases during migration.

---

## 16. Frontend architecture and UX debt

### 16.1 Current composition

Each page route passes a screen key to `IndustrialConsole`. `IndustrialConsole` handles authentication, CSRF/data fetch, workspace switching, role navigation, generic page layout, record loading, action posting and screen-specific composition. It delegates workflow forms to `WorkflowForms.tsx` and mounts `AgentDrawer` in the shell.

This delivers functionality quickly but creates two major costs:

1. The component is a data/controller/UI monolith. A change to a simple screen risks shell behavior.
2. Generic tables and raw record objects leak implementation fields and produce an unpolished console.

### 16.2 UI target

The intended product is an industrial operations workspace like the provided `ui.png` reference:

- dark, restrained left navigation with meaningful grouped workflow entries;
- calm light work surface with strong hierarchy;
- four concise status cards above real work;
- business cards/tables with owner, date, material/supplier and decision context;
- an always-available but non-intrusive role assistant;
- clear status colors used sparingly: critical red, action amber, healthy green, information blue/purple;
- generous but compact spacing, consistent 8px scale, 44px action controls, controlled typography;
- mobile navigation and full-height assistant without overflow.

### 16.3 Required frontend refactor boundaries

Split `IndustrialConsole.tsx` into:

```text
app shell / navigation / workspace switcher
workspace data hooks + query cache
My Work dashboard
record-list components
record-detail/workbench components
shared status/action/confirmation components
screen route adapters
```

Split `WorkflowForms.tsx` into domain modules:

```text
requirements and material master
RFQ preparation/review/send
quote upload and evidence verification
comparison and approvals
PO and supplier communication
inbound and quality
integrations/admin/workspace setup
```

Do not do this as a visual-only refactor. First introduce tests for each public behavior and keep all mutations routed through the same backend service.

### 16.4 Design system requirements

- Establish CSS variables for background, surface, text, muted text, border, accent, success, warning, critical, focus ring, radius, shadow, and spacing.
- Use one font stack deliberately. Do not claim proprietary visual identity until licensing and typography are set.
- Use semantic components: `StatusBadge`, `RecordIdentity`, `WorkflowStepper`, `PrimaryAction`, `SecondaryAction`, `ConsequenceDialog`, `EmptyState`, `ErrorState`, `LoadingState`, `EvidenceField`, `AgentCard`.
- Avoid raw technical labels such as `artifact`, `outbox`, `run`, `receipt`, `version`, UUIDs and serialized JSON in normal user surfaces.
- Make each mutation refresh data, badges, notification count and linked assistant context.
- Provide role-aware empty states rather than empty generic grids.
- Add keyboard order, visible focus, dialog focus trap, labels, error association, live status announcements, contrast and reduced-motion testing.

### 16.5 Manual workflow wording map

See Section 4 for RFQ. Apply the same business vocabulary elsewhere:

| Internal/system term | User-facing wording |
|---|---|
| Material master request | Request new material |
| Requirement | Material requirement |
| RFQ draft | Supplier request draft |
| RFQ publish | Send to suppliers |
| Quote extraction verification | Review extracted supplier quotation |
| Generate comparison | Compare verified quotations |
| Submit comparison | Send recommendation for approval |
| Award decision | Approve supplier selection |
| PO draft | Purchase order draft |
| Supplier email outbox | Supplier delivery status |
| ERP outbox | ERP synchronization status |
| Reconciliation | Check ERP synchronization |
| Artifact preview | Review document |

---

## 17. Security, privacy and ERP trust dossier

This is the material needed to answer customer due-diligence questions honestly. It separates implemented controls from work still required.

### 17.1 Implemented or code-evidenced controls

| Control | Code evidence | Caveat |
|---|---|---|
| Password hashing | Argon2 functions in `core/security.py` | Requires appropriate production password/MFA policy and external review. |
| Opaque sessions | Session hash persisted, cookie session ID only | Configure secure cookies/TLS in production. |
| CSRF protection | `csrf_guard` / `require_csrf` on unsafe authenticated routes | Audit every newly added mutable route. |
| Login throttling/lockout | Redis plus `LoginAttempt` records | Tune and test in production topology. |
| Tenant/plant scoping | `ScopedMixin`, scope queries, membership checks | Direct query bypasses must be reviewed. |
| Role authorization | `require_role`, `require_read_role`, capability registry | UI hiding is not security; server check is mandatory. |
| Idempotent HTTP writes | `IdempotencyMiddleware`, `IdempotencyRecord` | Semantic business/external idempotency needs adapter-specific tests. |
| Stale-write protection | ETag/`If-Match`/412 on selected versioned records | Coverage is not uniform across all write endpoints. |
| Audit/correlation | Audit events, workflow transitions, integration attempts, agent events | Define tamper resistance, retention and export policy. |
| Private objects | MinIO quarantine/evidence buckets and signed downloads | Production needs encryption, IAM, lifecycle and monitoring configuration. |
| Agent boundaries | Role capability registry, receipts, proposals, thread scope | Live runtime still contains legacy paths and needs comprehensive adversarial tests. |
| ERP live kill switch | `ERP_WRITE_MODE`, `ERP_LIVE_ENABLED` | Not a substitute for least-privilege service accounts and integration staging. |
| Agent kill switch | `AGENT_ENABLED`, tenant/profile policies/emergency stop | Verify cancellation/recovery behavior under load. |

### 17.2 Controls not proven by this repository

Do not claim any of the following without separate evidence:

- SOC 2, ISO 27001, GDPR/DPDP compliance, penetration-test results, or formal certification.
- Encryption at rest/in transit in the customer’s actual hosting environment.
- Key management, SIEM, WAF, DLP, backup/PITR, DR RTO/RPO, network segmentation, SSO/SCIM, or customer-managed keys.
- No model/provider retention or training. Groq/provider contractual terms and actual payload policy must be verified.
- Full Oracle or SAP production certification; SAP is contract-only in code.
- Universal rollback for ERP effects; some ERP operations need compensating transactions rather than rollback.

### 17.3 Safe customer deployment model

```text
Customer ERP
  <- read-only dedicated service account for approved imports
  -> separate least-privilege write account for approved actions only
  -> private network/VPN/allowlist where required

GenuineGigs integration service
  -> encrypted secret reference, never exposed to browser/model
  -> validation/staging/outbox/idempotency/version checks
  -> explicit customer-approved dispatch
  -> external reference + reconciliation + alerting
```

Recommended rollout sequence:

1. Start read-only: master data, suppliers, items, open PO/status imports.
2. Validate mappings in a sandbox against real customer cases.
3. Run shadow mode: create GenuineGigs proposals/outbox events but do not dispatch.
4. Enable one low-risk, approval-gated write flow in a limited plant/business unit.
5. Reconcile each write and review exceptions daily.
6. Expand only after acceptance criteria and incident procedures are proven.

### 17.4 LLM privacy policy design

- Send minimum required context; do not send ERP credentials, unrelated finance/payroll/customer data, or whole documents when a relevant extracted subset is enough.
- Maintain a data classification policy and redaction layer before provider calls.
- Record provider, model, prompt/policy version, data category and retention policy—not raw unrestricted chain-of-thought.
- Offer a deployment choice for sensitive customers: provider enterprise agreement, private/self-hosted model, or agent-disabled/manual workflow mode.
- Contractually document subprocessors, regions, retention, deletion, incident notification and DPA terms.
- Ensure agent trace export remains disabled unless a redacted approved destination is configured.

---

## 18. Test, evaluation and operations matrix

### 18.1 Existing test assets

| Location | Coverage intent |
|---|---|
| `apps/api/tests/conftest.py` | Test database and fixtures. |
| `test_agent_intent_runtime.py` | Intent/runtime behavior. |
| `test_agent_contract.py` | Agent contract/regression expectations. |
| `test_role_agents.py` | Role agent/membership/delegation behavior. |
| `test_control_tower.py` | Overview/control-tower workflow behavior. |
| `test_erp_contracts.py` | ERP adapter/contract behavior. |
| `test_production_contracts.py` | Production safety/configuration contracts. |
| `tests/agent_eval/live_groq_scorecard.py` | Optional scored live Groq evaluation. |
| `apps/web/e2e/role-workflows.spec.ts` | Browser role workflow test. |
| `apps/web/e2e/client-demo-screenshots.spec.ts` | Screenshot/demo flow regression. |

### 18.2 Mandatory future test additions

**Agent behavior**

- Exact transcript regressions: material requirements, ALU/ALI code variants, relative dates, missing material request, pending/approved/rejected continuation, “its ID,” topic changes, latest requirement, exact RFQ business number.
- Tool-policy tests: unknown, unauthorized, malformed or forged tool/entity IDs fail closed.
- Multi-step runtime tests: resolver observation -> canonical mutation; one mutation maximum; proposal stops loop; budgets terminate safely.
- Grounded response tests: no success language without matching receipt; no raw operational dump; no false future promise.
- Provider-outage tests: degraded mode only when enabled and context is unambiguous.
- Agent-to-agent/reporting hierarchy isolation, delegation depth and cycle tests.

**Workflow/integration**

- Task semantic idempotency and duplicate reconciliation.
- All state-machine invalid transitions return expected 409 and do not alter business state.
- Concurrent `If-Match` and duplicate idempotency-key tests.
- Outbox retry/timeout/duplicate dispatch/external reference/reconciliation tests.
- Oracle payload contract tests with mocked provider; no live calls in CI.
- Cross-tenant, cross-plant, cross-role and document-download isolation tests.
- Document bomb/invalid MIME/signature/OCR timeout/prompt-injection style content tests.

**Frontend**

- RFQ wizard state transitions, wording, autosave/error retention, send consequence confirmation, sent/delivery states.
- Assistant responsive drawer, attachments, proposal controls, recovery after errors, role-aware suggestions.
- Above-fold My Work, navigation/badges/workspace switcher, keyboard/focus, contrast/axe, mobile overflow.
- Screenshot tests at 1440×900, 1280×800, 1024×768, 768×1024 and 390×844.

### 18.3 Standard verification commands

```bash
npm run typecheck
npm run build:web
npm run check:api-contract
npm run test:api
npm run test:e2e
docker compose up --build
```

Before a release also run Alembic upgrade on a production-like backup copy, readiness checks, migration rollback/forward test where supported, dependency/vulnerability scan, integration mocks, and curated live-provider evaluation with ERP writes disabled.

### 18.4 Operational monitoring

Alert on:

- API health/readiness, migration mismatch, database/Redis/object-storage failure.
- Agent provider timeouts, malformed outputs, policy denials, tool errors, token/budget exhaustion and queue age.
- Stuck document jobs, extraction failures, verification backlog.
- Outbox retries, dead letters, ERP reconciliation mismatches and supplier delivery failures.
- Authentication anomalies, lockout spikes, CSRF/idempotency failures, cross-scope denial spikes.
- Task/delegation overdue counts, circular escalation attempts and notification delivery failure.

---

## 19. Configuration and deployment reference

### 19.1 Important environment settings

| Group | Settings |
|---|---|
| Runtime | `APP_ENV`, `DATABASE_URL`, `REDIS_URL`, `LOG_LEVEL`, `WEB_BASE_URL`, `ALLOWED_ORIGINS` |
| Security | `SESSION_SECRET`, `SESSION_TTL_SECONDS`, `COOKIE_SAMESITE`, `SECURE_COOKIES` |
| Storage | object storage endpoint/bucket/quarantine/evidence/region/secure/access/secret fields |
| Agent/provider | `AI_PROVIDER`, `AGENT_ENABLED`, `GROQ_API_KEY`, primary/fast model, budgets, time/graph/tool/mutation/proposal/candidate/task limits, fallback flag, trace policy |
| Documents | upload limits, parser/OCR timeout, download URL TTL |
| Email | `SMTP_MODE`, host/port/user/password/from |
| ERP | provider, write mode, live-enabled flag, Oracle OAuth/base URL/BUs/receipt resource, SAP values, integration timeout |
| Workers | Celery eager mode |

`Settings.validate_runtime_safety()` blocks some unsafe production settings: insecure cookies, weak session secret, wildcard CORS, unenabled ERP live mode, and certain Groq-without-key combinations. It should be expanded with deployment-specific requirements rather than bypassed.

### 19.2 Docker Compose is development/demo infrastructure

- Postgres/MinIO credentials are intentionally visible development values.
- Mailpit is a local email sink.
- Local ERP and SMTP modes are simulated.
- Compose mounts named local volumes; it is not a customer disaster-recovery environment.
- Docker health checks are useful but insufficient for enterprise observability.

### 19.3 Helm deployment position

The Helm chart expects external PostgreSQL, Redis, S3-compatible object storage and Kubernetes Secrets. Before production use, complete TLS/ingress policy, image provenance, secret rotation, non-root/runtime hardening, resource limits, network policies, backups, monitoring, log redaction, and deploy-time schema/health gates.

---

## 20. Known gaps, contradictions and planning risks

This section intentionally states uncomfortable realities so a planning model does not produce cosmetic work while missing the product risks.

### 20.1 Agent/runtime gaps

1. `agent_runtime.py` is a clean bounded loop but is not integrated into `run_message`.
2. `agent_state.py`/`AgentThreadStateV2` exist, but live code still directly manipulates JSON state dictionaries in handlers.
3. `agent_service.py` still includes deterministic regex/fact parsing and `AgentTurnDecision`; several capabilities use legacy translation paths.
4. One-shot tool selection can choose a less useful capability (`list_my_tasks`) instead of resolving a business object and executing the requested workflow.
5. Capability registry required fields are metadata, not a universally enforced adapter schema contract.
6. Some capability IDs may still reach the “not implemented yet” terminal branch; add registry-to-adapter completeness tests.
7. `compose_grounded_answer` may rewrite otherwise good deterministic output; maintain strict receipt-grounding and test exact user-facing language.
8. `AgentResponseBlock` supports many historical types; normalize the frontend contract and hide stale headings/internal wording.
9. Formal delegation exists, but true employee-agent autonomous progress/update behavior needs a clear, bounded trigger and human ownership design.

### 20.2 Workflow/data gaps

1. V1/manual and V2 procurement paths coexist. Define canonical ownership per lifecycle stage and migrate callers deliberately.
2. Task creation uses generic repeated titles; business context must be visible and task creation must be semantically idempotent.
3. Requirement/RFQ service behavior includes compatibility fallbacks; establish data quality/migration plan before removing them.
4. Supplier capability/master data quality determines RFQ success. Fresh-workspace onboarding must make this obvious.
5. Comparison/award/PO state needs clear status vocabulary and a single UI entry point per irreversible action.
6. ERP connection objects and adapters are not a substitute for customer-specific mapping/acceptance/reconciliation playbooks.
7. SAP is not implemented as a live writer; Oracle code still requires contract, security and operational validation.

### 20.3 UI gaps

1. `IndustrialConsole.tsx` and `WorkflowForms.tsx` are overgrown. They make high-fidelity, maintainable UI difficult.
2. Generic tables expose raw implementation concepts and cannot meet a client-facing polish bar.
3. Workflow actions are duplicated across panels and generic next-action queues.
4. There is no unified design system or workflow stepper abstraction.
5. Page context, selected record and assistant context are not consistently synchronized.
6. Loading, empty, offline, permission, validation and recoverable-error states need design-level treatment.
7. Responsive requirements, accessibility, keyboard interaction and visual regression coverage need systematic enforcement.

### 20.4 Security/enterprise gaps

1. Code evidence is not a security certification.
2. No evidence in repo of SSO/SAML/SCIM, formal RBAC review tooling, SIEM, customer-managed keys, DLP, WAF, external pentest, DR test, or compliance program.
3. Groq data flow/privacy terms must be resolved before customer claims; do not hide external model processing.
4. Document anti-malware scanning, content classification, retention/deletion enforcement and audit immutability need a production assessment.
5. Live ERP credential provisioning, rotation, per-customer account design, network connectivity, mapping validation and disaster procedures require a dedicated integration program.

---

## 21. Recommended future planning order

The product should not attempt every roadmap item at once. The following ordering protects customer demos while reducing architectural debt.

### Milestone A — Demo reliability and client-facing clarity

- Fix/lock exact agent conversations and task display behavior.
- RFQ wizard: Prepare -> Suppliers -> Review -> Send, with business wording and one primary action.
- Remove raw/internal UI output and duplicate publish controls.
- Seed idempotency, task reconciliation and accurate demo master data.
- Add screenshot and transcript regressions.

### Milestone B — Live agent runtime foundation

- Integrate `agent_runtime.run_bounded_tool_loop` behind a feature flag.
- Convert all capabilities to a typed adapter map returning `ToolResult`.
- Integrate `AgentThreadStateV2` as the only write path for state.
- Add first-class read/resolution tools and bounded observations.
- Retire legacy decision routing capability by capability with equivalence tests.

### Milestone C — Work graph and agent-to-agent differentiation

- Make Task the single coordination primitive with visible entity context and semantic idempotency.
- Implement governed progress requests/employee responses with notifications, escalation, timestamps and reporting-tree enforcement.
- Build manager status from factual tasks/delegations/records, never private conversations.
- Add “why this is blocked / what happens next” workflow explanation cards.

### Milestone D — Workflow and integration hardening

- Consolidate V1/V2 service ownership.
- Complete evidence/verification/comparison/approval/PO manual and assistant equivalence.
- Build sandbox/shadow/reconciliation tooling for Oracle; decide SAP product scope honestly.
- Establish integration health, outbox operator experience and recovery playbooks.

### Milestone E — Enterprise trust readiness

- Threat model, data-flow inventory, privacy/subprocessor policy, access-review model.
- Secret manager, private connectivity, least-privilege service accounts, audit export, monitoring/alerting, backups and recovery test.
- External penetration test and compliance roadmap appropriate to target market.
- Customer-specific ERP connector certification/acceptance pack.

### Milestone F — Product scale and maintainability

- Frontend component/data-layer refactor and design system.
- API router/service/repository modularization.
- Generated API client adoption.
- Evaluation datasets, prompt/model rollout controls, analytics and performance/cost monitoring.

---

## 22. Instructions for a future planning LLM

Use this dossier as context, but follow these rules when producing a plan:

1. Treat checked-in code as more current than historic plan files or architecture prose.
2. Do not claim the bounded ReAct runtime is live merely because `agent_runtime.py` exists.
3. Preserve human approval boundaries, receipts, tenant/plant scope, idempotency, audit and ERP safe defaults.
4. Do not replace canonical procurement services with direct model/database mutation.
5. Do not make a visual redesign that breaks manual workflow routes or hides operational consequences.
6. Do not market unverified security/compliance/ERP capabilities.
7. Make each change testable with a regression that captures the actual user complaint.
8. Plan data migrations, OpenAPI/type regeneration, idempotency, concurrency and rollout/rollback before changing persisted contracts.
9. Prefer a vertical slice: one complete user outcome across UI, assistant, service, audit, test and monitoring—rather than broad but disconnected scaffolding.
10. Explicitly identify where user/customer/security-owner decisions are required instead of assuming authority.

The desired outcome is a trustworthy operations product: conversational and agentic where it helps people work, deterministic and governed where it protects money, ERP records, privacy, inventory and customer trust.
# PLAN(3) implementation completion — 2026-07-18

The patch-first runtime upgrade is implemented through migration `0012_agent_runtime_contract`. It adds typed V2 thread state, deterministic business/material/assignee resolution, a bounded LangGraph read-loop with a single mutation or controlled proposal, direct adapters into the canonical procurement and inbound services, semantic task/notification idempotency, runtime metrics, and governed confirmation receipts. The RFQ workbench is now a state-driven review/send flow with one canonical consequence control; responsive role workbenches and the contextual drawer pass desktop, tablet, mobile, and critical accessibility checks.

Verification at handoff: API `163 passed`; deterministic agent evaluation `100 passed`; Playwright `40 passed, 2 intentionally skipped` (the screenshot capture runs once on desktop); OpenAPI hash `d2f69aff7802`; migration head `0012_agent_runtime_contract`; web typecheck and production build pass. Live Groq evaluation was not run because credentials are unavailable. Docker Compose verification remains unavailable because Docker Desktop WSL integration is not enabled in this environment.
