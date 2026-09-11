# GenuineGigs Role-Agent Operating System

> Code-aligned architecture for private employee agents, governed delegation, human authority, fresh workspaces, and provider-independent operation.

## 1. Operating Model

Each workspace member has a role-specialized agent. The agent is not a global chatbot and does not receive the complete tenant. A conversation is attached to a personal queue, work item, objective, or team follow-up and receives a server-generated authorization envelope.

~~~mermaid
flowchart LR
  Human[Workspace member] --> Thread[Scoped agent thread]
  Thread --> Context[AgentContextEnvelope]
  Context --> Graph[LangGraph role workflow]
  Graph --> Model[Groq or configured provider]
  Graph --> Tools[Local typed tools]
  Tools --> Policy[Server authorization]
  Policy --> Records[(Authorized records)]
  Tools --> Proposal[Controlled action proposal]
  Proposal --> Review[Authorized human review]
  Review --> Workflow[Existing workflow API]
~~~

Normal procurement remains usable when agents are disabled or the model provider is unavailable.

## 2. Technology

| Concern | Implementation |
| --- | --- |
| API and policy authority | FastAPI, Pydantic, SQLAlchemy |
| Agent graph | LangGraph embedded in the API/worker code |
| Primary provider | Groq through langchain-groq; local function calling only |
| Model profiles | openai/gpt-oss-120b for planning; llama-3.1-8b-instant for routing |
| Provider boundary | LangChain chat-model interface; permissions remain provider-independent |
| Durable business state | PostgreSQL agent runs, messages, proposals, delegations, tool decisions, and audit |
| Background delivery | Redis and Celery with an independently scalable agents queue |
| Knowledge | Approved ACL-labelled documents/chunks; PostgreSQL with pgvector enabled |
| Evidence storage | Existing private MinIO/S3 quarantine and evidence buckets |
| Streaming | SSE state, output, citation, proposal, error, and completion events |
| Observability | Product audit is authoritative; external trace export is disabled by default |
| Deployment | Docker Compose locally; Helm with external PostgreSQL, Redis, S3, and Secret references |

The model never executes tools remotely. It returns typed intent; GenuineGigs validates identity, scope, arguments, entity version, and authority before local execution.

## 3. Identity And Workspace Isolation

