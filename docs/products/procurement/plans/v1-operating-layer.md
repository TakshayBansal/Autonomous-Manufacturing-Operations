# GenuineGigs Agentic Manufacturing Operating Layer — Full Product and Repository Upgrade Plan

> **Document type:** Codex execution contract
> **Primary source of truth:** latest `HANDOFF2(1).md`, then the current repository
> **Target:** convert the existing governed procurement application from a brittle one-shot command router into a reliable, assistant-first, hierarchy-aware manufacturing operations platform
> **Execution mode:** patch-first, phase-gated, no repository rewrite
> **Scope:** complete procurement and inbound workflows as the first production-quality vertical; build reusable agent/runtime foundations for later production, maintenance, stores, and quality expansion

---

# 0. Mandate

The product must stop behaving like:

```text
ERP screens + a deterministic chatbot that recognizes a few commands
```

It must behave like:

```text
A role-specific manufacturing assistant that understands ordinary language,
resolves the correct records, uses authorized tools across multiple observations,
prepares real work through canonical services, remembers results, coordinates
people through the plant hierarchy, and presents one clear next action.
```

The existing FastAPI procurement services, role authority, audit trail, immutable documents, private storage, tasks, proposals, receipts, tenant isolation, and manual fallback are valuable and must remain authoritative.

The main architectural change is the agent orchestration layer. The main product change is the information architecture and manual workflow presentation.

This plan is complete only when users can work naturally without learning internal lifecycle verbs, opening a task before every request, repeating known facts, or interpreting raw database/task output.

---

# 1. Definition of success

## 1.1 End-user success

A user must be able to say any reasonable paraphrase of the following in a normal personal assistant thread:

```text
Create a requirement for 100 KG Aluminium Ingot needed next month.
Prepare the supplier request for the latest requirement.
Generate the RFQ for REQ-2026-0033.
Upload these three quotations and compare them.
Why did you recommend Bharat Metals?
Send the recommendation for approval.
What is blocking this purchase?
Ask Meera for an update and remind me when she responds.
Show me everything that needs my decision today.
```

The assistant must:

1. understand the goal without exact prompt matching;
2. reuse already supplied facts;
3. resolve exact and relative record references;
4. use multiple read tools when required;
5. execute at most one business mutation per turn;
6. call the same canonical services as the manual UI;
7. return persisted business IDs and artifacts immediately;
8. separate draft preparation from controlled external consequences;
9. offer only actions that the current role is authorized to perform;
10. never claim success without a persisted receipt;
11. never dump raw task arrays, JSON, UUIDs, or runtime internals;
12. remember the created/selected record for follow-up questions;
13. remain useful when Groq is unavailable by providing manual navigation and safe deterministic continuation for unambiguous operations.

## 1.2 Manual product success

For every workflow state, the manual interface must show:

- the selected business record and context;
- current state in plain business language;
- blockers and who owns them;
- one visually dominant next action;
- secondary review/download/history actions in a non-competing location;
- the same result that an assistant action would create.

Users must not need to understand terms such as:

- artifact;
- outbox;
- checkpoint;
- run;
- tool call;
- receipt;
- entity;
- record version;
- publish versus dispatch implementation details.

These concepts remain in backend/audit/admin surfaces only.

## 1.3 Business success

The product must visibly create measurable customer value:

- shorter requirement-to-RFQ time;
- faster quotation extraction and comparison preparation;
- fewer missing commercial fields;
- fewer overdue internal actions;
- fewer manager follow-up calls/messages;
- faster approvals;
- traceable supplier and quality decisions;
- complete evidence and audit history;
- assistant-prepared work that is accepted with minimal correction.

## 1.4 Engineering success

The release must achieve:

- no new parallel procurement data model;
- no direct LLM writes to business tables;
- no loss of current manual functionality;
- no weakened authorization or tenant/plant scope;
- deterministic authorization and calculations;
- bounded LLM execution;
- typed tools and typed results;
- exact transcript regression tests;
- scenario-based live-model evaluation;
- complete API, frontend, Playwright, and build verification.

---

# 2. Codex operating contract

## 2.1 Read order

Before editing:

```powershell
git status --short
git diff --check
docker compose ps -a
```

Then read, in this order:

1. latest `HANDOFF2(1).md` or the renamed authoritative handoff;
2. this `PLAN.md` completely;
3. only the exact files listed in Section 22 before broad search;
4. existing tests around the affected service before editing it.

Do not begin by recursively reading the entire repository.

## 2.2 Patch-first rules

Codex must:

- preserve the dirty worktree;
- make targeted edits;
- reuse canonical services;
- reuse current data models where possible;
- add the minimum necessary migration;
- preserve generated OpenAPI workflow;
- run tests after each phase;
- fix failures before moving forward;
- continue through all phases unless blocked by missing credentials or an unrecoverable environment problem.

Codex must not:

- rewrite the repository;
- replace FastAPI, Next.js, SQLAlchemy, LangGraph, PostgreSQL, Redis, MinIO, or Celery;
- add CrewAI, AutoGen, a second agent SDK, or an unrestricted autonomous framework;
- create `/v2` replacement pages for existing workflows;
- create another requirement/objective model;
- introduce an agent-only copy of RFQ/comparison/PO records;
- expose shell, arbitrary SQL, unrestricted HTTP, or raw database access to the model;
- weaken confirmations for commercial, financial, inventory, quality, or external actions;
- remove existing tests to obtain a passing result;
- report a test as passed unless it was actually run;
- leave placeholders, TODO-only adapters, mock success cards, or “will provide shortly” responses.

## 2.3 Decision rule

Where this plan specifies a data structure, endpoint, adapter, UI component, label, or test, implement it as written unless the current repository has an equivalent reusable structure.

If an equivalent exists:

1. reuse it;
2. adapt naming at the boundary;
3. document the equivalence in the final report;
4. do not create a duplicate.

If repository reality conflicts with the plan, preserve the business invariants and choose the smallest compatible implementation. Record the conflict in the final report.

---

# 3. Product architecture

## 3.1 Positioning

GenuineGigs is not intended to replace an ERP ledger. It is an agentic manufacturing operations layer that can sit above an existing ERP, MES, QMS, WMS, document store, and email system.

Use this architectural distinction throughout the UI and documentation:

```text
Existing ERP / MES / QMS / WMS
    = system of record

GenuineGigs
    = system of work, coordination, preparation, explanation, and governed action
```

The current internal procurement records can remain the development/demo system of record. Integration adapters later synchronize with external ERPs.

## 3.2 Core product primitives

The platform revolves around five primitives:

1. **Business records** — requirement, RFQ, quote, comparison, approval, PO, receipt, inspection.
2. **Tasks** — outcome, owner, due date, blocker, expected output, linked record.
3. **Role assistants** — one assistant per workspace membership, with role-scoped tools.
4. **Governed actions** — direct low-risk actions or controlled proposals requiring human confirmation.
5. **Evidence** — source documents, calculations, citations, artifacts, audit events, receipts.

Chat is an interface to these primitives, not a separate process.

## 3.3 Human and agent hierarchy

Each `WorkspaceMembership` has one role assistant profile.

The reporting hierarchy must be reflected by structured permissions and task/delegation relationships:

```text
Plant Manager + Plant Manager Agent
    ├── Purchase Manager + Purchase Manager Agent
    │       └── Purchase Executive + Purchase Executive Agent
    ├── Gate Operator + Gate Agent
    ├── Store Manager + Store Agent
    ├── Quality Inspector + Quality Agent
    └── Admin + Admin Agent
```

Rules:

- an assistant acts only with its human membership’s permissions;
- assistants do not own independent commercial authority;
- managers may delegate to authorized descendants;
- peers cannot assign peers unless an explicit policy grants it;
- agent-to-agent communication is persisted task/delegation activity, not hidden roleplay;
- private transcripts are not visible to managers;
- managers see structured work status, blockers, commitments, and authorized evidence.

---

# 4. Current problems to remove

The following are release-blocking defects, not optional enhancements.

## 4.1 One-shot command routing

Current pattern:

```text
one LLM tool selection -> one deterministic dispatcher -> optional narration
```

This prevents the assistant from:

- resolving a record and then acting on it;
- checking workflow state before selecting an action;
- examining attachments and then preparing a comparison;
- recovering from the wrong first tool;
- asking a precise clarification based on a tool observation.

## 4.2 Task-bound execution gates

A valid exact business request must not fail because the conversation was not opened from a task.

Task context is an optional resolution signal, never a mandatory execution prerequisite when an exact authorized entity is supplied.

Remove active paths where:

- `prepare_rfq_draft` ignores `requirement_id`;
- comparison preparation requires a task when an RFQ/comparison reference is known;
- PO preparation requires page/task context when the approved comparison is supplied;
- any direct entity capability is mapped back to a legacy task-only intent.

## 4.3 Inconsistent context memory

Remove ad hoc, handler-specific interpretation of `AgentThread.context_state`.

The assistant must not:

