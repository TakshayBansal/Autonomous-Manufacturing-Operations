# GenuineGigs Agentic Manufacturing Platform — Execution Plan

> **Document type:** implementation contract for Codex or another engineering agent  
> **Target release:** Agentic Procurement Workspace v1  
> **Repository:** `C:\Users\Takshay\Desktop\Important\GenuineGigs`  
> **Companion source of truth:** `HANDOFF.md`  
> **Execution mode:** complete the full target release in one continuous implementation pass; do not stop after scaffolding, partial UI work, or a written architecture proposal.

---

## 0. How Codex must use this document

Read `HANDOFF.md` completely before changing any file. Then read this document completely. Treat `HANDOFF.md` as the source of truth for the existing implementation and this file as the source of truth for the next release.

This is not permission to rewrite the repository from scratch. Extend the existing procurement product safely. Preserve the deliberately dirty worktree, existing migrations, generated contracts, tests, document security, and all valid current behavior.

### Mandatory execution behavior

1. Start by running:

   ```powershell
   git status --short
   git diff --check
   docker compose ps
   ```

2. Inspect the existing implementation before creating replacements. Reuse or refactor retained agent, task, permission, document, audit, and workflow code where it is sound.
3. Implement every item marked **REQUIRED FOR THIS RELEASE**.
4. Do not implement items marked **FUTURE EXPANSION** except for clean extension points and documentation.
5. Do not create a second procurement workflow, second requirement model, second approval system, or agent-only shadow records.
6. Keep the manual ERP-style workflow fully usable when AI is unavailable or disabled.
7. Do not use destructive Git commands, delete uncommitted work, squash migrations, hand-edit the generated TypeScript API contract, expose MinIO, or commit secrets.
8. After any API schema change, regenerate and validate the API contract.
9. Run relevant tests after each major layer and the complete test suite at the end. Fix failures caused by the work.
10. Do not leave placeholder buttons, dead navigation items, fake success states, `TODO` implementations, or “coming soon” routes in the target release.
11. If the current code differs from a filename or type named below, adapt the implementation while preserving the specified behavior. Do not pause merely because a class or route has a different name.
12. Finish with a concise implementation report containing changed files, migrations, architectural decisions, test commands and results, and any genuine blockers.

### Definition of “one continuous implementation pass”

Codex must proceed through discovery, backend, migrations, frontend, tests, contract generation, and documentation without asking for approval between phases. When a small ambiguity exists, resolve it using the priorities in this plan:

1. security and tenant isolation;
2. canonical domain integrity;
3. truthful action state;
4. role authority;
5. user clarity;
6. minimal safe change;
7. visual polish.

---

## 1. Product direction

GenuineGigs must evolve from a focused procurement ERP into an **agentic operations platform for manufacturing**, beginning with procurement and inbound material operations.

The product is not intended to replace every ERP, MES, QMS, WMS, CMMS, email system, or document store. It should become the **system of work, coordination, and assistance** above those systems.

### Product thesis

Every plant employee receives a role-specific assistant. Each assistant:

- understands the employee’s role, authority, plant, department, manager, and assigned work;
- can explain tasks and company procedures using trusted sources;
- can prepare operational artifacts from documents and structured records;
- can call the same domain services used by the manual UI;
- can create and delegate governed tasks;
- can request and collect follow-ups through the employee hierarchy;
- can submit prepared work for the correct upstream approvals;
- records every proposed and executed action with evidence;
- never claims an action succeeded without a verified execution receipt;
- never bypasses permissions, approvals, tenant scope, or immutable-document rules.

### First vertical

The complete first vertical is procurement and inbound material operations:

```text
Requirement -> RFQ -> Supplier quotations -> Verified comparison
-> Plant Manager + Purchase Executive approval -> PO
-> Gate entry -> Store receipt -> Quality inspection
```

This release must make the above workflow usable in two equivalent ways:

1. **Structured mode:** forms, tables, filters, previews, and explicit buttons.
2. **Agentic mode:** natural-language requests that call the same canonical services and show reviewable structured results.

Neither mode is secondary. Customers must be able to adopt the product gradually.

---

## 2. Release scope

## 2.1 REQUIRED FOR THIS RELEASE

Deliver an **Agentic Procurement Workspace v1** containing:

- a redesigned professional application shell and responsive design system;
- a role-aware “My Work” home page;
- a persistent contextual assistant workspace, not a floating chatbot;
- governed agent threads attached to a task or business context;
- a canonical task/delegation/follow-up system based on the existing `Task` model;
- hierarchy-aware delegation and manager visibility;
- typed agent tools that call existing procurement domain services;
- quotation-document assistance culminating in a verified comparison artifact;
- agent-assisted requirement and RFQ drafting;
- agent-assisted approval summaries and PO preparation;
- source citations, extraction confidence, calculation evidence, action proposals, approval interruptions, and execution receipts;
- durable agent run state and resumable human-in-the-loop actions;
- role and action policy controls;
- provider health, limited mode, emergency stop, and feature flags;
- agent activity and audit visibility;
- deterministic/manual fallbacks when the model provider is absent;
- complete API, unit, integration, and Playwright coverage for the release;
- updated product, architecture, acceptance, and runbook documentation.

## 2.2 FUTURE EXPANSION — DO NOT BUILD FULL MODULES NOW

Create clean abstractions but do not build full production modules for:

- production planning and scheduling;
- machine control or automated safety-critical actions;
- predictive maintenance;
- comprehensive inventory planning;
- finance, invoicing, payments, or payroll;
- live SAP/Oracle writes;
- autonomous supplier negotiation;
- external supplier portal rollout;
- plant IoT ingestion;
- multi-region deployment;
- generic no-code agent builders;
- unrestricted agent-to-agent conversations.

The current Gate, Store, and Quality workflow remains supported and should receive UI consistency improvements, but procurement is the agentic showcase.

---

## 3. Non-negotiable invariants

The following are hard constraints. Add tests where necessary.

1. `PurchaseRequirement` remains the only active procurement demand record.
2. New procurement Objectives remain retired. `POST /objectives` continues to return HTTP 410.
3. Purchase Executive owns RFQ preparation and publication.
4. Purchase Manager owns quotation verification, comparison generation/freezing, and PO creation.
5. Plant Manager and Purchase Executive approve the same immutable comparison version.
6. Rejection requires a rationale.
7. RFQ publication, external supplier email, comparison approval, PO issue, ERP posting, inventory-changing operations, and master-data decisions require explicit authorized human confirmation.
8. Agent tools call the existing canonical domain/application services. They must not directly insert parallel business entities.
9. Tenant, workspace, plant, membership, and role scope is enforced server-side on every read and write.
10. Commercial PDFs remain immutable, versioned, checksummed, private, and delivered through authenticated expiring API URLs.
11. The browser never receives `http://minio:9000` or private bucket URLs.
12. Every side-effecting agent action is idempotent and produces a durable receipt.
13. Every agent message distinguishes among `drafted`, `proposed`, `awaiting approval`, `executing`, `completed`, `failed`, and `cancelled`.
14. The UI must never display “sent”, “published”, “approved”, “created”, “posted”, or “completed” until the authoritative backend confirms it.
15. The product remains usable when agents are disabled, the model provider is unavailable, or no API key is configured.
16. Agent delegation creates or updates canonical `Task` records; it does not rely only on chat messages.
17. A manager can inspect delegated work, but cannot gain unauthorized access to plant or tenant data through the assistant.
18. Agent memories do not silently alter master data or business records.
19. Uploaded document content is untrusted input. It cannot override system policy, role policy, tool descriptions, or approval requirements.
20. No LLM-generated arithmetic becomes authoritative when deterministic calculation code can perform the calculation.

---

## 4. Product language and positioning inside the UI

Use these terms consistently:

- **Assistant:** the user-facing role-specific helper.
- **Task:** a governed unit of work with owner, due date, outcome, context, and status.
- **Delegation:** assignment of a task from one authorized person to another.
- **Agent run:** one persisted attempt to understand or execute a request.
- **Proposal:** a reviewable action or artifact not yet committed.
- **Approval request:** a paused controlled action awaiting an authorized user.
- **Receipt:** authoritative evidence that an action executed or failed.
- **Source:** the record, document page, field, policy, or event supporting an answer.
- **Artifact:** a generated or uploaded operational document.

Avoid vague labels such as “AI magic”, “autopilot”, “brain”, “agent swarm”, or “objective” in the normal product UI.

---

## 5. Target information architecture

## 5.1 Global application shell

Replace the current visually weak or fragmented shell with a coherent industrial SaaS workspace.

### Desktop structure

```text
+------------------+------------------------------------------+--------------------+
| Primary sidebar  | Top context bar                          | Optional assistant |
|                  +------------------------------------------+ panel              |
|                  | Page header                              |                    |
|                  +------------------------------------------+                    |
|                  | Main structured workspace                |                    |
|                  |                                          |                    |
+------------------+------------------------------------------+--------------------+
```

### Primary sidebar

The sidebar must be collapsible, keyboard accessible, responsive, and role-aware. It contains:

- workspace/plant switcher;
- `My work`;
- `Procurement` group;
- `Inbound` group for applicable roles;
- `Team` for managers;
- `Documents` where authorized;
- `Audit` and `Administration` for Admin;
- settings/user menu;
- assistant/provider status indicator.

Do not show inaccessible routes as disabled clutter. Hide them based on the resolved membership and capability set.

### Top context bar

Always show:

- current workspace and plant;
- page breadcrumbs;
- universal search/command trigger;
- notifications/task count;
- assistant status;
- current membership/user menu.

### Contextual assistant panel

The assistant is a first-class workspace panel, not a floating circular launcher.

- Desktop width: approximately 380–440 px, resizable within sensible bounds.
- Closed state: a clear `Open assistant` control in the top bar with current task context.
- Tablet: overlay sheet.
- Mobile: full-height bottom sheet or dedicated route.
- Preserve the selected business context when opening and closing the panel.
- Do not obscure critical forms or approval actions.
- The assistant panel can be opened globally, but action capabilities are constrained by the active role and context.

## 5.2 Role-aware navigation

### Plant Manager

- My work
- Requirements
- Approvals
- Team
- Documents

### Purchase Executive

- My work
- Requirements
- RFQs
- Approvals
- Suppliers where currently authorized
- Documents

### Purchase Manager

- My work
- Supplier quotations
- Comparisons
- Purchase orders
- Team where applicable
- Documents

### Gate Operator

- My work
- Gate entries
- Expected deliveries

### Store Manager

- My work
- Store receipts
- Receipt exceptions

### Quality Inspector

- My work
- Quality inspections
- Held/rejected materials

### Admin

- Control centre
- Workspace setup
- People and hierarchy
- Materials
- Suppliers and capabilities
- Agent policies
- Knowledge
- Provider health
- Audit

---

## 6. UI and visual design system

## 6.1 Design intent

The product should feel like a modern industrial operations platform: calm, information-dense without being crowded, trustworthy, and suitable for daily use on plant desktops and tablets.

Do not imitate a consumer chat app. Do not use excessive gradients, glowing effects, oversized rounded cards, decorative AI illustrations, or large empty hero sections in authenticated product screens.

## 6.2 Foundation

Use the existing frontend stack and Tailwind configuration. Inspect installed component libraries before adding dependencies. Prefer reusable local primitives built on the existing React/Tailwind/Radix stack. If shadcn-style components are already present or compatible, use source-owned components rather than introducing a heavy runtime UI package.

Create or standardize:

- typography scale;
- spacing scale;
- page width and gutters;
- semantic surface tokens;
- border and radius tokens;
- focus rings;
- shadow levels;
- semantic status colors;
- table density modes;
- icon size rules;
- animation duration and reduced-motion behavior.

### Semantic status system

Use consistent meanings across the app:

- neutral/draft;
- informational/in progress;
- warning/needs attention;
- success/completed or approved;
- destructive/rejected or failed;
- held/awaiting review;
- agent/proposal state distinct from business approval state.

Never use color as the only status indicator. Pair color with label, icon, and accessible text.

## 6.3 Reusable components

Create a coherent component layer, including at minimum:

- `AppSidebar`;
- `WorkspaceSwitcher`;
- `TopContextBar`;
- `PageHeader`;
- `RoleBadge`;
- `StatusBadge`;
- `MetricCard`;
- `ProcessStepper`;
- `DataTable` with sorting, filters, pagination, empty state, and row actions;
- `FilterBar`;
- `DetailDrawer` or `DetailPanel`;
- `Timeline`;
- `ActivityFeed`;
- `DocumentPreviewCard`;
- `SourceCitation`;
- `ConfidenceBadge`;
- `ApprovalBanner`;
- `ActionProposalCard`;
- `ActionReceiptCard`;
- `TaskCard`;
- `TaskStatusMenu`;
- `AssigneePicker`;
- `DueDatePicker`;
- `AssistantPanel`;
- `AssistantComposer`;
- `AssistantMessage` with typed blocks;
- `AgentRunProgress`;
- `EmptyState`;
- `InlineError`;
- `Skeleton`;
- `ConfirmControlledActionDialog`;
- `CommandPalette`.

## 6.4 Page behavior standards

Every primary screen must include:

- clear page title and role-appropriate description;
- primary action in a predictable location;
- status summary or metrics only when actionable;
- search and filters for list views;
- empty, loading, error, and permission-denied states;
- responsive table/card transformation;
- keyboard focus and screen-reader labels;
- direct links to related requirement, RFQ, quote, comparison, PO, receipt, inspection, task, and document records;
- no horizontal overflow at tested breakpoints.

## 6.5 Accessibility and responsiveness

Meet WCAG 2.2 AA where practical:

- visible focus states;
- semantic headings and landmarks;
- keyboard-operable menus, dialogs, drawers, tables, and assistant controls;
- accessible labels for icon-only controls;
- sufficient contrast;
- reduced-motion support;
- polite live regions for agent streaming and task status changes;
- no time-sensitive interaction that cannot be resumed.

Maintain Playwright coverage for desktop, tablet, and mobile.

---

## 7. Core user experiences

## 7.1 My Work — REQUIRED

Create a role-aware landing page after login/workspace selection.

### Sections

1. **Needs my action**
   - approvals;
   - extraction verification;
   - controlled agent proposals;
   - rejected work needing revision;
   - overdue tasks.

2. **My tasks**
   - assigned to me;
   - due soon;
   - in progress;
   - blocked;
   - completed recently.

3. **Delegated by me** for managers
   - status;
   - assignee;
   - last update;
   - due date;
   - follow-up/escalation state.

4. **Operational exceptions** relevant to the role
   - missing quotations;
   - approaching RFQ deadlines;
   - comparison approval delays;
   - delayed expected deliveries;
   - quality holds.

5. **Assistant briefing**
   - a deterministic summary assembled from canonical records;
   - optional model-generated explanation only when provider is available;
   - every item links to evidence.

### Quick commands

Role-specific examples:

- “Create a purchase requirement”;
- “Prepare an RFQ from this requirement”;
- “Compare these quotations”;
- “What needs my approval?”;
- “Follow up on overdue RFQs”;
- “Show tasks delegated by me”;
- “Explain why this material is held”.

## 7.2 Procurement record workbench — REQUIRED

Every major procurement record should open in a consistent workbench layout:

```text
Header: identifier, status, owner, due date, primary controlled action
Tabs: Overview | Documents | Tasks | Activity | Agent runs
Main: structured record details and domain-specific work
Right panel: related records / contextual assistant
```

Use a clear process stepper showing the authoritative current stage. The process stepper is navigation and status, not a fake linear wizard; users can inspect previous stages without mutating them.

## 7.3 Requirement workbench — REQUIRED

Improve requirement creation and detail pages:

- multi-line material entry;
- approved material search;
- UOM and quantity validation;
- need-by date and inspection requirement;
- named Purchase Executive;
- specification and reason;
- missing-material master request flow;
- save draft and submit behavior if supported by current domain rules;
- assistant can draft fields from natural language but must show a structured preview;
- unresolved or low-confidence fields require user review;
- agent action uses the canonical requirement creation service.

Example assistant flow:

> “We need 5,000 Bearing 6205 units by August 12 for Line 3. Assign Priya.”

The assistant must resolve approved material and assignee, display the exact proposed requirement lines, highlight unresolved values, and require confirmation before creating the requirement.

## 7.4 RFQ workbench — REQUIRED

- supplier capability filters;
- approved supplier selection;
- selected supplier summary;
- RFQ line and commercial-term preview;
- PDF preview/download;
- explicit publication confirmation;
- publication receipt;
- timeline of supplier responses;
- agent can recommend suppliers with transparent reasons;
- agent can draft RFQ terms but cannot publish automatically.

## 7.5 Supplier Quotations workspace — REQUIRED AND HIGHEST PRIORITY

This is the flagship agentic experience.

### Layout

- left/main: quotation list and upload area;
- center/detail: selected quote, extracted fields, evidence, validation state;
- optional right: assistant panel;
- clear requirement and RFQ context at the top.

### Upload and processing

Support existing PDF/image/XLSX behavior. Improve:

- drag-and-drop and file picker;
- per-file processing state;
- duplicate detection where possible;
- extraction progress;
- unsupported/corrupt file errors;
- clear quarantine/validation state;
- source page/evidence navigation;
- reprocess action;
- document download through secure API URLs only.

### Extraction review

Display fields in a review table:

- extracted value;
- normalized value;
- source page/region or worksheet reference;
- confidence;
- validation rule result;
- user correction control;
- correction history.

Required commercial and technical fields include the existing canonical fields plus terms available in the document, such as:

- quotation number and date;
- supplier;
- material/line mapping;
- quantity and UOM;
- unit price;
- tax;
- freight/packing or explicit absence;
- delivery date/lead time;
- payment terms;
- quotation validity;
- specification deviations;
- warranty where present;
- total and normalized landed cost.

Use deterministic normalization and calculation services. The model may map labels and explain anomalies, but it must not become the source of truth for totals.

### Assisted verification

The assistant can:

- explain extracted fields;
- flag missing or inconsistent terms;
- compare against RFQ requirements;
- map quotation lines to requirement lines;
- propose corrections;
- identify low-confidence values;
- prepare a verification checklist.

The Purchase Manager remains the verifier.

## 7.6 Comparison workbench — REQUIRED AND HIGHEST PRIORITY

Create an approval-grade comparison experience.

### Comparison table

- one supplier per column or a responsive equivalent;
- one criterion per row;
- normalized landed cost;
- taxes/freight/packing breakdown;
- delivery date or lead time;
- payment terms;
- validity;
- specification compliance/deviation;
- supplier capability/approval state;
- prior performance fields only when backed by actual data;
- missing data clearly marked;
- source citation per material value;
- deterministic calculations;
- selected/recommended supplier state distinct from approved award state.

### Assistant output

The assistant can produce:

- concise executive summary;
- cheapest option;
- earliest delivery option;
- compliance risks;
- commercial risks;
- missing-information list;
- recommendation with reasons and counter-risks;
- questions to send back to suppliers;
- approval package draft.

It must never invent supplier history or silently choose a supplier. If performance data does not exist, state that it is unavailable.

### Freeze and approval

- user reviews and edits allowed fields;
- Purchase Manager explicitly freezes/submits a comparison version;
- frozen version becomes immutable;
- Plant Manager and Purchase Executive receive the same version;
- approval UI shows summary, sources, deviations, and artifact link;
- rejection requires rationale;
- approvals produce authoritative receipts and activity entries;
- any material change after rejection creates a new comparison version.

## 7.7 Purchase Order workbench — REQUIRED

- show source requirement, RFQ, quotes, comparison version, and approvals;
- PO preview and immutable PDF;
- creation confirmation after both approvals;
- separate states for draft/prepared, confirmed/issued, emailed, and ERP-posted;
- external email or ERP posting requires explicit confirmation and feature availability;
- agent may draft or prepare, but cannot claim issue/send/post without receipt.

## 7.8 Inbound workspaces — REQUIRED UI CONSISTENCY

Retain canonical backend separation for Gate and Store.

Improve:

- expected delivery context;
- PO and document links;
- concise structured entry forms;
- discrepancy callouts;
- activity timeline;
- responsive layout;
- handoff context between Gate, Store, and Quality.

Agentic functionality can remain limited to explanation, field drafting, document extraction assistance, and task reminders in this release. Do not implement autonomous inventory changes.

## 7.9 Team and hierarchy — REQUIRED FOR MANAGERS/ADMIN

Create a professional organization view using existing memberships and roles.

### Capabilities

- show current plant hierarchy;
- show role, person, manager, status, and workload counts;
- manager sees direct reports and delegated task status;
- Admin can configure reporting relationships within valid membership/role rules;
- delegation picker uses this hierarchy;
- no cross-tenant or cross-plant leakage;
- no visual “agent clones” detached from employees—the assistant is attached to a membership/person.

## 7.10 Agent activity and audit — REQUIRED

Authorized users must be able to inspect:

- user request;
- resolved context;
- agent run status;
- model/provider used;
- tools proposed and called;
- action approvals;
- execution receipts;
- artifacts generated;
- errors/retries;
- timestamps and actor identities;
- source citations;
- redacted prompt/response metadata according to policy.

Do not expose secrets, full sensitive prompts, signed document tokens, or private storage URLs.

---

## 8. Assistant interaction model

## 8.1 Context, not generic chat

Every assistant turn must have a clearly resolved context:

- workspace;
- plant;
- membership;
- role and capabilities;
- active route;
- optional canonical business entity;
- optional task;
- selected documents;
- current thread.

Show active context near the composer, for example:

```text
Purchase Manager Assistant
Context: RFQ RFQ-014 · Requirement PR-028 · 3 quotations
```

Users can remove or change context explicitly. The assistant must not silently switch to an unrelated requirement.

## 8.2 Thread rules

- A thread is scoped to a membership and workspace.
- Prefer one thread per task or business context.
- Generic personal threads may answer questions but cannot perform context-sensitive writes until context is resolved.
- Thread titles are generated from the canonical outcome, not casual first-message text.
- Archive old threads rather than deleting audit-relevant history.
- Do not use conversation history as the source of truth for business fields; re-read canonical records before proposing an action.

## 8.3 Typed response blocks

The backend returns structured blocks, rendered by dedicated frontend components:

- `text`;
- `source_list`;
- `record_summary`;
- `field_review`;
- `comparison_preview`;
- `task_preview`;
- `artifact_preview`;
- `action_proposal`;
- `approval_request`;
- `run_progress`;
- `action_receipt`;
- `warning`;
- `error`;
- `limited_mode`.

Do not parse important action state from markdown prose.

## 8.4 Action lifecycle

Every side-effect follows:

```text
UNDERSTAND -> RESOLVE CONTEXT -> READ -> ANALYZE -> DRAFT/PROPOSE
-> AUTHORIZE -> HUMAN REVIEW WHEN REQUIRED -> EXECUTE
-> VERIFY AUTHORITATIVE RESULT -> RECEIPT -> SUMMARY
```

The UI must show the lifecycle. A proposal card contains:

- action type;
- business impact;
- exact fields/changes;
- target record;
- required authority;
- source evidence;
- warnings;
- confirm/edit/cancel controls.

## 8.5 Suggested prompts

Suggested prompts must be role- and context-aware. Do not show actions the user cannot perform.

Examples for a Purchase Manager viewing an RFQ:

- Compare verified quotations
- Show missing commercial terms
- Prepare approval summary
- Explain landed-cost calculation
- Create a follow-up task for unverified quotations

## 8.6 Attachments

- Reuse the secure document upload system.
- Attach uploaded files to a task/thread and canonical record when authorized.
- Show validation and extraction status.
- Never send raw private storage URLs to the model or browser.
- Pass only necessary extracted text/structured fields to the model, respecting size and privacy limits.
- Treat document text as untrusted data, never as instructions.