~~~mermaid
erDiagram
  ACCOUNT ||--o{ WORKSPACE_MEMBERSHIP : joins
  TENANT ||--o{ WORKSPACE_MEMBERSHIP : contains
  WORKSPACE_MEMBERSHIP ||--|| AGENT_PROFILE : owns
  WORKSPACE_MEMBERSHIP ||--o{ TASK : assigned
  WORKSPACE_MEMBERSHIP ||--o{ AGENT_THREAD : owns
  AGENT_THREAD ||--o{ AGENT_MESSAGE : contains
  AGENT_THREAD ||--o{ AGENT_RUN : executes
  AGENT_RUN ||--o{ AGENT_TOOL_CALL : records
  PURCHASE_REQUIREMENT ||--o{ TASK : coordinates
  PURCHASE_REQUIREMENT ||--o{ AGENT_DELEGATION : delegates
  AGENT_PROPOSAL }o--|| WORKSPACE_MEMBERSHIP : confirms
~~~

- Account is global identity: verified email, password, MFA, backup codes, and sessions.
- WorkspaceMembership supplies tenant, plants, department, role, manager, status, and permissions.
- Sessions pin the selected membership. Switching workspace rotates selected scope and invalidates frontend data.
- Demo workspaces contain reference procurement records.
- Fresh workspaces contain organization/bootstrap records but no sample RFQs, quotes, tasks, awards, POs, receipts, or cases.
- Demo and fresh are separate tenants; there is no destructive mode toggle.

Invitation, password recovery, TOTP MFA, backup recovery, session listing, and revocation are identity endpoints and produce security/audit records.

## 4. Context Assembly

Every run builds an AgentContextEnvelope on the server:

    tenant and workspace
    selected membership and role
    authorized plant and reporting scope
    thread owner and scope type
    requirement/work-item identifiers
    explicit entity allowlist
    approved knowledge namespaces
    read, draft, delegation, and proposal tools
    restricted actions
    token, time, handoff, and delegation limits
    policy/prompt version and correlation ID

Context is assembled from the selected membership and work_items, never from model-provided IDs. Structured records use tenant, plant, and ownership SQL filters. Knowledge is ACL-filtered before semantic ranking. Similarity can order authorized chunks but cannot grant access.

~~~mermaid
flowchart TD
  Session[Selected membership] --> Scope[Tenant plant role ownership]
  Scope --> Work[Owned work item]
  Work --> Entities[Explicit linked entities]
  Scope --> Knowledge[Approved role/plant knowledge]
  Entities --> Envelope[Context envelope]
  Knowledge --> Envelope
  Envelope --> Prompt[Role playbook plus user request]
~~~

Employee agents may read assigned tasks, linked records, approved shared knowledge, their private memory/thread, and addressed delegations. Manager agents receive formal status for their reporting subtree, not private messages.

## 5. Tool And Authority Guardrails

1. No database credentials, generic SQL, unrestricted HTTP, shell, or admin tool enters model context.
2. Tool names are allowlisted and arguments are Pydantic-validated.
3. Every call rechecks tenant, plant, membership, task ownership, role, entity, and action.
4. Model-generated or forged entity IDs fail closed.
5. Agents can explain, summarize, extract, compare, draft, request updates, and create governed follow-up work.
6. Publishing, approval, award, PO posting, inventory changes, master-data changes, and case closure become expiring AgentProposal records.
7. Proposal confirmation rechecks human role and record version, then calls the authoritative workflow function.
8. Peer agents can request collaboration but cannot assign or mutate a peer's work.
9. Manager delegation is restricted to reporting descendants and configured depth.
10. Documents are untrusted evidence; their text cannot change policy or tool availability.
11. Runs carry token/time budgets, handoff/delegation limits, cancellation state, correlation IDs, and auditable failures.
12. Deployment, tenant, and profile switches must all be enabled. Any switch can stop AI while leaving workflows available.

## 6. Agent Communication

Agents communicate through structured durable delegations, not shared transcripts.

~~~mermaid
sequenceDiagram
  participant M as Manager agent
  participant P as Policy
  participant D as Delegation store
  participant W as Recipient agent
  participant H as Recipient human
  M->>P: Requested outcome, references, due date
  P->>P: Validate reporting line and minimal context
  P->>D: Commit delegation and audit
  D->>W: Start scoped recipient work
  W->>H: Explain or prepare recipient task
  W->>D: Accept, clarify, progress, complete, or escalate
  D-->>M: Formal cited status projection
~~~

A delegation packet contains objective, requested outcome, record references, constraints, due date, response schema, and depth. It excludes private history and unrelated records. Repeated failure, no owner, overdue commitments, or exhausted handoffs escalate to the human manager.

## 7. Fresh Workspace Journey

~~~mermaid
flowchart TD
  Create[Create fresh workspace] --> Bootstrap[Company plant owner]
  Bootstrap --> People[Invite employees and reporting lines]
  People --> Master[Add item and supplier master data]
  Master --> Policy[Choose provider models budgets policy]
  Policy --> Requirement[Plant Manager creates canonical purchase requirement]
  Requirement --> Validate[Assistant identifies missing required fields]
  Validate --> Preview[Human previews requirement and assignment]
  Preview --> Delegate[Governed task to named Purchase Executive]
  Delegate --> RFQ[Purchase agent prepares RFQ]
  RFQ --> Approval[Human controlled decisions]
  Approval --> Inbound[Store dependent work]
  Inbound --> Quality[Quality dependent work]
  Quality --> Status[Manager receives formal cited status]
~~~

The implemented vertical slice creates a fresh tenant, plant, and owner membership; supports invitations and workspace selection; creates canonical multi-line purchase requirements; and produces named Purchase Executive work plus a durable delegation. Objective creation is retired and returns HTTP 410.

## 8. UI Boundaries

- My Work is the universal role home for assigned tasks, delegated work, blockers, notifications, and team status.
- Work-item screens expose a contextual assistant panel in the page grid; it is not a floating chat overlay.
- Plant Managers see canonical requirements, hierarchy-safe delegation, and formal team status.
- Results state sources used, work prepared, missing information, and required human authority.
- Tool/run activity is visible without exposing hidden reasoning.
- Disabled, provider-failure, cancellation, and empty states keep the non-AI workflow reachable.

The canonical Task record is the coordination primitive. It records requested outcome, instructions, priority, due date, assignee, delegator, expected output, source entity, blocker, completion summary, follow-up timestamps, escalation level, and optional source agent run. Legal lifecycle transitions are enforced by the API, and delegation is limited to self, Admin authority, or reporting descendants.

Agent activity is persisted as typed AgentEvent records. AgentCheckpoint stores bounded operational graph state for context resolution, validated decisions, human interruptions, resumed execution, failure, and final metrics. Successful mutations produce AgentActionReceipt records only after the domain transaction succeeds. Proposals carry risk class, required capability, idempotency, confirmation, and rejection rationale. SSE projects persisted run events without exposing hidden chain-of-thought.

The current specialist execution slice supports canonical requirement delegation, RFQ draft/PDF preparation by the assigned Purchase Executive, deterministic comparison preparation from verified quotations by the assigned Purchase Manager, and an interrupting purchase-order commitment proposal. RFQ publication, comparison submission/approval, and final PO creation remain server-authorized human decisions.

## 9. Runtime And Deployment

Docker Compose starts pgvector PostgreSQL, Redis, MinIO, migration, demo seed, API, web, workers, Beat, and Mailpit. Groq is optional: with no key the development demo uses deterministic cited fallback; production should disable fallback unless explicitly accepted.

The Helm chart in deploy/helm/genuinegigs expects managed PostgreSQL, Redis, S3-compatible storage, and a pre-created Kubernetes Secret. API, web, agent workers, and workflow workers scale independently. Migrations run before install/upgrade and readiness checks block unhealthy API rollout.

Production rollout:

1. Deploy with AGENT_ENABLED=false.
2. Migrate and verify identity/workspace isolation.
3. Upload and approve role knowledge.
4. Run mocked policy tests and restricted provider evaluations.
5. Enable one internal tenant and monitor denials, cost, latency, and citation quality.
6. Promote prompt, policy, and model versions through staged tenant flags.
7. Keep ERP live writes independently disabled until connector acceptance.

## 10. Non-Negotiable Invariants

1. ERP authority is never bypassed.
2. A model cannot increase its own context or tool permissions.
3. Private employee conversations are not manager status data.
4. Controlled actions require the correctly authorized human.
5. Context, tools, proposals, handoffs, decisions, and failures are correlated and audited.
6. Agent shutdown or provider outage cannot stop ordinary workflow execution.
7. Demo data and fresh customer operations remain tenant-isolated.