- continue asking about Copper after the user switches to Aluminium;
- forget a need-by date supplied in a prior message;
- forget the record it just created;
- repeat the same clarification after the user supplied the answer;
- let a stale suggestion card override a newer explicit instruction.

## 4.4 Weak entity resolution

The assistant must understand:

- exact business numbers;
- exact internal IDs when supplied;
- material codes and names;
- “latest requirement”;
- “that RFQ”;
- “the comparison you just made”;
- “its ID”;
- selected page record;
- attached quotation context.

## 4.5 Raw output leakage

Normal users must never receive:

- full task arrays;
- raw `count` fields;
- empty `{}` blocks;
- raw UUIDs unless requested;
- internal status enums without a human label;
- run/checkpoint/tool/receipt terminology;
- future promises such as “I’ll provide it shortly” when no asynchronous job exists.

## 4.6 Confusing manual lifecycle controls

Do not present implementation operations as equal peer actions.

Examples to replace:

```text
Generate RFQ / Save RFQ / Preview PDF / Publish RFQ / Download PDF
```

with a state-driven business flow:

```text
Prepare supplier request -> Review -> Send to suppliers -> Track quotations
```

## 4.7 Agent as a secondary widget

The assistant must not look bolted on.

On wide desktop it is a persistent workspace panel. The centre workspace shows assistant-prepared work, decisions, tasks, and blockers. Manual record pages remain available for detailed verification.

---

# 5. Target agent runtime

## 5.1 Keep LangGraph; replace the active graph

Use the existing LangGraph dependency and persistence concepts. Do not add another orchestration framework.

Implement a bounded tool-observation loop using a state graph.

Recommended graph nodes:

```text
START
  -> load_identity_and_policy
  -> load_thread_state
  -> build_compact_context
  -> model_decide
      -> validate_tool_request
      -> execute_read_tool
      -> append_observation
      -> model_decide
      -> validate_tool_request
      -> execute_mutation_tool OR create_controlled_proposal
  -> build_grounded_response
  -> persist_state_and_receipts
END
```

Conditional exits:

- final answer;
- one successful mutation;
- one controlled proposal;
- precise clarification;
- budget exceeded;
- provider failure;
- authorization failure;
- unrecoverable tool failure.

## 5.2 Runtime budgets

Default limits, configurable through existing settings:

```text
maximum model decisions per turn: 6
maximum read/resolution tool calls: 5
maximum business mutations per turn: 1
maximum controlled proposals per turn: 1
maximum attachment summaries: 8
maximum search candidates returned to model: 5
maximum candidates shown to user: 3
maximum task rows shown by default: 5
maximum run wall time: 45 seconds for interactive non-document work
maximum synchronous document wait: 12 seconds
```

Long document extraction must create a real background job and return its actual state. The assistant may say processing is underway only when a persisted job exists and the UI can poll it.

## 5.3 Model responsibility

Groq/LLM is responsible for:

- understanding ordinary user language;
- deciding which authorized read or business tool is needed;
- extracting semantic arguments;
- evaluating compact tool observations;
- deciding whether sufficient information exists;
- producing a concise business explanation from grounded results.

The model is not responsible for:

- authorization;
- tenant/plant scoping;
- workflow-state legality;
- landed-cost calculations;
- supplier eligibility rules;
- persistence;
- idempotency;
- record-number generation;
- document immutability;
- determining whether a mutation succeeded.

## 5.4 One mutation rule

Within one user turn the model may perform multiple reads and resolutions, but at most one business mutation.

Examples:

```text
resolve requirement -> inspect workflow -> create RFQ draft -> stop
```

```text
resolve RFQ -> inspect verified quotes -> generate comparison -> stop
```

```text
resolve comparison -> inspect approval state -> create PO confirmation proposal -> stop
```

It must not create an RFQ and send it externally in the same turn unless the user is confirming an already prepared, exact, controlled proposal and policy explicitly treats that confirmation as the one mutation.

## 5.5 Controlled actions

The following remain proposals requiring explicit human confirmation and fresh revalidation:

- send RFQ to suppliers;
- submit comparison/recommendation for approval;
- approve/reject/request changes;
- create final purchase order;
- send purchase order to supplier;
- approve/dispatch ERP posting;
- record inventory-impacting receipt/inspection disposition where policy requires confirmation;
- close cases with commercial/quality impact;
- external supplier communication outside approved templates;
- destructive/cancellation operations.

Proposal confirmation must revalidate:

- membership and role;
- tenant and plant;
- target entity and version;
- current workflow state;
- expiry;
- idempotency key;
- authority/capability;
- relevant policy flags.

## 5.6 Provider failure

When Groq is unavailable:

- manual workflows remain fully functional;
- exact, unambiguous follow-up reads may use deterministic resolvers;
- exact, low-risk draft preparation may use deterministic continuation only where the capability, entity, and required fields are unambiguous and authorized;
- controlled external actions still require proposals and confirmation;
- do not fabricate a conversational answer;
- return a concise outage notice plus a direct action to the manual workbench.

Do not create a large regex-based replacement chatbot.

---

# 6. Versioned agent state

## 6.1 Replace implicit JSON with a typed schema

Create a Pydantic model such as `AgentThreadStateV2` and serialize it into the existing `context_state` column.

Required shape:

```json
{
  "schema_version": 2,
  "active_goal": {
    "capability": null,
    "status": "idle",
    "started_at": null
  },
  "selected_context": {
    "entity_type": null,
    "entity_id": null,
    "business_number": null,
    "source": null
  },
  "recent_entities": [
    {
      "entity_type": "purchase_requirement",
      "entity_id": "...",
      "business_number": "REQ-2026-0033",
      "label": "Aluminium Ingot · 100 KG",
      "created_or_used_at": "..."
    }
  ],
  "draft_fields": {},
  "candidate_set": [],
  "pending_proposal_id": null,
  "last_receipt": null,
  "attachments": [],
  "blocked_on": null,
  "last_user_correction": null,
  "updated_at": "..."
}
```

## 6.2 State merge rules

Implement centrally, not separately in each adapter.

Rules:

1. Explicit user corrections override older inferred values.
2. A clear topic switch clears incompatible `active_goal`, candidates, blockers, and draft fields.
3. Reusable facts such as plant, role, selected workspace, and explicitly referenced need-by date remain only when semantically applicable.
4. A successful mutation stores the actual entity, business number, and receipt.
5. Recent entities are bounded to 12 and ordered by recency.
6. “It,” “that,” “its ID,” and “the one you created” resolve from recent entities before database search.
7. A pending controlled proposal remains active only until confirmed, rejected, expired, superseded, or contradicted by a newer explicit request.
8. Stale errors must not survive a successful topic change.
9. UI selected context may update `selected_context`, but it may never expand authorization.
10. Attachments persist only as scoped document references and compact metadata, never unbounded extracted text.

## 6.3 State migration

Add a compatibility loader:

- read existing implicit state;
- map known keys into V2;
- discard unknown stale candidate/error keys;
- preserve recent valid entity references and draft facts;
- save as V2 on the next successful turn.

Avoid a table rewrite if JSON migration-on-read is sufficient.

---

# 7. Universal entity resolution

## 7.1 Central resolver service

Create a service module, preferably:

```text
apps/api/app/agent_resolution.py
```

Do not duplicate record-resolution logic inside each capability.

## 7.2 Resolution order

For a business record reference:

1. exact scoped internal ID;
2. exact scoped business number, case-insensitive and punctuation-normalized;
3. selected page/work-item context;
4. recent thread entity reference;
5. safe relative qualifier such as latest eligible/open/assigned;
6. bounded scoped search;
7. at most three user-visible candidates if genuinely ambiguous.

## 7.3 Relative reference rules

### “Latest requirement”

Resolution order:

1. latest recent eligible requirement in thread state;
2. selected requirement context;
3. latest accessible requirement assigned to/created by current membership with no later-stage incompatible state;
4. latest accessible approved requirement without an RFQ for RFQ-preparation requests;
5. ask one bounded clarification only when two records are materially tied.

### “Latest RFQ”

Prefer:

1. recent RFQ;
2. selected RFQ;
3. latest RFQ owned/assigned to the current role in an actionable state;
4. bounded candidates.

### “That comparison” / “the one you made”

Use recent comparison created by the last receipt before searching.

## 7.4 Material resolution

Resolve in this order:

1. exact item code;
2. exact normalized name;
3. alias/synonym;
4. token-normalized name;
5. typo-tolerant candidate search;
6. at most three approved scoped candidates.

Rules:

- never invent a material;
- never silently choose a materially different item;
- show code, name, UOM, and specification when asking for disambiguation;
- if no approved item exists, offer a material-master request flow inside the assistant;
- do not dead-end with “use another screen.”

## 7.5 Assignee resolution

Resolve only active memberships in the current workspace/plant and required role.

Order:

1. exact name/email;
2. unique role holder;
3. assigned owner from linked record/task;
4. reporting-tree candidate;
5. ask bounded clarification.

## 7.6 Search result contract

Never return giant rows to the model.

Each candidate observation contains:

```json
{
  "entity_type": "purchase_requirement",
  "entity_id": "internal-id",
  "business_number": "REQ-2026-0033",
  "label": "Aluminium Ingot · 100 KG",
  "status": "Approved",
  "owner": "Meera Iyer",
  "need_by": "2026-08-16",
  "allowed_next_actions": ["prepare_rfq_draft"]
}
```

---

# 8. Typed tool architecture

## 8.1 Remove active legacy intent remapping

The new capability registry may remain the policy catalog, but every active capability must point directly to a typed adapter.

Remove active mappings such as:

```text
prepare_rfq_draft -> legacy prepare_rfq -> task-bound handler
```

Do not delete compatibility code until tests prove it is unused, but remove it from the active runtime path.

## 8.2 Standard adapter signature

Every tool adapter uses:

```python
async def adapter(
    *,
    db: Session,
    actor: User,
    membership: WorkspaceMembership,
    thread: AgentThread,
    run: AgentRun,
    args: TypedArgs,
    correlation_id: str,
) -> ToolResult:
    ...
```

## 8.3 Standard `ToolResult`

Create a typed result model:

```python
class ToolResult(BaseModel):
    status: Literal[
        "observed",
        "completed",
        "needs_clarification",
        "blocked",
        "proposal_created",
        "processing",
        "failed",
    ]
    business_summary: str
    records: list[BusinessRecordRef] = []
    observations: list[CompactObservation] = []
    missing_fields: list[MissingField] = []
    blockers: list[Blocker] = []
    allowed_next_actions: list[AllowedAction] = []
    proposal: ProposalRef | None = None
    receipt: ReceiptRef | None = None
    artifacts: list[ArtifactRef] = []
    citations: list[CitationRef] = []
    job: JobRef | None = None
```

A mutation result without a receipt is invalid and must be converted to `failed` before response generation.

## 8.4 Tool categories

### Read/resolution tools

- `resolve_record`
- `search_records`
- `get_record_summary`
- `get_workflow_state`
- `list_actionable_work`
- `list_pending_decisions`
- `resolve_material`
- `resolve_assignee`
- `get_recent_entity`
- `get_document_summary`
- `get_quote_extraction_status`
- `get_supplier_performance`
- `get_team_status`

### Draft/preparation tools

- `create_purchase_requirement`
- `create_material_master_request`
- `prepare_rfq_draft`
- `update_rfq_draft`
- `prepare_quote_upload`
- `verify_quote_fields`
- `prepare_bid_comparison`
- `update_comparison_rationale`
- `prepare_purchase_order`
- `prepare_gate_entry`
- `prepare_store_receipt`
- `prepare_quality_inspection`
- `create_task`
- `delegate_task`
- `request_task_update`

### Controlled proposal tools

- `propose_send_rfq`
- `propose_submit_comparison`
- `propose_comparison_decision`
- `propose_confirm_purchase_order`
- `propose_send_purchase_order`
- `propose_erp_dispatch`
- `propose_inventory_disposition`
- `propose_case_closure`

### Knowledge/explanation tools

- `search_company_knowledge`
- `explain_workflow_state`
- `explain_recommendation`
- `explain_required_fields`
- `summarize_source_documents`

## 8.5 Role capability matrix

### Plant Manager

May:

- create requirements;
- inspect all scoped procurement progress;
- view pending decisions;
- approve/reject/request changes where policy allows;
- delegate to reporting descendants;
- request updates;
- summarize material risks/team status;
- view assistant-prepared approval briefs;
- search company knowledge.

May not:

- verify quotation evidence as Purchase Manager;
- publish RFQs unless explicitly granted Admin-like policy;
- create final PO unless role policy grants it;
- fabricate gate/store/quality facts.

### Purchase Manager

May:

- inspect requirements/RFQs/quotes;
- verify extracted quote fields;
- prepare comparisons;
- explain landed-cost calculations;
- prepare recommendation rationale;
- submit comparison through controlled proposal;
- prepare/confirm PO after approvals;
- request supplier/performance summaries;
- delegate/follow up with Purchase Executive descendants.

### Purchase Executive

May:

- create requirements;
- resolve approved materials and suppliers;
- prepare/update RFQ drafts;
- review draft documents;
- propose sending RFQs;
- upload/link quotations;
- follow up suppliers through controlled communication;
- approve/reject comparison when policy requires Purchase Executive approval.

### Gate Operator

May:

- find expected issued PO/ASN;
- prepare gate entry from challan/document/photo;
- record vehicle/challan/packages after confirmation;
- view only necessary handoff context;
- report missing documents or mismatch.

### Store Manager

May:

- find gate-admitted deliveries;
- prepare receipt from selected delivery;
- record received/damaged quantities;
- identify shortage/excess;
- create handoff to Quality;
- ask SOP questions.

### Quality Inspector

May:

- find pending inspections;
- retrieve specification/certificates;
- prepare inspection checklist;
- record accepted/rejected/held quantities;
- explain why comparison/inventory is blocked;
- create/update quality exception case.

### Admin

May perform operational capabilities for demo/support, but normal authority must still be visible and audited. Admin capabilities must never bypass tenant/plant scope.

---

# 9. Detailed assistant skills

## 9.1 Requirement creation

### Natural-language inputs

Support ordinary variations:

```text
Create a requirement for 100KG aluminium ingot needed next month.
We need 2 tonnes of copper rod by 15 August for raw material.
Raise a requirement for item CUI-102, quantity 100 kg, needed in four weeks.
Ask Meera to source 500 bearing sleeves by Friday.
```

### Required canonical fields

- approved item;
- positive quantity;
- UOM;
- need-by date;
- reason/purpose;
- Purchase Executive assignee.

Defaults:

- reason may default to a concise user-derived phrase such as `Raw material requirement` only when the user clearly states the purpose;
- assignee may auto-resolve when exactly one active Purchase Executive exists for the plant;
- UOM may default from the approved item only when quantity syntax does not contradict it.

### Behavior

1. extract supplied facts;
2. resolve item and assignee;
3. ask only for genuinely missing/ambiguous fields;
4. retain prior answers;
5. show a compact confirmation summary only when necessary;
6. call `domains/workflows.py::create_requirement`;
7. create receipt;
8. return exact business number, material, quantity, need-by, assignee, and next action;
9. store requirement as recent entity;
10. refresh My Work, tasks, badges, and selected context.

### Correct result

```text
Requirement PR-2026-0157 was created.

Aluminium Ingot · 100 KG
Needed by 16 Aug 2026
Assigned to Meera Iyer

Next: Meera can prepare the supplier request.

[View requirement] [Ask Meera to prepare RFQ]
```

Do not append generic role-ownership lectures unless the user asks or an authority boundary blocks the action.

## 9.2 Material-master request

When the item does not exist:

```text
I could not find “Copper Ingot” in the approved material master.

I can prepare a material request with:
Code: CUI-102
Name: Copper Ingot
UOM: KG
Reason: Raw material requirement

[Create material request] [Choose another material]
```

The agent may create the material-master request through the canonical service. It may not create the procurement requirement until the item is approved.

## 9.3 RFQ preparation

### User requests

```text
Generate RFQ for REQ-2026-0033.
Prepare the RFQ for the latest requirement.
Start supplier enquiry for the aluminium requirement.
Create the supplier request for the one I just made.
```

### Behavior

1. resolve requirement;
2. inspect workflow state;
3. verify role authorization;
4. check whether an RFQ already exists;
5. inspect capable supplier availability;
6. call `create_rfq_from_requirement` directly;
7. generate or refresh draft preview artifact;
8. persist receipt and recent RFQ/requirement;
9. return compact card;
10. do not send externally.

### Correct result

```text
Supplier request RFQ-2026-0041 is ready for review.

REQ-2026-0033 · Aluminium Ingot · 132 KG
3 approved suppliers selected
Response deadline: 1 Aug 2026

It has not been sent to suppliers.

[Review draft] [Edit suppliers]
```

If an RFQ already exists, return it idempotently with its current state.

If no capable suppliers exist, show the exact blocker and authorized remediation.

## 9.4 RFQ editing and sending

The assistant may:

- change deadline;
- include/exclude eligible suppliers;
- explain why a supplier is ineligible;
- generate/review draft PDF;
- create a controlled send proposal.

It must not send based on vague language such as “looks fine” unless the active proposal is unambiguous and the UI requires explicit confirmation.

The proposal summary must include:

- RFQ number;
- suppliers and contacts;
- response deadline;
- attachment version;
- immutability consequence;
- communication mode/status.

## 9.5 Quotation upload and extraction

### Desired flow

The Purchase Manager or Purchase Executive can attach PDFs/images/XLSX and say:

```text
These are the quotations for RFQ-2026-0041. Upload and process them.
```

The assistant must:

1. validate attachment scope/type/size;
2. resolve RFQ;
3. resolve supplier from document, filename, attachment metadata, or bounded user clarification;
4. create canonical quote/document records;
5. start extraction job;
6. return real job state;
7. when complete, show missing/low-confidence fields and source evidence;
8. never pretend extraction completed if the job is pending.