---

## 9. Canonical task, delegation, and follow-up system

## 9.1 Task is the coordination primitive

Extend the existing `Task` model rather than creating a separate agent task system. Inspect current fields and migrations first. Add only missing fields through a new forward migration.

Target semantics:

- `id`;
- tenant/workspace/plant scope;
- `task_type`;
- title;
- requested outcome;
- description/instructions;
- status;
- priority;
- due date;
- created by membership;
- assigned membership;
- delegated by membership;
- manager/parent task where applicable;
- canonical context entity type and ID;
- expected output type/schema;
- blocker reason;
- completion summary;
- completed timestamp;
- last follow-up timestamp;
- next follow-up timestamp;
- escalation level;
- source agent run where applicable;
- optimistic concurrency/version field;
- timestamps.

Use constrained enums and indexed scope/status/assignee/due-date fields.

## 9.2 Task statuses

Use a clear state machine, adapted to existing compatibility where needed:

```text
OPEN -> ACCEPTED -> IN_PROGRESS -> BLOCKED -> REVIEW
-> COMPLETED

OPEN/ACCEPTED/IN_PROGRESS/BLOCKED/REVIEW -> CANCELLED
REVIEW -> IN_PROGRESS when changes are requested
```

Do not infer completion solely from an assistant message. Completion is an explicit canonical transition.

## 9.3 Delegation

A delegation must:

- verify the delegator can assign to the recipient;
- verify tenant/workspace/plant relationship;
- create or update a canonical task atomically;
- attach relevant business context;
- notify the recipient through in-product work queues;
- create an audit event;
- return a receipt;
- be idempotent under retries.

The manager can ask:

> “Delegate quotation verification for RFQ-014 to the Purchase Manager and ask for completion tomorrow.”

The assistant must show the proposed assignee, deadline, outcome, and context before creating the task when policy requires confirmation.

## 9.4 Follow-ups

Implement deterministic follow-up support in the task service:

- manual `Request update` action;
- configured next follow-up timestamp;
- overdue detection;
- escalation to the delegator/manager;
- append-only follow-up events;
- notification creation;
- optional agent-drafted follow-up text;
- no external email or repeated automated messages without policy and explicit enablement.

A scheduled worker may identify due follow-ups and create notifications/tasks. It must not send uncontrolled external communications.

## 9.5 Manager visibility

Managers see:

- direct reports’ task counts;
- overdue and blocked tasks;
- last meaningful update;
- due date;
- escalation state;
- linked business context.

Managers do not receive unrestricted access to unrelated private content. Use existing role and hierarchy policy.

---

## 10. Agent architecture

## 10.1 Framework decision

Retain and rationalize the existing **LangGraph-based** infrastructure. Do not introduce a second orchestration framework for the same runtime.

Use LangGraph for:

- explicit state machines;
- durable run checkpoints;
- resumable human-in-the-loop interruptions;
- streaming progress/events;
- bounded subgraphs for specialized workflows;
- fault recovery.

Use ordinary Python application services for deterministic business logic. LangGraph orchestrates; it does not own procurement rules.

### Do not use

- an unrestricted autonomous loop;
- free-form agent-to-agent chat as a business protocol;
- one separate process/runtime per employee;
- direct database writes from model-selected tools;
- multiple competing agent SDKs in the same release;
- MCP as the internal domain-service layer.

### MCP position

MCP may be added later as an external integration adapter for approved third-party systems. It is not required for this release. Current internal capabilities should remain typed local tools over the canonical service layer, which preserves identity, authorization, transactions, and auditability.

### Framework evaluation and decision record

Do not leave the framework choice open for the implementation agent. Use the following decision record:

| Technology | Decision for this release | Reason |
| --- | --- | --- |
| LangGraph | **Use and consolidate** | It already exists in the repository and fits explicit state machines, persistence, streaming, and human approval interruptions. |
| Pydantic models | **Use heavily** | Use for tool inputs/results, graph state boundaries, API schemas, proposals, receipts, and validation. |
| FastAPI application services | **Use as the domain boundary** | Business rules, authorization, transactions, calculations, and canonical writes belong here, outside model reasoning. |
| Celery/worker/beat or current job runner | **Use where already present** | Use for document extraction, due follow-up scans, and long-running jobs; do not make the LLM runtime a scheduler. |
| OpenAI Agents SDK | **Do not add** | Adding another orchestration runtime would duplicate LangGraph and complicate the existing Groq/OpenAI-compatible provider strategy. |
| CrewAI | **Do not add** | Role-playing agent crews are not the business hierarchy or transaction model needed here; canonical tasks provide coordination. |
| AutoGen | **Do not add** | Free-form multi-agent conversations would create a second coordination model and weaken deterministic control. |
| PydanticAI | **Do not add as a second runtime** | Pydantic validation is useful, but a second agent framework is unnecessary while LangGraph remains the orchestrator. |
| MCP | **Future external adapter only** | Useful for standard third-party tool integration, but internal canonical services need direct identity, transaction, policy, and audit control. |
| Custom autonomous loop | **Prohibited** | Unbounded planning/tool loops are unsuitable for controlled procurement actions. |

This is a deliberate single-runtime architecture. Do not add a framework merely because it offers a chat abstraction or “multi-agent” terminology.

## 10.2 Logical architecture

```text
Next.js UI
  -> Agent API / SSE event stream
    -> Agent Run Service
      -> LangGraph role workflow
        -> Context Resolver
        -> Policy Engine
        -> Retrieval Services
        -> Typed Tool Registry
          -> Canonical Procurement/Task/Document Services
            -> Database / MinIO / simulated integrations
      -> Agent Event + Receipt Store
```

## 10.3 One role-aware runtime, not fake independent employees

Represent an assistant configuration for each membership/role, but use shared tested graphs and tools.

Runtime inputs include:

- membership and resolved capabilities;
- role profile;
- hierarchy context;
- workspace/plant;
- active record/task/document context;
- policy configuration;
- provider configuration.

This provides personal assistants without duplicating code or allowing agents to drift into ungoverned personalities.

## 10.4 Graph design

Implement a primary role-assistant graph with bounded specialist subgraphs.

### Primary graph state

Include typed fields such as:

- `run_id`;
- `thread_id`;
- `membership_id`;
- `workspace_id`;
- `plant_id`;
- `role`;
- `capabilities`;
- `user_message`;
- `active_context`;
- `selected_document_ids`;
- `resolved_entities`;
- `intent`;
- `requested_outcome`;
- `retrieved_sources`;
- `plan_steps`;
- `tool_calls`;
- `proposal`;
- `approval_state`;
- `receipts`;
- `artifacts`;
- `warnings`;
- `final_blocks`;
- `error_state`.

### Primary graph nodes

1. `validate_request`
2. `resolve_identity_and_context`
3. `classify_intent`
4. `load_authoritative_records`
5. `retrieve_policy_and_knowledge`
6. `select_bounded_workflow`
7. `prepare_plan`
8. `execute_read_or_analysis_tools`
9. `validate_result`
10. `build_proposal`
11. `policy_gate`
12. `human_interrupt` when required
13. `execute_action`
14. `verify_receipt`
15. `build_typed_response`
16. `persist_summary_and_metrics`

Routing must be deterministic where intent or context maps to a known workflow.

### Specialist subgraphs for this release

- requirement drafting;
- RFQ preparation;
- quotation extraction review assistance;
- quotation comparison preparation;
- approval summary;
- PO preparation;
- task delegation;
- task status/follow-up;
- knowledge/SOP explanation.

Do not create specialist subgraphs for future plant modules yet.

## 10.5 Persistence and memory

Use durable production persistence. Do not rely on in-memory checkpointers outside tests.

### Short-term run/thread state

- use a database-backed LangGraph checkpointer compatible with the deployed database;
- stable UUID `thread_id` and `run_id` values;
- retention policy for old checkpoints;
- resume interrupted runs using the same thread identity;
- ensure operations before an interrupt are idempotent because nodes may re-run after resume.