### Attachment association

When several files are uploaded:

- summarize filename/type/size;
- detect likely supplier and quote number;
- show unresolved associations before mutation if unsafe;
- allow one user confirmation for the batch;
- maintain per-file job state;
- create no duplicate quote for the same RFQ/supplier/document checksum.

## 9.6 Quote verification

The assistant may answer:

```text
What is still unverified?
Show me fields below 80% confidence.
Accept the GST and freight from Bharat Metals.
Correct delivery date to 4 August.
Why is this quotation blocked?
```

Behavior:

- use field-level source evidence;
- preserve units and currency;
- show confidence only when useful;
- one mutation per turn;
- explain whether the change enables comparison;
- never accept all uncertain fields without explicit user scope.

## 9.7 Supplier comparison chart

### Core user story

A Purchase Manager uploads quotations and says:

```text
Create the comparison chart and recommend the best supplier.
```

The assistant must:

1. resolve RFQ from explicit reference, attachments, selected context, or recent entity;
2. inspect extraction jobs;
3. identify verified and blocked quotations;
4. explain blockers if comparison is premature;
5. call the canonical deterministic comparison service;
6. generate the comparison artifact;
7. return real comparison business identity/version;
8. summarize recommended supplier, landed cost, delivery, compliance, and risks;
9. offer review/download/edit-rationale actions;
10. display the same comparison in the manual Comparison workbench.

### Correct result

```text
Comparison CMP-2026-0088 is ready for review.

Recommended: Bharat Metals
Landed total: ₹18.40 lakh
Delivery: 4 days before need-by
Verified quotations: 3

Watch-outs
• Payment terms are 15 days instead of the requested 30 days.
• Quote validity expires in four days.

[Review comparison] [Download chart] [Explain recommendation]
```

### Explanation

`explain_recommendation` must cite:

- quotation fields/evidence;
- deterministic score components;
- delivery feasibility;
- supplier quality/delivery score;
- disqualifications/deviations;
- calculation inputs.

Do not let the LLM invent a recommendation independent of the canonical comparison calculation.

## 9.8 Comparison approval

The assistant may prepare a proposal to send the frozen recommendation for approval.

Approvers receive a concise decision brief:

- requirement and RFQ;
- recommended supplier;
- total/variance;
- delivery feasibility;
- technical/commercial deviations;
- source comparison version;
- rationale;
- consequences of approve/reject/request changes.

The same immutable comparison version must be approved by the required roles.

## 9.9 Purchase order

After dual approval, the Purchase Manager can say:

```text
Prepare the purchase order.
```

The assistant should resolve the approved comparison, inspect state, and create a controlled PO confirmation proposal or draft according to current canonical semantics.

Result must clearly separate:

- PO prepared;
- PO finalized;
- supplier communication prepared;
- email dispatched;
- ERP posting proposed/approved/dispatched/acknowledged.

Never collapse these into “PO sent” unless delivery is actually recorded.

## 9.10 Gate, Store, and Quality assistants

### Gate

Input examples:

```text
This truck is for PO-2026-0187. Here is the challan.
Prepare the gate entry.
```

Assistant resolves PO, reads challan attachment, drafts vehicle/challan/package data, highlights mismatch, and asks for confirmation before recording factual entry.

### Store

```text
We received 1,480 KG; 20 KG is damaged.
```

Assistant resolves selected gate/PO context, validates quantities, calculates shortage/excess, records through canonical service after confirmation, and creates Quality handoff.

### Quality

```text
Inspect the pending sleeve delivery.
Show me the required checks.
1,400 KG accepted, 50 rejected, 30 held.
```

Assistant retrieves specification/certificates, presents checklist, validates dispositions, records canonical inspection after confirmation, and creates/updates exceptions.

## 9.11 Tasks and delegation

Users can say:

```text
Ask Meera to collect the remaining quotations by tomorrow 3 PM.
Follow up with Vikram on the comparison.
What am I waiting on?
What is my team blocking?
```

The assistant must create/update real tasks/delegations and notifications.

Task display must include:

- business outcome;
- linked business number/material;
- owner;
- due state;
- blocker;
- expected result;
- last update;
- next authorized action.

Default task queries show active/actionable work only, maximum five, ordered by urgency/business impact.

## 9.12 Manager follow-up and agent-to-agent coordination

Manager request:

```text
What is blocking REQ-2026-0033? Ask the owner for an update.
```

Flow:

1. manager agent resolves requirement and active task;
2. verifies owner is an authorized descendant;
3. creates persisted follow-up/delegation;
4. recipient sees notification/task request;
5. recipient or recipient assistant records a response based on real workflow state;
6. manager receives sourced summary with owner, timestamp, blocker, next commitment;
7. no hidden recursive model conversation;
8. delegation depth/cycle limits enforced.

## 9.13 Knowledge and task explanation

Users can ask:

```text
Why do I need to verify quotations before comparison?
What certificates are required for this material?
How do we handle a rejected delivery?
Explain this task to me.
```

Answers must prefer:

1. current business record/workflow state;
2. company policy/SOP knowledge;
3. product process documentation;
4. general model knowledge only when clearly labelled and non-authoritative.

Cite source document/section when company knowledge is used.

## 9.14 Proactive assistance

Implement scheduled/proactive preparation using Celery/beat and persisted notifications, not spontaneous untraceable messages.

Initial proactive rules:

- approval due within configured SLA;
- delegated task overdue;
- supplier quotation deadline approaching with missing responses;
- need-by date at risk based on promised delivery;
- quote validity expiring;
- extraction waiting for verification;
- PO acknowledgement overdue;
- gate/store/quality handoff pending;
- quality hold unresolved;
- supplier document/certificate missing.

Each alert must include:

- why it matters;
- linked record;
- owner;
- due/risk time;
- recommended next action;
- deduplication key;
- dismissal/resolution state.

---

# 10. Response generation and conversation quality

## 10.1 Answer-first policy

Every response begins with the answer or result.

Bad:

```text
I can help you with procurement. Purchase Executive owns RFQ preparation...
```

Good:

```text
RFQ-2026-0041 is ready for review.
```

Then include only the context required to trust or continue the work.

## 10.2 Mutation response template

For successful preparation/mutation:

```text
<Business result and exact business number>

<Key fields, maximum 5 lines>

<Important warning or consequence, if any>

[Primary next action] [Secondary action]
```

## 10.3 Clarification policy

Ask a clarification only when:

- a required field is genuinely absent;
- multiple candidates create meaningful risk;
- authority or workflow state requires user choice;
- attachment-to-record association is ambiguous;
- a controlled consequence needs confirmation.

A clarification must:

- retain and restate known facts compactly;
- ask one focused question where possible;
- show at most three candidates;
- never repeat a question already answered;
- never redirect to another page when the assistant can prepare the necessary request itself.

## 10.4 Failure policy

Failures must state:

1. what could not be done;
2. the exact blocker;
3. what was preserved;
4. the authorized next action.

Example:

```text
I could not prepare the supplier request because no approved supplier is capable of all requirement lines.

Requirement: REQ-2026-0033
No records were changed.

[Review supplier capabilities] [Ask Admin to update master data]
```

## 10.5 Prohibited response patterns

Block or rewrite responses containing unsupported phrases such as:

- “I’ll provide it shortly”;
- “I’m checking” without a persisted job;
- “has been sent” when only drafted;
- “has been approved” without a matching decision record;
- “I completed” without receipt;
- raw tool names;
- raw JSON;
- giant record lists;
- generic role explanations unrelated to the request.

## 10.6 Response length

Default:

- direct answer: 1–4 short paragraphs;
- result card: maximum 8 business lines plus actions;
- task list: maximum five rows;
- comparison explanation: top recommendation, 2–4 reasons, 1–3 risks;
- detailed calculations only on request or expandable UI.

---

# 11. Manual workflow redesign

## 11.1 Global interaction rules

1. One dominant next action per workflow state.
2. Preserve selected record context across navigation and refresh.
3. Use business numbers and labels, not raw IDs.
4. Ordinary draft edits autosave or use one unobtrusive `Save changes` action.
5. External/immutable actions get consequence confirmation.
6. Disabled actions explain the blocker and resolution.
7. Assistant and manual UI call identical services.
8. After mutation, refresh record, tasks, badges, notifications, and assistant context together.
9. Do not show the complete lifecycle as a row of equal buttons.
10. Put detailed history/audit under secondary tabs.

## 11.2 Business language system

Use:

| Avoid | Use |
|---|---|
| Generate RFQ | Prepare supplier request |
| Publish RFQ | Send to suppliers |
| Save RFQ | Save changes |
| Preview draft PDF | Review supplier document |
| Generate comparison | Compare verified quotations |
| Submit comparison | Send recommendation for approval |
| Record decision | Approve / Reject / Request changes |
| Confirm PO | Create purchase order |
| Supplier email | Send purchase order to supplier |
| Outbox | Delivery status |
| Artifact | Document |
| Entity | Record |
| Receipt | Completed action |
| Agent run | Assistant activity |