### Long-term memory

Long-term memory is limited to explicit, governed facts:

- user display preferences;
- role-specific recurring preferences where allowed;
- approved company terminology;
- confirmed mapping hints;
- task summaries;
- prior correction patterns with provenance.

Do not store an LLM’s unverified inference as a fact. Every durable memory has:

- scope;
- source;
- creator;
- confidence/status;
- created/updated timestamps;
- optional expiry;
- delete/disable control.

Business data remains in canonical tables and is reloaded from them.

## 10.6 Provider abstraction

Create or consolidate a model-provider interface supporting:

- the current Groq/OpenAI-compatible provider configuration;
- a fast model for classification/extraction assistance;
- a stronger model for complex summaries when configured;
- structured output validation;
- timeouts and retries;
- circuit breaker/health state;
- token and latency metrics;
- deterministic limited mode.

Do not hard-code one model name throughout the domain layer. Keep provider/model choices in configuration and policy.

When no provider is available:

- canonical manual workflows continue;
- deterministic summaries and record lookups continue;
- agent UI clearly displays limited mode;
- unsupported generative actions are disabled or return an honest limitation;
- no fake generated output is presented.

## 10.7 Typed tool registry

Every tool requires:

- stable tool name and version;
- Pydantic input schema;
- typed result schema;
- natural-language purpose;
- required capability;
- allowed roles;
- action risk class;
- tenant/plant scoping behavior;
- whether human confirmation is mandatory;
- idempotency behavior;
- timeout/retry policy;
- audit behavior;
- test coverage.

### Tool categories

#### Read

- get current user and hierarchy;
- get assigned work;
- get requirement/RFQ/quote/comparison/PO;
- list relevant suppliers and capabilities;
- read document extraction/evidence;
- search approved knowledge;
- read task/delegation status.

#### Analyze

- validate requirement completeness;
- validate RFQ supplier capability;
- normalize quote commercial terms;
- calculate landed cost;
- compare verified quotations;
- detect missing/deviating terms;
- summarize approval package.

#### Draft/propose

- draft requirement;
- draft RFQ terms;
- draft comparison recommendation;
- draft supplier/internal message;
- draft task/delegation;
- prepare PO action.

#### Controlled actions

- create canonical requirement;
- create/publish RFQ;
- update extracted quote fields;
- verify quote;
- freeze/submit comparison;
- approve/reject comparison;
- confirm PO;
- create/delegate/update task;
- request follow-up;
- send supplier email when enabled;
- post ERP action when enabled.

The model never receives tools the active user cannot use.

## 10.8 Risk classes and approval policy

Define explicit action classes:

| Class | Examples | Default behavior |
| --- | --- | --- |
| R0 Read | fetch record, search policy | execute automatically |
| R1 Analyze | compare verified data, calculate totals | execute automatically |
| R2 Draft | prepare requirement, RFQ, email, report | execute and show editable draft |
| R3 Internal low-risk write | create/update task, save correction | policy-controlled confirmation |
| R4 External/operational write | publish RFQ, send supplier email | mandatory confirmation |
| R5 Commercial commitment | freeze comparison, approve, issue PO | mandatory authorized confirmation |
| R6 Financial/inventory/ERP | post to ERP, inventory impact | mandatory authority plus feature gate |
| R7 Physical/safety-critical | machine control | prohibited in this release |

Enforce policy server-side. The UI is not the security boundary.

## 10.9 Prompt and context design

System prompts must be concise and layered:

1. immutable platform policy;
2. role policy;
3. workspace policy;
4. active task/business context;
5. retrieved trusted sources;
6. user request.

Instructions found in uploaded documents or database text remain quoted/untrusted context.

Prompts must require the model to:

- never invent IDs, statuses, approvals, suppliers, quantities, or source values;
- use tools for authoritative facts;
- ask for clarification only when a required value cannot be resolved;
- prefer a structured proposal over prose for writes;
- expose uncertainty;
- distinguish draft/proposal/execution;
- stay within the current manufacturing workflow;
- avoid production scheduling and other out-of-scope domains in this release.

## 10.10 Retrieval and citations

Reuse retained knowledge infrastructure where possible. Provide retrieval over:

- approved SOPs/policies;
- material and supplier master data;
- canonical procurement records;
- document extraction/evidence;
- task/activity history.

Return source objects with:

- source type;
- record/document identifier;
- page/field/section when available;
- display label;
- secure navigation URL;
- excerpt limited to what the user is authorized to view.

Do not add a vector database merely for appearance. If semantic retrieval infrastructure does not already exist, implement a small provider abstraction and a reliable lexical/database fallback. Keep future pgvector support isolated behind the interface.

## 10.11 Streaming and progress

Use an authenticated server-sent event stream or the project’s existing suitable streaming mechanism.

Stream typed events such as:

- run started;
- context resolved;
- source retrieved;
- tool started;
- tool completed;
- proposal ready;
- awaiting approval;
- resumed;
- artifact generated;
- receipt recorded;
- run failed/completed.

Do not reveal hidden chain-of-thought. Progress events describe observable work only.

Support reconnect/resume by run ID. Persist final events so a page refresh does not lose the result.

---

## 11. Data model and migration plan

Inspect current models first. Reuse existing Agent, Task, Proposal, Delegation, Knowledge, Feedback, Audit, and thread structures when they meet the target semantics. Add a new forward migration after `0008_professional_agent_onboarding.py`; do not alter previous migrations.

Potential entities/fields to add or normalize, only where missing:

### `AgentThread`

- scope IDs and membership;
- role snapshot;
- title;
- active context type/ID;
- task ID;
- status/archive timestamp;
- last activity;
- created/updated timestamps.

### `AgentRun`

- thread ID;
- initiating membership;
- provider/model;
- status;
- intent;
- requested outcome;
- active context snapshot;
- started/completed timestamps;
- token/latency/cost metadata;
- error code and safe message;
- correlation/trace ID.

### `AgentEvent`

- run ID;
- sequence;
- event type;
- safe structured payload;
- visibility policy;
- timestamp.

### `AgentProposal`

- run ID;
- action type/version;
- target type/ID;
- exact proposed payload;
- risk class;
- required capability;
- status;
- expires at;
- approved/rejected by and timestamp;
- rejection rationale;
- idempotency key.

### `AgentActionReceipt`

- proposal/run ID;
- tool/action type;
- status;
- target type/ID;
- authoritative result reference;
- safe result summary;
- error code;
- executed by membership/system actor;
- started/completed timestamps;
- idempotency key.

### `AgentArtifactLink`

Prefer linking existing `GeneratedArtifact` and `Document` records rather than duplicating file storage.

### `Task` extensions

Add missing fields described in Section 9.

### `HierarchyRelationship` only if required

If the current membership/role data cannot represent a manager relationship, add a scoped reporting relationship model with validity dates and audit history. Do not infer reporting hierarchy solely from role names when an explicit relationship is available.

### Indexes and constraints

Add:

- tenant/workspace/plant composite indexes;
- run/thread/status indexes;
- task assignee/status/due-date indexes;
- proposal status/expiry indexes;
- unique idempotency constraints;
- foreign keys and cascade behavior that preserve audit history;
- check constraints for valid states where supported.

Migration must work against both a fresh database and the existing development database.

---

## 12. API design

Prefer a coherent new versioned agent API or cleanly consolidate existing `/agent/*` and `/agents/actions` behavior without breaking retained compatibility. Do not expose duplicate ways to perform the same uncontrolled action.

Suggested API surface, adapted to existing conventions:

### Assistant/thread

- `GET /agent/v2/config`
- `GET /agent/v2/threads`
- `POST /agent/v2/threads`
- `GET /agent/v2/threads/{thread_id}`
- `POST /agent/v2/threads/{thread_id}/messages`
- `POST /agent/v2/threads/{thread_id}/archive`

### Runs/events

- `GET /agent/v2/runs/{run_id}`
- `GET /agent/v2/runs/{run_id}/events`
- `POST /agent/v2/runs/{run_id}/cancel`