## 11.3 Requirement page

Layout:

- compact page header;
- primary `New requirement` action;
- filters/search;
- requirement cards/table with business number, material summary, need-by, owner, current stage, blocker, next action;
- assistant context follows selected requirement.

Creation form:

- multi-line support remains;
- searchable approved material picker;
- quantity + UOM inline;
- natural language date helper;
- assignee defaults when unique;
- missing material request inline;
- no raw IDs or setup jargon.

## 11.4 RFQ workbench

When opened from requirement, never ask the user to reselect it.

State-driven stepper:

```text
1. Request details
2. Suppliers
3. Review
4. Send
```

State behavior:

| Current state | Dominant action |
|---|---|
| Approved requirement, no RFQ | Prepare supplier request |
| Draft missing fields | Complete supplier request |
| Complete draft | Review and send |
| Review | Send to N suppliers |
| Published/pending dispatch | View sent request |
| Dispatched | Track quotations |

Remove duplicate publish controls from other pages. Other surfaces deep-link to the canonical Review and Send step.

## 11.5 Quotation workbench

Use three panes/areas where screen permits:

- quote/source list;
- document preview;
- extracted fields and verification.

Show:

- supplier and quote number;
- extraction status;
- fields needing review;
- evidence source;
- confidence only when helpful;
- whether comparison is blocked;
- one dominant action such as `Finish verification`.

## 11.6 Comparison workbench

Sections:

1. requirement/RFQ context;
2. supplier comparison table;
3. recommendation summary;
4. deviations and risks;
5. source evidence/calculation drawer;
6. approval state;
7. one dominant next action.

Do not show `Generate`, `Preview`, `Submit`, and approval controls simultaneously.

## 11.7 Purchase order workbench

Clearly separate:

- prepared draft;
- final controlled PO;
- supplier delivery state;
- ERP posting state.

Do not imply one state means another.

## 11.8 Inbound workbenches

Gate, Store, and Quality pages must always show selected:

- PO/business number;
- supplier;
- material;
- expected quantity;
- previous-stage record;
- current owner/status.

No raw-ID dropdown workflow.

---

# 12. Assistant-first frontend

## 12.1 Desktop information architecture

At width `>= 1280px`:

```text
compact navigation | actionable workspace | persistent assistant panel
```

Recommended widths:

```text
navigation: 220–232 px
assistant: 360–400 px
centre: remaining width
```

When assistant is intentionally collapsed, centre content expands fully. Do not reserve a blank column.

## 12.2 Header

Show:

- greeting and role;
- plant/workspace selector;
- global search/command palette;
- notification bell with unread badge;
- user menu;
- small environment badge only in non-production.

Remove duplicate greetings and generic status chips such as `Role queue active`.

## 12.3 My Work homepage

First viewport order:

1. **Needs your attention**
2. **Assistant prepared**
3. **My tasks** / **Waiting on others**
4. optional recent activity/summary below fold

The page must answer:

- what needs my decision;
- what my assistant prepared;
- what I need to do;
- what I am waiting for;
- what is at risk.

### Needs your attention

Cards represent decisions/blockers, not generic counters.

Each card contains:

- business outcome;
- record number/material;
- reason it matters;
- due/risk state;
- owner;
- one action.

### Assistant prepared

Show real persisted items:

- RFQ draft ready;
- quotation extraction waiting for review;
- comparison ready;
- supplier follow-up drafts;
- approval brief;
- PO draft.

Never display synthetic demo cards unrelated to records.

### My tasks

Show actionable tasks only, grouped by urgency. Completed work belongs in activity/history.

### Waiting on others

Show delegated/handed-off work with owner, due status, blocker, and `Request update` action.

## 12.4 Notification badges

Badge counts are server-derived and role-scoped.

Required badges:

- My Work: total actionable attention items;
- Requirements: assigned requirements waiting for action;
- RFQs: drafts/reviews/responses needing action;
- Quotations: uploads/extractions/verifications needing action;
- Comparison: recommendations/decisions needing action;
- Purchase Orders: confirmations/delivery/posting attention;
- Inbound role pages: pending gate/store/quality work;
- notification bell: unread notifications.

Do not count completed records or unrelated tenant data.

## 12.5 Assistant panel

Header:

- role assistant name;
- current availability/provider state in plain language;
- thread history button;
- new conversation;
- expand/collapse.

Context chips:

- selected plant;
- selected business record;
- current task when applicable;
- attachments.

Conversation:

- user and assistant messages;
- result cards;
- proposal confirmations;
- job-progress cards;
- evidence/source links;
- concise errors.

Composer:

- multiline input;
- file attachment;
- record attachment/context selector;
- send;
- optional voice later, not required now;
- disabled/loading state with clear reason.

Suggested prompts must be role- and context-specific. They are convenience actions, not the only supported language.

## 12.6 Error presentation

Never render raw API JSON such as:

```text
{"detail":"Unknown assistant capability"}
```

Map errors to business copy:

```text
I could not match that request to an available action.
Try naming the requirement, RFQ, quotation, or task you want to work on.
```

Developer details may appear in a collapsible diagnostic area only in development/admin mode.

## 12.7 Responsive behavior

### 900–1279 px

- navigation collapsible;
- assistant is a right drawer;
- centre uses full available width;
- no horizontal page overflow.

### Below 900 px

- attention items first;
- bottom/floating assistant entry with composer drawer;
- cards stack;
- tables horizontally scroll with fixed action visibility;
- controls minimum 44px targets.

## 12.8 Visual system

Use the already generated modern UI direction as reference, not as pixel-perfect code.

Tokens:

```css
--background: #f5f7fa;
--surface: #ffffff;
--surface-muted: #f8fafc;
--sidebar: #101827;
--sidebar-hover: #1c293b;
--text-primary: #111827;
--text-secondary: #667085;
--border: #e2e8f0;
--primary: #e86f24;
--primary-hover: #cf5c17;
--success: #16835f;
--warning: #b7791f;
--danger: #c2413b;
--info: #2563eb;
```

Rules:

- 10–12px card radius;
- subtle borders;
- restrained shadows;
- 16–24px card padding;
- no beige legacy canvas;
- no excessive uppercase letter spacing;
- no decorative AI gradients/illustrations;
- monospace only for business IDs where useful;
- status colors used semantically, not decoratively.

---

# 13. Workspace and demo behavior

## 13.1 New demo workspace access

A newly created development/demo workspace must be accessible by all standard demo roles, not only the creator.

After workspace creation in development/demo mode:

- creator remains Plant Manager and workspace owner;
- create/reuse standard Purchase Manager, Purchase Executive, Gate, Store, Quality, and Admin accounts;
- create scoped memberships and plant access;
- create reporting lines;
- create role AgentProfiles;
- make workspace selectable at login for every demo account;
- create no sample transactional records unless user selects an explicit seeded-demo option;
- show a demo access summary page with role emails and one-click copy, never passwords in production.

## 13.2 Production safety

Demo bootstrap must be guarded by explicit environment/config flags.

Production workspace creation must not automatically attach global demo accounts.

## 13.3 Readiness

Workspace readiness must clearly show:

- role coverage;
- approved materials;
- capable suppliers;
- assistant provider/configuration;
- email/ERP simulation/live state.

Do not block all product use because one optional integration is absent.

---

# 14. Tasks, notifications, and coordination model

## 14.1 Task semantic key

Prevent active duplicate workflow tasks.

Define a semantic uniqueness key using available fields, conceptually:

```text
tenant + plant + task_type + linked_entity_type + linked_entity_id + owner_membership + active_generation
```

Before creating a workflow task:

- find existing active equivalent;
- update/reuse it where appropriate;
- do not create another identical active task;
- preserve historical completed/cancelled tasks.

Add a migration/index only if it is compatible with existing records; otherwise enforce service-level idempotency and add a reconciliation command/test.

## 14.2 Task titles

Generic task type remains internal. User-facing task label is enriched from linked record.

Bad:

```text
Prepare and publish supplier RFQ
```

Good:

```text
Prepare supplier request
REQ-2026-0033 · Aluminium Ingot · 132 KG
```

## 14.3 Notification model

Notification categories:

- decision required;
- task assigned;
- follow-up requested;
- task overdue;
- assistant prepared work;
- document processing complete/failed;
- supplier response received;
- approval result;
- handoff ready;
- exception/risk;
- controlled action result.

Each notification contains:

- category;
- title;
- concise body;
- business record reference;
- task/proposal reference where applicable;
- severity;
- read state;
- action/deep link;
- deduplication key;
- created/resolved timestamps.

## 14.4 Badge-count API

Provide one compact endpoint or extend existing agent home response:

```json
{
  "my_work": 3,
  "requirements": 1,
  "rfqs": 2,
  "quotations": 4,
  "comparison": 1,
  "purchase_orders": 0,
  "gate": 2,
  "store": 0,
  "quality": 1,
  "notifications_unread": 6
}
```

Counts are role-, tenant-, plant-, and membership-scoped.

---

# 15. Data model and migration guidance