### Proposals and interruptions

- `GET /agent/v2/proposals/{proposal_id}`
- `POST /agent/v2/proposals/{proposal_id}/approve`
- `POST /agent/v2/proposals/{proposal_id}/reject`
- `POST /agent/v2/proposals/{proposal_id}/edit-and-approve`

### Tasks

Use or improve canonical task endpoints:

- task list/detail/create;
- delegate/reassign;
- accept/start/block/submit/complete/cancel;
- request update;
- add update/comment;
- manager/direct-report summary.

### Knowledge/admin

- list/upload/approve/archive knowledge documents where retained infrastructure supports it;
- agent policy read/update for Admin;
- provider health;
- workspace agent enablement;
- emergency stop;
- audit queries.

### API requirements

- Pydantic request/response models;
- generated OpenAPI contract;
- CSRF/session/auth consistency;
- rate limits for assistant messages and side effects;
- pagination;
- safe error codes;
- no raw model exceptions;
- no secrets or private URLs;
- idempotency key support for controlled actions;
- tests for role and tenant denial.

---

## 13. Frontend implementation plan

## 13.1 Refactor strategy

Start from:

- `apps/web/components/industrial/IndustrialConsole.tsx`;
- `apps/web/components/features/WorkflowForms.tsx`;
- `apps/web/app/globals.css`;
- `apps/web/lib/api.ts`;
- retained `AgentDrawer.tsx` and `AgentWorkspace.tsx`;
- existing role workflow routes and tests.

Do not keep a monolithic console component. Extract shell, navigation, page layout, tables, workbench, task, and assistant components into focused modules.

A sensible structure is:

```text
apps/web/components/
  shell/
  design-system/
  assistant/
  tasks/
  procurement/
  inbound/
  documents/
  audit/
```

Adapt to existing conventions rather than forcing this exact tree when it conflicts with the repository.

## 13.2 Assistant panel states

Implement and test:

- closed;
- ready;
- limited mode;
- composing;
- uploading;
- streaming;
- proposal ready;
- awaiting approval;
- action executing;
- completed with receipt;
- failed with retry guidance;
- cancelled;
- provider unavailable;
- permission denied.

## 13.3 Message rendering

Use typed components. Markdown may be used for explanatory text, but never for executable controls or authoritative state.

Sources open the canonical record or secure document preview. Proposal and receipt cards remain visible in thread history after refresh.

## 13.4 Command palette

Add a universal keyboard-accessible command palette for:

- navigation;
- record search;
- create requirement where authorized;
- open assistant;
- open task;
- go to pending approvals;
- quick role-allowed actions.

It must not bypass confirmation rules.

## 13.5 Notifications

Create a compact in-product notification/task surface for:

- assigned task;
- update requested;
- task overdue/escalated;
- approval requested;
- proposal awaiting review;
- quotation extraction completed/failed;
- action completed/failed.

Notifications link to the exact task, proposal, record, or run.

## 13.6 URL and state behavior

- important filters and selected records should survive refresh through URL state where appropriate;
- direct links to records work after login/workspace resolution;
- assistant context is reconstructable from route and query parameters without leaking sensitive data;
- thread/run IDs may be in URLs when authorized;
- do not put signed document tokens in durable browser history beyond existing secure content behavior.

---

## 14. Procurement agent tool flows

## 14.1 Natural language to requirement

1. Parse requested outcome and candidate fields.
2. Resolve material from approved master data.
3. Resolve UOM and assignee.
4. Validate quantity/date/specification.
5. Present a structured proposal.
6. Confirm when required.
7. Call canonical requirement service.
8. Reload authoritative record.
9. Return receipt and link.

## 14.2 Requirement to RFQ

1. Load requirement.
2. Validate ownership/state.
3. List approved capable suppliers.
4. Explain recommendations from actual capability data.
5. Draft terms and supplier selection.
6. Present RFQ preview.
7. Create draft through canonical service.
8. Require explicit confirmation to publish.
9. Publish and verify artifact only after confirmation.

## 14.3 Quotations to comparison

1. Resolve RFQ and requirement.
2. Validate documents and extraction status.
3. Show fields requiring verification.
4. Allow Purchase Manager corrections.
5. Verify quotes using canonical service.
6. Run deterministic normalization/calculation.
7. Generate comparison preview from verified quotes.
8. Generate model-assisted narrative using structured comparison data.
9. Show source citations and unavailable values.
10. Allow edits to permitted recommendation fields.
11. Freeze/submit only after Purchase Manager confirmation.
12. Create approval tasks/notifications for the exact version.

## 14.4 Approval

1. Load immutable comparison version.
2. Show recommendation, deviations, evidence, and PDF.
3. Ask for explicit approve/reject decision.
4. Require rejection rationale.
5. Call canonical approval service.
6. Reload approval state.
7. Return receipt.
8. Do not allow the assistant to approve on behalf of another membership.

## 14.5 Comparison to PO

1. Verify both required approvals on the exact version.
2. Prepare PO preview through canonical service.
3. Show commercial commitment warning.
4. Require Purchase Manager confirmation.
5. Confirm PO and verify immutable artifact.
6. Treat email and ERP post as separate controlled actions with separate receipts.

---

## 15. Security and safety requirements

## 15.1 Authorization

- server-side capability checks on every tool and endpoint;
- membership selected at login determines scope;
- no trust in client-provided role, tenant, plant, or approval identity;
- hierarchy checks for delegation and manager reads;
- deny by default;
- test cross-role and cross-tenant attacks.

## 15.2 Prompt injection and untrusted content

- document text is data, not instructions;
- separate system/policy/tool definitions from retrieved content;
- sanitize or safely render document excerpts;
- restrict tools before model invocation;
- do not allow documents to request secrets, policy changes, or unrelated actions;
- detect suspicious instruction-like content and surface a warning where useful;
- never execute commands or code from uploaded documents.

## 15.3 Data minimization

- send only necessary fields and excerpts to model providers;
- redact secrets and private tokens;
- configurable model logging/privacy policy;
- do not expose password/MFA/session data to agents;
- avoid storing full prompts when structured safe metadata is sufficient.

## 15.4 Idempotency and transactions

- every controlled action accepts/derives an idempotency key;
- duplicate retries return the prior receipt;
- database writes are transactional;
- document generation and business state changes remain consistent;
- outbox pattern used for simulated/future external delivery where already available.

## 15.5 Rate and cost controls

- per-user/workspace assistant request limits;
- attachment size and count limits;
- bounded tool-call count;
- bounded graph steps;
- timeout/retry budgets;
- context-size limits and summarization;
- Admin-visible usage metrics;
- safe cancellation.

## 15.6 Emergency controls

Retain or restore:

- workspace-level agent enable/disable;
- global emergency stop;
- provider status;
- disable side-effect tools while retaining read-only assistance;
- clear UI indicator when restricted.

---

## 16. Observability and operational reliability

Implement structured telemetry for:

- request/run/thread IDs;
- user/workspace/plant IDs in safe internal form;
- graph node transitions;
- tool name/version;
- tool duration and result status;
- model provider/model;
- latency;
- token counts/cost estimate where available;
- interruption/resume;
- proposal and receipt IDs;
- errors and retry count.

Do not log secrets, raw document bytes, session tokens, signed URLs, or unnecessary sensitive content.

Use existing logging infrastructure and add OpenTelemetry-compatible boundaries if practical without blocking the release. Do not require a paid external observability product for local development or tests.

Add health/readiness checks for:

- API;
- database;
- Redis/worker where used;
- MinIO;
- provider configured/reachable state;
- agent emergency-stop state.

---

## 17. Evaluation and test strategy

Agent quality must be tested as behavior, not only as snapshots of prose.

## 17.1 Backend tests — REQUIRED

Add tests for:

- role/capability tool filtering;
- tenant and plant isolation;
- hierarchy delegation rules;
- task state transitions;
- idempotent actions;
- proposal approval/rejection;
- interrupted run resume;
- provider unavailable limited mode;
- agent cannot bypass RFQ publication confirmation;
- agent cannot approve comparison for wrong role;
- comparison uses only verified quotes;
- deterministic landed-cost calculation;
- immutable comparison and PO versions;
- receipt truthfulness;
- secure document URLs;
- prompt-injection content cannot alter tool policy;
- cross-tenant document citation denial;
- emergency stop;
- rate limits where feasible;
- migration upgrade and fresh database.

## 17.2 Golden workflow evaluations — REQUIRED

Create deterministic fixture-driven evaluations for at least:

1. Create a valid requirement from natural language.
2. Missing material triggers material-master request guidance, not a duplicate material.
3. Prepare RFQ with approved capable suppliers.
4. Reject a request to publish RFQ without confirmation.
5. Upload three quotation fixtures and surface extraction uncertainties.
6. Produce a comparison only after verification.
7. Correctly calculate and cite landed costs.
8. Identify a delivery/specification deviation.
9. Submit the exact comparison version for both approvals.
10. Reject with rationale and create a new version after revision.
11. Prepare and confirm PO only after both approvals.
12. Delegate a verification task and surface it to the recipient.
13. Request a follow-up and escalate an overdue task.
14. Answer an SOP question with sources.
15. Refuse an out-of-scope production scheduling action.
16. Continue manual workflow with provider disabled.

Where model output is nondeterministic, assert structured schemas, selected tools, policy gates, sources, and resulting domain state rather than exact prose.

## 17.3 Playwright E2E — REQUIRED

Extend `apps/web/e2e/role-workflows.spec.ts` or split focused specs.

Cover desktop, tablet, and mobile for:

- login and workspace selection;
- role-aware navigation;
- My Work;
- open/close assistant panel;
- context shown correctly;
- requirement proposal and creation;
- RFQ draft and publication confirmation;
- quotation upload/extraction review;
- comparison preview/freeze;
- dual approval;
- PO confirmation and PDF opening;
- task delegation and recipient visibility;
- action proposal and receipt persistence after refresh;
- limited mode;
- permission-denied action;
- no internal MinIO URL;
- keyboard navigation for critical controls;
- no horizontal overflow.

Use deterministic test provider behavior or fixtures. Do not make E2E depend on a live paid LLM.

## 17.4 Visual quality checks — REQUIRED

At desktop, tablet, and mobile:

- capture key screenshots;
- inspect shell consistency;
- inspect dense tables and forms;
- inspect assistant panel states;
- inspect long content and error states;
- confirm no clipped dialogs, overlapping panels, or unreadable status colors.

## 17.5 Existing verification must remain green

Run at minimum:

```powershell
npm run generate:api
npm run check:api-contract
npm run typecheck
npm run build:web
npm run test:e2e
cd apps/api
python -m pytest -q
```

Also run `git diff --check` at completion.

---

## 18. Implementation sequence

Codex must execute all phases without stopping after a phase summary.

## Phase 0 — Baseline and discovery

1. Read `HANDOFF.md`, this file, architecture docs, product principles, acceptance docs, and current agent code.
2. Inspect Git status/diff without reverting.
3. Inspect Docker health and existing tests.
4. Map current models/routes/components to the target concepts.
5. Identify reusable legacy agent code and obsolete duplicate paths.
6. Record a private implementation checklist, then begin changes.

**Gate:** existing baseline understood; no destructive cleanup.

## Phase 1 — Design system and application shell

1. Establish tokens and reusable primitives.
2. Refactor `IndustrialConsole` into shell/navigation/layout components.
3. Implement role-aware sidebar and top context bar.
4. Implement My Work page skeleton with real canonical data.
5. Standardize list/detail/workbench patterns.
6. Improve loading/error/empty/permission states.
7. Verify responsive behavior before adding assistant complexity.

**Gate:** all current manual routes remain reachable and functionally intact.

## Phase 2 — Task and hierarchy foundation

1. Extend canonical Task model/services.
2. Add hierarchy model only if current memberships cannot represent reporting.
3. Add migrations and seed/bootstrap compatibility.
4. Add task/delegation/follow-up APIs.
5. Add task UI, manager summaries, and notifications.
6. Add authorization, state-machine, and isolation tests.

**Gate:** managers can delegate and inspect tasks without any LLM.

## Phase 3 — Agent persistence, policy, and runtime

1. Consolidate retained agent models/services.
2. Add thread/run/event/proposal/receipt semantics.
3. Implement durable checkpointer and provider abstraction.
4. Implement typed tool registry and policy engine.
5. Implement primary LangGraph workflow and bounded subgraphs.
6. Implement human interruptions and resumable runs.
7. Implement streaming events and limited mode.
8. Add audit and observability.

**Gate:** a test agent can read authorized records, create a task proposal, pause, resume, execute, and return a verified receipt.

## Phase 4 — Assistant UI

1. Replace the old launcher/drawer experience with the contextual panel.
2. Implement thread list/history and context display.
3. Implement typed blocks, streaming progress, sources, proposals, approval, and receipts.
4. Add attachment handling through current document services.
5. Add command palette and role/context suggestions.
6. Add provider/emergency status.
7. Persist state across refresh.

**Gate:** UI never relies on prose to determine action state.

## Phase 5 — Procurement agent workflows

Implement end to end in this priority order:

1. quotation review and comparison;
2. approval summary and controlled approval;
3. requirement drafting/creation;
4. RFQ preparation/publication;
5. PO preparation/confirmation;
6. task delegation/follow-ups;
7. SOP explanation;
8. inbound explanation/drafting assistance.

For each workflow:

- implement tools;
- enforce policy;
- add structured response blocks;
- add backend tests;
- add E2E coverage;
- verify manual equivalent still works.

**Gate:** flagship demo in Section 20 passes without manually editing the database.

## Phase 6 — UI polish and consistency

1. Complete all workbench redesigns.
2. Fix responsive issues.
3. Standardize statuses and timelines.
4. Remove dead ordinary-navigation remnants of legacy duplicate screens.
5. Keep compatibility endpoints/files where required.
6. Verify accessibility and keyboard interactions.
7. Capture/inspect screenshots.

**Gate:** no placeholder UI and no broken normal role workflow.

## Phase 7 — Contracts, documentation, and final verification

1. Generate API contract; never hand-edit it.
2. Update architecture docs.
3. Update product principles and acceptance criteria.
4. Add runbook for agent provider, emergency stop, migrations, and troubleshooting.
5. Run complete tests/build.
6. Fix regressions.
7. Run `git diff --check`.
8. Produce final implementation report.

---

## 19. File-level work map

This map is directional. Inspect before editing.

### Backend likely to change

- `apps/api/app/main.py` — route registration and shared app wiring;
- `apps/api/app/procurement_v2.py` — expose/reuse canonical application services, not duplicate agent logic;
- `apps/api/app/domains/workflows.py` — task/work queues/stage projections/authorization;
- `apps/api/app/documents.py` — attachment/evidence access, no MinIO regression;
- `apps/api/app/integrations.py` — controlled email/ERP action receipts;
- `apps/api/app/db/models.py` and related API models — agent/task persistence;
- `apps/api/app/core/permissions.py` — capability and risk policy;
- `apps/api/app/routers/agents.py` — coherent v2 agent endpoints and retained compatibility;
- `apps/api/app/agent_service.py` — run orchestration/service boundary;
- `apps/api/app/agent_schemas.py` — typed blocks/tools/proposals/receipts;
- worker/beat configuration — due follow-ups and background extraction/run jobs where appropriate;
- new migration after `0008`.

### Frontend likely to change

- `apps/web/components/industrial/IndustrialConsole.tsx` — decompose/refactor;
- `apps/web/components/features/WorkflowForms.tsx` — decompose and standardize;
- `apps/web/components/AgentDrawer.tsx` — replace or retire from normal use;
- `apps/web/components/AgentWorkspace.tsx` — rebuild as contextual assistant;
- `apps/web/lib/api.ts` — generated-contract-compatible clients and stream handling;
- `apps/web/app/globals.css` — design tokens and base styles;
- procurement/inbound pages — workbench layouts;
- new shell/design-system/assistant/task components;
- `apps/web/e2e/role-workflows.spec.ts` and focused new specs.