## 15.1 Reuse existing models

Prefer existing:

- `AgentProfile`;
- `AgentThread`;
- `AgentMessage`;
- `AgentRun`;
- `AgentEvent`;
- `AgentCheckpoint`;
- `AgentToolCall`;
- `AgentProposal`;
- `AgentActionReceipt`;
- `AgentDelegation`;
- `Task`;
- `Notification`;
- `KnowledgeDocument/Chunk`;
- business procurement entities.

## 15.2 Expected schema changes

Only add fields/tables proven necessary after inspection.

Likely additions:

- `AgentThread.context_schema_version` if not inferable from JSON;
- `AgentRun.step_count`, `read_tool_count`, `mutation_count`, `termination_reason` if metrics cannot fit existing columns;
- `Task.semantic_key` or equivalent idempotency field;
- notification `dedupe_key`, `resolved_at`, `action_type`, `action_payload` if absent;
- attachment-to-agent-run association only if existing message/document relation is insufficient;
- agent evaluation result tables are optional; JSON reports in test artifacts are sufficient initially.

Use one new Alembic migration after existing `0010`, with a descriptive name rather than an opaque number if repository convention permits.

## 15.3 No model-direct business writes

Every business mutation adapter must call an existing canonical domain service. If no canonical service exists for a supported UI mutation, extract one from the current route handler and make both route and agent call it.

Do not duplicate route logic inside `agent_service.py`.

---

# 16. API contracts

## 16.1 Agent message response

The normal response should include:

```json
{
  "message": {
    "id": "...",
    "content": "RFQ-2026-0041 is ready for review.",
    "blocks": []
  },
  "selected_context": {},
  "created_or_updated_records": [],
  "allowed_actions": [],
  "proposal": null,
  "job": null,
  "badge_counts": {},
  "correlation_id": "..."
}
```

Do not expose chain-of-thought, hidden planning, or raw tool observations.

## 16.2 Typed block set

Use a small stable set:

- `answer`;
- `record_card`;
- `task_card`;
- `prepared_work_card`;
- `comparison_summary`;
- `missing_information`;
- `blocker`;
- `warning`;
- `proposal_confirmation`;
- `job_progress`;
- `artifact_link`;
- `source_citation`;
- `next_actions`.

Remove or hide runtime-specific blocks from normal role UI.

## 16.3 Tool execution API boundary

Tools are internal server operations, not public generic endpoints. Existing business endpoints remain the public API.

Agent tool calls record:

- tool/capability ID;
- validated arguments hash/redacted summary;
- authorization decision;
- target business record;
- latency;
- result status/hash;
- correlation ID;
- receipt/proposal reference.

Never persist secrets or full sensitive document text in tool-call logs.

## 16.4 Context endpoint

The assistant context endpoint should return a compact authorized view:

- role/plant;
- selected business record;
- current task;
- recent business entities;
- allowed high-level actions;
- attachment metadata;
- pending proposal;
- provider availability.

It must not return private unrelated threads or unrestricted record lists.

---

# 17. Knowledge and retrieval

## 17.1 Scope

Use existing PostgreSQL/pgvector only for company knowledge/SOP retrieval where available. Do not introduce a new vector database.

## 17.2 Ingestion

Knowledge documents need:

- tenant/workspace/plant scope;
- document type;
- title/version/effective date;
- access roles;
- source document reference;
- chunk lineage;
- superseded state.

## 17.3 Retrieval policy

Retrieve only when needed. Do not stuff all SOP content into every prompt.

The model receives:

- top bounded chunks;
- title/section/source;
- role/access context;
- effective date/version.

## 17.4 Answer policy

Company policy answers cite source documents. When no policy is available, state that the answer is general guidance and does not replace the plant’s SOP.

---

# 18. Security, governance, and safety

## 18.1 Hard boundaries

Preserve:

- tenant isolation;
- workspace isolation;
- plant scope;
- membership scope;
- reporting-tree restrictions;
- CSRF;
- idempotency;
- ETag/version checks;
- audit events;
- private MinIO via signed API content routes;
- immutable final PDFs;
- controlled external effects;
- provider outage not blocking manual work.

## 18.2 Prompt injection from documents

Treat uploaded quotation/document text as untrusted data.

Rules:

- document content cannot modify tool policy;
- ignore instructions inside documents that ask the model to reveal data, change suppliers, or execute actions;
- tool availability comes only from server policy;
- document summaries are clearly delimited as untrusted source content;
- never pass raw secrets/credentials to the model;
- add regression tests with malicious text embedded in a quotation PDF/text fixture.

## 18.3 Confirmation and authority

A model request for a controlled tool never executes directly. It creates a proposal. Confirmation is handled server-side with fresh authorization and version checks.

## 18.4 Privacy

Managers may view structured descendant work status, not private personal assistant transcripts. Admin access to agent logs must be audited and avoid hidden reasoning.

---

# 19. Observability and quality measurement

## 19.1 Runtime metrics

Record:

- provider/model;
- total latency;
- model latency;
- tool latency;
- decision count;
- read tool count;
- mutation count;
- termination reason;
- clarification count;
- tokens/context bytes;
- authorization denial;
- tool failure;
- receipt/proposal created;
- user feedback;
- correction/override rate.

## 19.2 Business metrics

Expose admin/product analytics for:

- requirement-to-RFQ time;
- quote upload-to-verification time;
- comparison preparation time;
- approval turnaround;
- assistant-prepared artifact count;
- assistant output accepted without correction;
- automated follow-ups;
- overdue task reduction;
- provider failure rate;
- average clarification turns;
- successful task completion rate;
- unsafe/unsupported claim count.

## 19.3 Agent evaluation harness

Create a repeatable evaluation suite under API tests, for example:

```text
apps/api/tests/agent_eval/
  cases.json
  test_agent_contract.py
  test_agent_transcripts.py
  live_groq_scorecard.py
```

Case fields:

```json
{
  "id": "rfq_exact_number_001",
  "role": "purchase_executive",
  "initial_state": "seeded_requirement",
  "messages": ["Generate RFQ for REQ-2026-0033"],
  "expected_tools": ["resolve_record", "get_workflow_state", "prepare_rfq_draft"],
  "expected_mutations": 1,
  "expected_record_type": "rfq",
  "must_include": ["RFQ-"],
  "must_not_include": ["Task context required", "count", "{}"]
}
```

## 19.4 Evaluation categories

At minimum 100 paraphrase/noise cases across:

- create requirement;
- topic switching;
- material code/name/typo;
- date/quantity phrasing;
- exact and relative record references;
- RFQ preparation;
- RFQ existing/idempotent;
- quotation attachment association;
- quote verification;
- comparison generation;
- recommendation explanation;
- approval proposal;
- PO proposal;
- task delegation/follow-up;
- manager team summary;
- inbound preparation;
- unauthorized role;
- out-of-tenant record;
- provider outage;
- malicious document prompt injection;
- ambiguous record clarification;
- follow-up pronouns.

## 19.5 Quality thresholds

### Deterministic/mock model suite

- 100% authorization and scope correctness;
- 100% controlled-action confirmation correctness;
- 100% mutation receipt correctness;
- 100% no raw JSON/runtime leakage;
- at least 95% scenario task success;
- zero false success claims;
- zero cross-tenant data exposure.

### Live Groq scorecard

Run separately when credentials exist:

- at least 85% end-to-end task success on the representative set;
- at least 95% correct tool family selection after bounded recovery;
- zero unsafe automatic controlled actions;
- median clarifications no more than one for resolvable tasks;
- all failures categorized with captured correlation IDs.

Do not make unit tests depend on live Groq.

---

# 20. Exact acceptance conversations

Codex must add tests for these and additional paraphrases.

## 20.1 Requirement with topic change

```text
User: Create a requirement for Copper Ingot 100 KG for raw material.
Assistant: asks only for need-by date if item/assignee are resolvable.
User: Item code CUI-102 and delivery date is one month.
Assistant: if material absent, offers material-master request.
User: Leave this. Create a requirement for Aluminium Ingot 100 KG for raw material.
Assistant: clears Copper blocker, resolves Aluminium, asks only any genuinely missing field.
User: Create this requirement.
Assistant: creates the Aluminium requirement and returns exact PR number.
User: What is its ID?
Assistant: returns the same exact PR number immediately.
```

## 20.2 Exact RFQ

```text
User: Generate RFQ for REQ-2026-0033.
Assistant: resolves exact requirement and prepares real RFQ from a normal thread.
```

Must not require opening a task.

## 20.3 Latest RFQ

```text
User: Can you generate the RFQ for the latest requirement?
Assistant: resolves one eligible requirement or asks one bounded clarification.
```

Must not list all tasks.

## 20.4 RFQ follow-up

```text
User: What is its ID?
Assistant: returns RFQ business number.
User: Show me the preview.
Assistant: returns/open action for the actual draft document.
User: Send it to suppliers.
Assistant: creates a controlled proposal with supplier/deadline consequences.
```

## 20.5 Comparison from attachments

```text
User attaches three quotation files.
User: These are for RFQ-2026-0041. Process them and create the supplier comparison.
Assistant: associates files, starts real extraction jobs, reports processing state.
After jobs complete, assistant identifies fields needing verification or prepares comparison if verified.
Assistant: returns comparison number, recommendation, reasons, risks, and artifact actions.
```

Do not claim the comparison exists before canonical persistence.

## 20.6 Explain recommendation

```text
User: Why Bharat Metals?
Assistant: cites landed cost, delivery, compliance, supplier performance, and deviations from persisted comparison data.
```

## 20.7 Manager delegation

```text
Plant Manager: Ask Meera to collect the missing quotation by tomorrow at 3 PM.
Assistant: creates a real delegated task/follow-up to authorized descendant and returns task identity.
Plant Manager: What is the status?
Assistant: reads the persisted task/update and answers with owner, blocker, timestamp, commitment.
```

## 20.8 Unauthorized action

```text
Gate Operator: Approve the supplier comparison.
Assistant: refuses the unauthorized action, explains who owns it, and offers to view status or notify the owner.
```

## 20.9 Provider outage

Exact unambiguous reads and safe draft continuation may work through deterministic fallback according to policy. Complex ambiguous planning returns a clear outage state and manual deep link. No fake answer.

---

# 21. Implementation phases

Codex must complete phases in order. Each phase has a gate. Do not move to the next phase with failing phase tests.

## Phase 0 — Baseline and protection

Tasks:

1. capture `git status --short`, `git diff --check`, Docker health;
2. run current API, typecheck, build, and targeted Playwright baseline;
3. preserve screenshots of current My Work, assistant, RFQ, quotations, comparison;
4. add exact failing transcript tests before changing behavior;
5. document current active runtime path from message endpoint to adapter;
6. identify which legacy handlers are still actively invoked;
7. inspect existing task duplicates using the handoff SQL and service paths.

Gate:

- baseline recorded;
- failing transcript tests reproduce defects;
- no source edits outside tests/diagnostic documentation yet.

## Phase 1 — Typed state, resolution, and result contracts

Tasks:

1. implement `AgentThreadStateV2`;
2. implement compatibility loader/migration-on-read;
3. implement central state merge/topic-switch/coreference rules;
4. create `agent_resolution.py`;
5. implement exact business number, selected context, recent entity, latest eligible, and bounded search resolution;
6. implement `ToolResult` and related typed references;
7. add unit tests for state and resolution across tenant/plant scope.

Gate:

- state tests pass;
- exact/relative resolution tests pass;
- no cross-scope lookup;
- existing agent tests remain passing or are intentionally updated.

## Phase 2 — Direct adapters for demonstrated procurement skills

Implement direct adapters first for:

1. `create_purchase_requirement`;
2. `create_material_master_request`;
3. `prepare_rfq_draft`;
4. `update_rfq_draft`;
5. `list_actionable_work`;
6. `get_record_summary`;
7. `get_workflow_state`.

Remove their active mapping to legacy task-bound handlers.

Add receipt/recent-entity updates and compact response cards.

Gate:

- exact requirement conversation passes;
- topic switch passes;
- exact/latest RFQ conversations pass;
- no task-context prerequisite;
- no raw output leakage;
- one mutation per turn enforced.

## Phase 3 — Bounded LangGraph tool loop

Tasks:

1. implement model-decide/tool-observe loop;
2. expose only role-scoped tool schemas;
3. validate every tool request server-side;
4. append compact observations;
5. enforce budgets and one mutation;
6. implement termination reasons;
7. preserve checkpoints/events without exposing hidden reasoning;
8. retain grounded receipt validation;
9. implement provider-failure behavior;
10. retire active one-shot dispatcher path after compatibility tests.

Gate:

- multi-read single-mutation tests pass;
- wrong-first-read recovery test passes;
- budget exhaustion is safe;
- provider outage behavior passes;
- no unsafe controlled actions.

## Phase 4 — Complete procurement tool suite

Tasks:

1. quotation attachment association and processing adapters;
2. extraction status/read tools;
3. quote verification adapters;
4. comparison preparation adapter;
5. recommendation explanation tool;
6. comparison submission proposal;
7. approval decision proposal;
8. PO preparation/confirmation proposal;
9. supplier follow-up/task tools;
10. artifact/document result cards.

Gate:

- upload-to-comparison scenario passes with fixture documents;
- blocked quote verification is explained;
- deterministic recommendation is preserved;
- controlled proposals revalidate and confirm correctly;
- assistant-created records appear in manual workbenches.

## Phase 5 — Inbound and role-assistant completion

Tasks:

1. Gate preparation/recording assistant;
2. Store receipt assistant;
3. Quality checklist/disposition assistant;
4. exception/case explanation;
5. role-specific suggested prompts;
6. authorization tests across every standard role.

Gate:

- gate -> store -> quality order enforced;
- quantity validation preserved;
- unauthorized roles denied without data leakage;
- normal role can complete its scoped workflow conversationally and manually.

## Phase 6 — Hierarchy, follow-ups, notifications, proactive rules

Tasks:

1. task semantic idempotency;
2. enriched task summaries;
3. real manager delegation and update requests;
4. agent-to-agent persisted coordination;
5. notification categories/deduplication;
6. badge counts;
7. Celery proactive rules;
8. manager team summary.

Gate:

- duplicate active task tests pass;
- reporting-tree scope tests pass;
- manager follow-up scenario passes;
- notifications/badges update after workflow transitions;
- no recursive hidden agent chatter.

## Phase 7 — Manual workflow simplification

Tasks:

1. state-driven Requirement and RFQ flows;
2. one canonical RFQ review/send control;
3. quotation verification workbench;
4. comparison/approval step flow;
5. PO delivery/posting separation;
6. inbound context-rich workbenches;
7. business-language replacement;
8. no raw IDs/JSON in normal UI;
9. deep links from assistant cards to selected workbench state.

Gate:

- one dominant action per state;
- no duplicate publish/send mutation controls;
- selected context retained;
- same canonical service used by assistant and manual route;
- Playwright workflow passes desktop/tablet/mobile.

## Phase 8 — Assistant-first UI and visual redesign

Tasks:

1. compact shell/navigation/header;
2. persistent desktop assistant panel;
3. My Work sections in required order;
4. attention/prepared/task/waiting cards;
5. notification bell and nav badges;
6. role/context suggestions;
7. attachment and job-progress UI;
8. business error mapping;
9. responsive drawer/mobile behavior;
10. visual token replacement;
11. accessibility/focus/loading states.

Gate:

At 1440x900:

- no large unused blank area;
- at least one actionable item above fold when data exists;
- assistant composer visible;
- no duplicate greeting;
- no giant empty metric cards;
- no raw API error;
- no technical runtime terminology.

At 1024 and mobile:

- no horizontal page overflow;
- assistant accessible;
- actions not clipped;
- focus and keyboard navigation work.

## Phase 9 — Evaluation, observability, and demo readiness

Tasks:

1. complete 100-case agent eval set;
2. run deterministic/mock suite;
3. run live Groq scorecard when key exists;
4. add provider/runtime dashboard or admin diagnostics;
5. verify demo workspace access for all roles;
6. create clean demo seed scenario;
7. run full client demo script;
8. capture final screenshots;
9. update authoritative handoff and README/product positioning;
10. produce final completion report.

Gate:

- all required commands pass;
- thresholds in Section 19.5 achieved or shortfall explicitly reported;
- client demo script works without database/manual repair;
- no known release-blocking transcript failure remains.

---

# 22. File-level implementation map

Inspect and modify only as needed.

## Backend primary files

### `apps/api/app/agent_service.py`

- extract active runtime graph from monolithic dispatcher;
- integrate bounded tool loop;
- remove active legacy mappings;
- build compact context;
- persist run/events/checkpoints/results;
- enforce budgets/termination;
- grounded response generation.

### `apps/api/app/agent_capabilities.py`

- keep policy registry;
- point every active capability to direct typed adapter;
- role/controlled/attachment metadata;
- remove “declared but not implemented” capabilities from user exposure.

### `apps/api/app/agent_schemas.py`

- `AgentThreadStateV2`;
- tool argument/result models;
- compact record/action/blocker/artifact/job schemas;
- stable user-facing block types.

### `apps/api/app/agent_resolution.py` — new if absent

- scoped exact/relative resolution;
- material/assignee resolvers;
- bounded candidate formatting.

### `apps/api/app/agent_tools.py` or `apps/api/app/agent_adapters.py` — new if useful

- direct adapter map;
- shared adapter helpers;
- no canonical business calculations here.

### `apps/api/app/routers/agents.py`

- message response contract;
- badge counts/context;
- proposal confirmation;
- notification/task endpoints;
- no runtime internals in normal response.

### `apps/api/app/domains/workflows.py`

- reuse/extract canonical services;
- task idempotency;
- business summaries/allowed next action helpers where appropriate;
- no agent-specific duplicate workflow.

### `apps/api/app/procurement_v2.py`