### Contracts and docs

- `packages/shared/src/api.generated.ts` — regenerate only;
- `docs/architecture/procurement-v2.md`;
- `docs/architecture/role-agent-os.md`;
- `docs/architecture/industrial-v1.md` or successor;
- `docs/product-principles.md`;
- `docs/v1-acceptance.md` or new release acceptance file;
- `docs/runbooks/` agent/provider/emergency/troubleshooting docs;
- `.env.example` for non-secret agent settings.

---

## 20. Flagship acceptance demo

The release is not complete until this scenario works through the UI and canonical APIs.

### Setup

- Plant Manager, Purchase Executive, Purchase Manager, Gate Operator, Store Manager, Quality Inspector, and Admin memberships exist.
- Approved material and at least three capable suppliers exist.
- Deterministic test quotation documents exist.
- Agent provider is configured or deterministic test provider is enabled.

### Scenario

1. Plant Manager opens My Work and asks the assistant:

   > “We need 5,000 units of Bearing 6205 by August 12. Assign it to the Purchase Executive.”

2. Assistant resolves material/assignee and displays a structured requirement and delegation proposal.
3. Plant Manager confirms. Canonical requirement and task are created atomically or through the defined safe sequence, with receipts.
4. Purchase Executive sees the task, opens the requirement, and asks the assistant to prepare an RFQ.
5. Assistant recommends only approved capable suppliers with evidence, prepares the RFQ, and pauses before publication.
6. Purchase Executive confirms publication. Immutable RFQ artifact and receipt appear.
7. Three quotation files are uploaded/associated.
8. Purchase Manager sees processing results, reviews low-confidence fields, makes corrections, and verifies the quotations.
9. Purchase Manager asks:

   > “Compare these quotations, show landed cost, delivery and specification risks, and prepare the approval package.”

10. Assistant uses deterministic comparison data, cites every material value, marks missing data, and provides a recommendation with risks.
11. Purchase Manager reviews and freezes/submits the comparison.
12. Plant Manager and Purchase Executive each see the exact immutable version and approve it independently.
13. Purchase Manager asks the assistant to prepare the PO.
14. Assistant shows a commercial-commitment proposal and pauses.
15. Purchase Manager confirms. Final PO artifact is created and verified.
16. Any supplier email action remains a separate confirmed action and produces its own receipt.
17. Plant Manager asks for status and receives the authoritative current state, owner, completed milestones, pending next action, and links.
18. Audit view shows all runs, proposals, approvals, tools, artifacts, and receipts.
19. Repeating an approved action with the same idempotency key does not create duplicates.
20. With the provider disabled, the same records remain fully operable through structured UI.

---

## 21. Release acceptance checklist

### Product

- [ ] Manual and agentic procurement use the same canonical records and services.
- [ ] Procurement is complete; future plant modules are not falsely represented as complete.
- [ ] Role hierarchy and task delegation are visible and useful.
- [ ] Agents explain, prepare, delegate, follow up, and submit for approval.
- [ ] Agents do not silently perform controlled actions.

### UI

- [ ] Professional, consistent shell on desktop/tablet/mobile.
- [ ] Role-aware sidebar and My Work page.
- [ ] Contextual assistant panel, not floating launcher.
- [ ] Workbench layout for major records.
- [ ] Quotations and comparison experiences are excellent.
- [ ] Typed proposals, sources, progress, and receipts.
- [ ] Accessible loading/error/empty/permission states.
- [ ] No placeholder or dead normal-navigation UI.

### Agent runtime

- [ ] LangGraph runtime consolidated rather than duplicated.
- [ ] Durable state and resumable interruptions.
- [ ] Bounded tools and graph steps.
- [ ] Provider abstraction and limited mode.
- [ ] Explicit policy and risk classes.
- [ ] Idempotent side effects.
- [ ] Verified receipts.
- [ ] Emergency stop.

### Security

- [ ] Tenant/plant/role scope on every operation.
- [ ] Prompt-injection-resistant tool policy.
- [ ] No private MinIO URLs.
- [ ] No secrets in logs or model context.
- [ ] Controlled actions require human authority.
- [ ] Cross-tenant and wrong-role tests pass.

### Engineering

- [ ] Forward migration added and tested.
- [ ] OpenAPI contract regenerated and validated.
- [ ] Typecheck and production build pass.
- [ ] API tests pass.
- [ ] Playwright tests pass at all breakpoints.
- [ ] `git diff --check` passes.
- [ ] Docs and runbooks updated.

---

## 22. Explicit anti-patterns

Reject or refactor any implementation that does the following:

- creates a second `Objective`-like demand intake;
- adds a generic floating agent button as the main interface;
- stores business truth only in chat history;
- lets the LLM generate database mutations directly;
- gives every role every tool;
- claims completion before backend verification;
- allows an agent to approve on behalf of a user;
- makes RFQ publication or PO issue automatic;
- creates comparisons from unverified quotes;
- calculates commercial totals only in model prose;
- exposes raw MinIO URLs;
- makes manual workflow depend on a model key;
- uses hard-coded demo IDs in production paths;
- introduces a new orchestration framework alongside LangGraph without removing the old one;
- adds unrestricted agent-to-agent conversations instead of canonical tasks;
- shows supplier performance claims without stored evidence;
- adds future modules as empty navigation or fake dashboards;
- rewrites generated API files manually;
- hides failures behind optimistic success toasts.

---

## 23. Configuration additions

Document and add safe defaults in `.env.example`, adapted to current naming:

- workspace/global agent enablement;
- provider base URL;
- fast and strong model names;
- provider API key placeholder;
- request timeout;
- maximum graph steps;
- maximum tool calls;
- maximum attachment/context size;
- checkpoint retention;
- rate limits;
- external email enablement;
- ERP posting enablement;
- agent trace content policy;
- deterministic test provider flag.

Never commit actual credentials.

---

## 24. Documentation deliverables

Update documentation so the next engineer can operate the release without reading code.

Required documents or sections:

1. Product principles: system of work above systems of record; manual + agentic equivalence.
2. Canonical domain and authority matrix.
3. Agent runtime architecture and graph diagram.
4. Tool risk/policy matrix.
5. Task/delegation state machine.
6. Proposal/approval/receipt lifecycle.
7. UI information architecture and responsive behavior.
8. Provider setup and limited mode.
9. Emergency stop and incident response.
10. Document/privacy/prompt-injection protections.
11. Migration and API contract workflow.
12. Test/evaluation strategy.
13. Flagship demo instructions.
14. Known production boundaries.

---

## 25. Official framework references

Use current official documentation while implementing, and pin compatible versions according to the existing dependency strategy.

- LangGraph persistence: `https://docs.langchain.com/oss/python/langgraph/persistence`
- LangGraph interrupts: `https://docs.langchain.com/oss/python/langgraph/interrupts`
- LangGraph streaming: `https://docs.langchain.com/oss/python/langgraph/streaming`
- Model Context Protocol tools specification for future integration boundaries: `https://modelcontextprotocol.io/specification/2025-06-18/server/tools`
- shadcn-style sidebar reference: `https://ui.shadcn.com/docs/components/base/sidebar`
- shadcn-style data-table reference: `https://ui.shadcn.com/docs/components/base/data-table`

These references are implementation aids, not permission to replace repository conventions blindly.

---

## 26. Final Codex completion response

After implementing everything required, Codex must report:

1. the release outcome in plain language;
2. major backend changes;
3. major frontend/UI changes;
4. migrations added;
5. security and policy controls added;
6. tests added;
7. exact commands run and results;
8. screenshots or browser-verification summary;
9. any pre-existing failures clearly separated from new failures;
10. any genuinely incomplete requirement with exact reason.

Do not report success if tests were skipped, the provider path was never exercised with a deterministic test adapter, the assistant only produces prose, controlled actions lack receipts, or the flagship demo cannot complete.