- reuse artifact/comparison/PO services;
- expose canonical callable functions if current logic is route-bound;
- preserve deterministic calculations/versioning.

### `apps/api/app/task_service.py`

- semantic active-task idempotency;
- actionable queries;
- delegation/follow-up/notification behavior;
- reporting-tree scope.

### `apps/api/app/documents.py`

- attachment validation/association;
- job state summaries;
- prompt-injection-safe extraction context.

### `apps/api/app/db/models.py`

- minimal fields only;
- no duplicate agent/business models.

### `apps/api/app/db/seed.py`

- clean demo master data;
- all-role workspace accessibility in demo mode;
- optional clean demo scenario;
- avoid duplicate tasks/transactions.

### `apps/api/app/core/config.py`

- runtime budgets;
- demo bootstrap flag;
- live evaluation flag;
- proactive rule settings;
- provider fallback policy.

### migrations

- one migration after current head if schema changes are required;
- update tests for PostgreSQL and SQLite compatibility.

## Frontend primary files

### `apps/web/components/features/IndustrialConsole.tsx`

- shell/page composition;
- My Work information architecture;
- navigation badges;
- selected context/deep links;
- remove duplicate greetings/empty chrome.

### `apps/web/components/features/AgentDrawer.tsx`

- persistent panel/drawer behavior;
- conversation cards;
- proposal/job/error rendering;
- attachments;
- suggestions;
- no raw errors.

### `apps/web/components/features/AgentWorkspace.tsx`

- business-oriented assistant activity;
- hide runs/checkpoints/tool calls from normal roles;
- admin diagnostics separated.

### `apps/web/components/features/WorkflowForms.tsx`

- requirement form simplification;
- RFQ stepper;
- quotation verification;
- comparison/approval/PO/inbound state-driven actions;
- remove duplicate transition controls.

### `apps/web/components/WorkspaceCommandPalette.tsx`

- business record/action search;
- role-scoped commands;
- open selected record context.

### `apps/web/lib/api.ts`

- typed endpoints;
- normalized business errors;
- context/badge refresh;
- idempotency/ETag preservation.

### `apps/web/app/globals.css`

- new tokens/layout/responsive behavior;
- remove conflicting legacy styles;
- no broad unrelated formatting.

### Playwright specs

- exact transcript UI flows;
- requirement -> RFQ -> review/send;
- attachments -> comparison;
- role workspace selection;
- badges/notifications;
- desktop/tablet/mobile screenshots.

---

# 23. Required test matrix

## 23.1 Backend unit tests

- state V2 load/merge/topic switch;
- recent entity coreference;
- exact business number resolution;
- latest eligible resolution;
- ambiguity candidates;
- material typo/alias/code resolution;
- assignee resolution;
- role capability authorization;
- one mutation per turn;
- tool budget;
- receipt required;
- controlled proposal revalidation;
- prompt injection in document content;
- task semantic idempotency;
- notification deduplication;
- reporting-tree scope;
- provider outage.

## 23.2 Backend integration tests

- requirement creation through assistant and manual endpoint produce equivalent canonical records;
- RFQ exact/latest from normal thread;
- RFQ idempotency;
- upload/extraction/verification/comparison;
- approval version isolation;
- PO controlled confirmation;
- gate/store/quality ordering;
- manager follow-up;
- cross-tenant denial;
- private document URLs.

## 23.3 Frontend tests

- no raw JSON error;
- assistant result card opens exact record;
- recent entity follow-up;
- attachment progress;
- proposal confirmation;
- badges refresh after mutation;
- one dominant action per state;
- no duplicate send/publish controls;
- selected context persists;
- responsive layouts;
- keyboard/focus/accessibility.

## 23.4 Screenshot set

Capture at minimum:

- My Work Plant Manager;
- My Work Purchase Executive;
- assistant successful requirement;
- assistant RFQ result;
- quotation extraction review;
- comparison recommendation;
- approval brief;
- RFQ Review and Send;
- mobile assistant drawer.

---

# 24. Verification commands

Use repository scripts where they exist. Expected minimum:

```powershell
git diff --check

docker compose up --build -d
docker compose ps -a
docker compose logs --tail=200 api worker beat web minio

cd apps/api
python -m pytest -q

cd ../..
npm run generate:api
npm run check:api-contract
npm run typecheck
npm run build:web
npm run test:e2e
```

Run targeted tests after each phase before the full suite.

If live Groq credentials exist:

```powershell
cd apps/api
python -m app.tests.agent_eval.live_groq_scorecard
```

Use the actual repository path/module name implemented for the scorecard.

Do not block the deterministic test suite on external provider availability.

---

# 25. Client demo script

The final product must support this clean sequence.

## Scene 1 — Workspace and roles

1. Plant Manager creates a new demo workspace.
2. Readiness page shows all standard role memberships.
3. Sign in/switch as Purchase Executive and Purchase Manager without manual database changes.

## Scene 2 — Natural requirement

Plant Manager:

```text
Create a requirement for 100 KG Aluminium Ingot for raw material, needed one month from today.
```

Assistant creates real requirement, returns ID, assignee, and next action.

Follow-up:

```text
What is its ID?
```

Assistant answers immediately.

## Scene 3 — RFQ

Purchase Executive:

```text
Prepare the supplier request for the latest requirement.
```

Assistant creates real RFQ draft and preview, returns business number and eligible suppliers.

User reviews manual workbench and confirms `Send to suppliers` proposal.

## Scene 4 — Quotations and comparison

Purchase Manager attaches three quotation files:

```text
These are for the latest RFQ. Process them and create the supplier comparison.
```

Assistant shows real processing state, verification needs, then creates comparison when eligible.

Follow-up:

```text
Why did you recommend this supplier?
```

Assistant explains from persisted comparison and sources.

## Scene 5 — Approval and PO

Plant Manager and Purchase Executive receive decision notifications and approve the same frozen version.

Purchase Manager:

```text
Prepare the purchase order for the approved comparison.
```

Assistant creates governed proposal/result with exact state.

## Scene 6 — Manager coordination

Plant Manager:

```text
What is my team waiting on? Follow up on anything overdue.
```

Assistant shows bounded actionable work and creates authorized persisted follow-ups.

## Scene 7 — Inbound

Gate, Store, and Quality roles complete their stages with assistant help and manual verification.

At no point should the demo require:

- raw ID selection;
- opening a task before an exact assistant request;
- repeating known facts;
- interpreting raw JSON;
- manually repairing database state;
- explaining why the chatbot cannot understand a reasonable sentence.

---

# 26. Out of scope for this release

Do not expand implementation into:

- production scheduling optimization;
- machine control;
- autonomous safety decisions;
- payroll/HR;
- accounting ledger replacement;
- unrestricted no-code agent builder;
- foundation-model training;
- multi-region deployment;
- billing/entitlements;
- full live SAP/Oracle rollout beyond existing adapter hardening/tests;
- external supplier portal redesign beyond what the procurement demo needs.

The runtime and task foundations must be reusable for future departments, but procurement and inbound must be completed to production-quality first.

---

# 27. Final completion report format

Codex must finish with exactly these sections:

## Implemented

- concise bullets grouped by runtime, capabilities, UI, coordination, tests.

## Files changed

- exact paths and purpose.

## Migrations and contracts

- migration ID/status;
- OpenAPI generation/check result.

## Verification results

For each command:

```text
PASS / FAIL / NOT RUN — command — key result
```

## Agent evaluation

- deterministic scenario success rate;
- live Groq scorecard result or `NOT RUN — credentials unavailable`;
- unsafe-action count;
- false-success count;
- known weak scenarios.

## Client demo result

- each scene PASS/FAIL;
- screenshot paths;
- exact blocker if any.

## Remaining gaps

Only real remaining gaps. Do not describe planned work as completed.

## Repository safety

Confirm:

- no destructive reset/revert;
- canonical procurement workflow preserved;
- no parallel requirement/agent workflow created;
- tenant/plant/role controls preserved;
- controlled actions remain human-confirmed;
- dirty unrelated worktree changes preserved.

---

# 28. Final definition of done

This upgrade is not done because the assistant uses Groq, because its prose sounds friendly, or because the dashboard looks modern.

It is done when:

1. a user can describe normal role work in ordinary language;
2. the assistant can resolve exact, recent, selected, and relative records;
3. the assistant can use several bounded read tools before one real mutation;
4. task context helps but never unnecessarily gates exact entity-driven work;
5. every supported capability has a direct typed adapter;
6. manual and assistant paths converge on the same canonical services;
7. assistant-created records appear immediately in normal workbenches;
8. the assistant returns real business IDs, documents, job states, blockers, and next actions;
9. controlled consequences remain explicitly confirmed;
10. managers can delegate and follow up through persisted hierarchy-aware work;
11. users see decisions, prepared work, tasks, and risks—not runtime internals;
12. the manual flow exposes one clear next action per state;
13. the exact bad transcripts and their paraphrases pass regression tests;
14. no false success claim, cross-tenant leak, or uncontrolled commercial action occurs;
15. the client demo can be completed from a clean workspace without developer intervention.
