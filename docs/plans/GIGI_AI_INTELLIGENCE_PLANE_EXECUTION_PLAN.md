# Gigi AI Intelligence Plane — Production Execution Plan

**Prepared:** 2026-09-02  
**Source specification:** `MD-files-for-codex/GIGI_AI_INTELLIGENCE_PLANE_IMPLEMENTATION.md`  
**Scope:** Phases 0–12, including production hardening and the canonical end-to-end acceptance proof.

## 1. Objective

Build one shared Gigi intelligence plane over the existing GenuineGigs Factory Brain and deterministic domain engines.

Gigi will:

- understand the authenticated user, role, authority, plant, module, page and selected entity;
- investigate through permission-filtered tools;
- reason across Procurement, SCM and Operations;
- use existing state, graph, trace, planning and simulation services as authoritative sources;
- return evidence-backed natural responses;
- compare real candidate interventions;
- propose consequential work exclusively through the shared ActionIntent boundary;
- proactively investigate important events without creating notification spam;
- persist conversations, validated memories, briefings, feedback and verified experiences;
- remain observable, bounded, tenant-isolated and usable when an AI provider is unavailable.

This is not permission to build a second source of truth, a second event bus, arbitrary SQL tools, independent module agents, online model training or direct ERP/machine control.

---

## 2. Audit of the current implementation

### 2.1 Reusable now

| Capability | Existing implementation | Reuse decision |
|---|---|---|
| Authentication, tenant and plant scope | `core/security.py`, `core/permissions.py`, workspace memberships | Reuse as the only identity/authority source. |
| Factory context primitives | `platform/context.py`, `platform/agent_runtime.py`, `platform/state.py` | Wrap in the new tiered context engine. |
| Canonical entity resolution | `platform/catalog.py`, `ExternalEntityReference` | Reuse for all entity grounding. |
| Relationship/impact traversal | `platform/relationships.py` | Expose through read-only registered tools. |
| State, history and trace | `platform/state.py`, `platform/trace.py` | Expose as evidence-producing tools. |
| Cases, work and approvals | `platform/cases.py`, `platform/work.py`, `platform/actions.py` | Reuse; do not introduce AI-owned alternatives. |
| SCM planning and scenarios | `scm/engine.py`, `planning.py`, `service.py`, `recommendations.py` | Gigi calls these; it never repeats their calculations. |
| Operations recovery | `operations/recovery/*`, Operations services | Gigi calls recovery/read services and simulations. |
| Transactional events | `platform/events.py`, `eventing.py`, outbox/receipts | Use for proactive triggers and downstream AI jobs. |
| Conversation-like persistence | `AgentThread`, `AgentMessage`, attachments | Migrate/extend rather than duplicate with parallel AI tables. |
| Run trace records | `AgentRun`, `AgentEvent`, `AgentCheckpoint`, `AgentToolCall` | Extend to the specification and use as canonical Gigi run records. |
| Prepared action records | `AgentProposal`, `AgentActionReceipt` | Compatibility adapter into `ActionIntent`; do not preserve as a second governance path. |
| Knowledge records | `KnowledgeDocument`, `KnowledgeChunk` | Extend for vector/hybrid retrieval and canonical entity links. |
| User feedback | `AgentFeedback` | Extend rather than introduce another feedback table. |
| Basic memory | `AgentMemory` | Migrate into governed, typed and scoped memory. |
| Proactive companion | `CompanionPreference`, `CompanionTriggerPolicy`, `CompanionIntervention`, `companion.py` | Reuse policies/preferences and migrate delivery into Gigi investigations/briefings. |
| Bounded tool loop | `agent_runtime.py` with LangGraph | Reuse its budgets/termination semantics behind the new runtime. |
| Capability registry | `agent_capabilities.py` | Migrate into a typed cross-domain tool registry. |
| Provider budgets | Settings plus provider request compaction in `agent_service.py` | Move behind the central model gateway. |
| Streaming/run events | Agent run event APIs and existing SSE patterns | Standardize into `/api/v1/gigi` safe stream events. |
| Frontend global entry point | `ProductShell.tsx` has module assistant hooks | Replace hooks with one persistent global Gigi controller. |
| Observability foundation | Prometheus metrics and OpenTelemetry | Extend with model/tool/cost/evaluation metrics. |

### 2.2 Partially existing

| Capability | Gap |
|---|---|
| Model gateway | `model_gateway.py` is a small structured-call abstraction, while `agent_service.py` still instantiates Groq/LangChain directly. No complete provider routing, fallback policy, normalized usage/cost or streaming abstraction exists. |
| Natural tool runtime | A bounded loop exists, but the active capability system is heavily Procurement-oriented and still contains deterministic intent compatibility logic. It is not the cross-domain goal → plan → investigate loop in the specification. |
| Context engine | User/work/page/context fragments exist, but not one tiered FactoryContext service with freshness, authority, evidence budgets and cross-domain expansion. |
| Tool registry | Capabilities contain roles and effects, but lack complete typed output contracts, consistent versions, permission predicates, domain grouping and SCM/Operations coverage. |
| Role profiles | `AgentProfile` and Operations agent types exist, but there is no single Gigi runtime with SCM planner, buyer, Operations, manager and leadership profiles. |
| Memory | Current memory is key/value per membership. It lacks evidence validation, scopes, types, confidence, validity, supersession and verified episodic memory. |
| Knowledge/RAG | Documents/chunks, ACLs and metadata exist. Chunk embeddings are stored as JSON/empty arrays and retrieval is not a production hybrid pgvector pipeline. |
| Proactive intelligence | Procurement companion triggers/deduplication exist; factory-wide event policy, `AIInvestigation`, SCM/Operations investigations and unified Gigi delivery do not. |
| Briefings | Operations and Procurement have bounded briefs; no central persisted morning/EOD/weekly briefing product exists. |
| Learning | Feedback and recovery history exist; no normalized verified `AgentExperience`, similar-case retrieval or effectiveness service spans domains. |
| Evidence responses | Existing blocks/citations exist, but high-value numeric grounding is not universally validated against tool result references. |
| Gigi frontend | Procurement `AgentDrawer`/`GenuineGigsCompanion` and Operations `GigiPanel` compete. No persistent cross-module conversation, full `/gigi` workspace or common evidence/action UI exists. |

### 2.3 Legacy/duplicate paths to migrate

- Direct provider construction inside `agent_service.py`.
- Procurement-centric deterministic intent parsing as the primary conversational architecture.
- Separate Procurement `AgentDrawer` and companion UI.
- Separate Operations `GigiPanel` and `/api/v2/gigi/*` experience.
- Deterministic Operations “objective agents” presented as separate brains.
- `AgentProposal` paths that are not ultimately represented by shared `ActionIntent`.
- Empty/JSON embedding placeholders in `KnowledgeChunk`.
- Old module URLs embedded in companion navigation actions.

These stay operational behind compatibility adapters until the equivalent Gigi path passes regression tests. They are removed only after traffic/readiness evidence confirms parity.

### 2.4 Missing

- A cohesive `app/intelligence/` module.
- Persisted prompt-version registry.
- Central production model gateway.
- Tiered cross-domain Context Engine.
- Fully typed cross-domain tool registry.
- Natural multi-tool planner/runtime with structured stop conditions.
- Decision Intelligence service.
- Governed typed memory and verified experience store.
- Production pgvector/hybrid knowledge retrieval and entity linking.
- Factory-wide proactive investigations and persisted briefings.
- Cross-domain outcome learning/effectiveness ranking.
- Programmatic numeric-grounding/hallucination checks.
- Unified `/api/v1/gigi` API and safe streaming contract.
- Shared Gigi panel plus `/gigi` workspace.
- Canonical AI fixture and complete production readiness suite/report.

---

## 3. Architecture and migration strategy

### 3.1 Package boundary

Create `apps/api/app/intelligence/` with these logical areas:

```text
models/schemas/router
model_gateway/
context/
tools/
runtime/
roles/
memory/
knowledge/
proactive/
learning/
evaluation/
prompts/
```

Existing services remain in their domains. Intelligence adapters call public service functions; they do not import routers or query arbitrary tables.

### 3.2 Existing model migration

Prefer additive extensions to the current records:

- `AgentThread` becomes the stored Gigi conversation; add conversation type, module context, archive timestamps and conversation metadata where absent.
- `AgentMessage` becomes the Gigi message; retain structured blocks/citations and add nullable run linkage where needed.
- extend `AgentRun` with run type, role profile, prompt-version FK/name, model task class, result summary/structured response and complete timing/usage fields;
- extend `AgentToolCall` with tool version, call index, typed result summary, status, start/end timestamps, error and source references;
- replace `AgentMemory` key/value semantics with additive typed fields and a migration/backfill adapter;
- extend `AgentFeedback` to message/experience references and general feedback types;
- extend `KnowledgeDocument/KnowledgeChunk` instead of creating a second knowledge store;
- create genuinely missing `AgentExperience`, `AIBriefing`, `AIInvestigation`, `PromptVersion` and document-entity link tables.

Use forward migrations beginning after current head `0064`. Each migration must upgrade a populated database and have a downgrade or a documented irreversible-data rationale.

### 3.3 Compatibility seams

- Existing `/agent/*`, `/agent/companion/*` and `/api/v2/gigi/*` APIs call the new application services during migration.
- Existing UIs become thin adapters to the shared Gigi store until replaced.
- Old agent records remain readable in audit/retention flows.
- Existing feature flags and emergency stop remain effective.
- Non-AI workflows continue to operate during provider outages and deployment rollback.

---

## 4. Delivery milestones

No milestone is complete when it contains only interfaces or scaffolding. Each milestone ends with its acceptance test, migration verification, observability and documentation.

## Milestone A — Foundation and read-only Gigi (Phases 0–3)

### Phase 0 — Characterize and protect the existing system

Deliverables:

1. Create `GIGI_EXISTING_AI_AUDIT.md` with Reusable/Partial/Legacy/Missing/Remove-later sections.
2. Add characterization tests for existing Procurement threads, proposals, companion intervention dedupe, Operations Gigi and provider outage behavior.
3. Capture the current schema and migration head.
4. Define canonical ownership: AgentThread/Message/Run/ToolCall remain the records to extend.
5. Inventory all direct provider calls and every current agent mutation path.
6. Add an architecture test that fails if `intelligence/` tools receive a raw SQL/session execution tool or direct external executor.

Exit gate: existing agent, Procurement, SCM, Operations and platform regression selections pass before refactoring begins.

### Phase 1 — AI persistence, prompt registry and model gateway

Backend:

1. Add migration(s) for conversation/run/tool-call extensions and `PromptVersion`.
2. Create typed request/response/provider protocols.
3. Implement model classes `FAST`, `REASONING`, `EXTRACTION`, `EMBEDDING`.
4. Implement provider adapters, beginning with the configured Groq path and a deterministic test adapter.
5. Centralize timeouts, retryable/non-retryable errors, structured output validation, streaming, fallback routing, token budgets, tenant budgets and cost calculation.
6. Move all new calls through the gateway; migrate direct calls in `agent_service.py` behind a compatibility adapter.
7. Persist provider/model/prompt/version/usage/cost/latency on every run.
8. Never log secrets, full hidden prompts or hidden reasoning.

API:

```text
POST /api/v1/gigi/conversations
GET  /api/v1/gigi/conversations
GET  /api/v1/gigi/conversations/{id}
GET  /api/v1/gigi/conversations/{id}/messages
POST /api/v1/gigi/conversations/{id}/messages
GET  /api/v1/gigi/runs/{id}
GET  /api/v1/gigi/runs/{id}/events
```

Streaming safe events:

```text
run_started, context_ready, progress, tool_started, tool_completed,
answer_delta, evidence, action_candidate, completed, failed
```

Exit gate: one conversation streams end-to-end; restart does not lose messages; run/tool metadata and cost persist; provider-specific code is absent from module services.

### Phase 2 — Tiered Context Engine and read-only tool registry

Context Engine:

1. Build Tier 0 user/workspace/plant/role/permission/page context.
2. Build Tier 1 selected entity state, cases, risks, recent events and relationships.
3. Add on-demand Tier 2 suppliers, BOM, work orders, downstream impact, other plants, documents and prior outcomes.
4. Add explicitly requested Tier 3 deep history only.
5. Carry source, observed/computed time, freshness, confidence and evidence references.
6. Validate page context server-side; never trust entity IDs or scope supplied by the browser.
7. Add deterministic context compression with a byte/token budget.

Tool registry:

- one immutable versioned registry;
- Pydantic input and output schemas;
- permission/capability predicate;
- risk and side-effect class;
- timeout and idempotency contract;
- domain owner;
- evidence/reference extraction;
- no arbitrary SQL, HTTP or shell tool.

First read-only tools:

- Factory: context, entity state/history, events, cases, trace, relationships, impact, work, approvals and entity search.
- SCM: material state/projection, readiness, horizon, risks, recommendations, run comparison, supplier context and data health.
- Procurement: requirement, RFQ, quotes, PO/history, supplier commercial context and receipts.
- Operations: line/work-order/equipment state, deviation, recovery case/strategies/history.

Exit gate: a scoped question about a selected material returns only authorized tool-derived evidence; forged tenant/plant/entity context is rejected.

### Phase 3 — Natural multi-tool runtime and shared evidence UI

Runtime:

1. Implement typed goal interpretation and investigation plan generation.
2. Use the bounded LangGraph loop with configurable limits for decisions, tool calls, elapsed time and context.
3. Support hypothesis/evidence iteration without persisting or streaming chain-of-thought.
4. Require explicit evidence sufficiency before operational conclusions.
5. Return the structured contract: answer, evidence, risks, recommendations, available actions, uncertainties and follow-ups.
6. Add numeric-claim validation against referenced tool outputs.
7. Implement stale/conflict/tool-failure response behavior.
8. Persist safe progress and tool events.

Frontend:

1. Add one `GigiProvider` at the authenticated product-shell level.
2. Make `Ask Gigi` in `ProductShell` open one persistent 420–520 px panel.
3. Send bounded route/module/entity/filter context.
4. Add conversation, composer, progress, evidence, uncertainty and context-badge components.
5. Preserve conversation while switching modules.
6. Add `/gigi` with conversation history and broad investigations.
7. Keep legacy panels as adapters until parity is proven.

Primary proof:

> Why is MAT-182 critical?

Gigi must use actual material state, planning change and downstream impact tools, cite them and refuse unsupported values.

---

## Milestone B — Roles, memory, decisions and governed actions (Phases 4–7)

### Phase 4 — One runtime with role profiles

Implement declarative profiles for:

- SCM planner;
- Procurement buyer;
- Operations users;
- manager;
- leadership.

Each profile defines objectives, skill bundle, context defaults, memory scopes, response depth and escalation behavior. Profiles filter tools before prompt construction; prompt instructions are not authorization.

Exit gate: the same question asked by a planner and leader produces appropriately different depth and available actions while using the same underlying facts.

### Phase 5 — Governed memory

1. Migrate key/value `AgentMemory` records into typed/scoped memory.
2. Implement conversation summaries without deleting recent raw turns.
3. Add user preferences that never override authority/current state.
4. Add procedural memories linked to approved knowledge.
5. Add episodic, factory-pattern and team-decision memory only from verified evidence.
6. Implement candidate → evidence validation → scope/type classification → policy-controlled write.
7. Implement validity, expiry, re-verification, supersession, deletion/retention and user visibility controls.
8. Never send memory to a model without labelling it remembered/non-current.

Exit gate: a verified prior shortage can be retrieved for a similar material problem; an unverified chat claim is not stored as a factory pattern.

### Phase 6 — Decision Intelligence and simulations

Create a deterministic `DecisionService` that normalizes candidates from existing engines into:

```text
strategy, parameters, expected impact, cost, time to effect,
operational risk, feasibility, authority, constraints,
evidence, simulation reference and rank
```

Integrate:

- SCM pull-in/push-out/cancel/new-buy/transfer scenarios;
- Operations recovery simulation;
- production-reschedule evaluation where an authoritative engine exists;
- policy/authority lookup;
- cross-domain constraint handling.

The LLM chooses investigations and explains trade-offs; deterministic services provide quantities, dates, costs, feasibility and scores.

Exit gate: Gigi compares pull-in, interplant transfer and production reschedule for the acceptance fixture and exposes missing/unavailable options honestly.

### Phase 7 — Governed action proposals

1. Register `propose_action_intent`, policy, approval and status tools.
2. Do not expose executor or connector-write tools to the runtime.
3. Require a valid simulation/evidence reference for high-consequence candidates where applicable.
4. Convert compatible legacy `AgentProposal` records into or link them to `ActionIntent`.
5. Render structured action cards with expected outcome, cost, evidence and approval requirement.
6. Refresh the card from shared action state after approval/execution/outcome.
7. Preserve explicit human confirmation and prohibit self-approval.

Exit gate: Gigi can propose an SCM PO reschedule, but cannot approve or execute it. Shared policy/approval/execution/verification completes the lifecycle.

---

## Milestone C — Knowledge, proactive intelligence, learning and hardening (Phases 8–12)

### Phase 8 — Production knowledge/RAG

1. Extend document metadata with checksum, authoritative source, validity, ACL and canonical entity links.
2. Preserve section/page/version metadata during chunking.
3. Replace JSON placeholder embeddings with pgvector-backed vectors through a forward migration.
4. Implement configured embedding provider through the central gateway.
5. Add asynchronous, idempotent indexing/re-indexing jobs.
6. Build hybrid retrieval: vector similarity + text search + metadata/ACL/entity/validity filters.
7. Treat retrieved text as untrusted data; isolate it from system/authority prompts.
8. Mark expired/superseded documents and never silently use drafts as approved procedures.
9. Add retrieval evaluation with known relevant/irrelevant documents.

Exit gate: an authorized user receives a cited answer from the current approved SOP/contract; another plant/role cannot retrieve it; prompt-injection text cannot change tool authority.

### Phase 9 — Factory-wide proactive intelligence

1. Create `AIInvestigation` and trigger-policy/deduplication services.
2. Subscribe to the existing outbox for high-value SCM, Procurement, Operations, action-failure, overdue approval and critical-case events.
3. Apply deterministic relevance/severity gates before calling a model.
4. Deduplicate by tenant, plant, entity and risk-window signature.
5. Suppress resolved, low-severity, repetitive and stale triggers.
6. Run investigations in Celery with retry/dead-letter visibility.
7. Produce findings linked to evidence, notification, case/work and optional briefing.
8. Extend existing companion preferences, quiet hours, snooze/dismiss and emergency stop.

Exit gate: one shortage event creates one useful investigation for relevant users; replay/noise does not generate duplicate notifications or runs.

### Phase 10 — Persisted briefings

Implement:

- morning personal brief;
- end-of-day brief;
- Operations shift handoff adapter;
- weekly manager brief.

Brief items come from work, cases, changes, approvals, supplier follow-ups and resolved outcomes. Every item deep-links to evidence. Generation is background and idempotent per user/type/period. User viewed/dismissed state persists.

Exit gate: the acceptance user sees a morning brief containing the new MAT-182 risk and verified prior-day outcomes without invented metrics.

### Phase 11 — Verified experience and learning

1. Create `AgentExperience` only after meaningful outcomes are verified.
2. Store problem signature, bounded context reference, candidates, selected strategy, prediction, actual outcome, cost/time/value and feedback.
3. Add similar-case retrieval with tenant/plant/entity/domain controls.
4. Calculate strategy effectiveness, time to effect, average cost, predicted-versus-actual error and supplier acceptance from records.
5. Use effectiveness as one transparent ranking feature, never hidden self-modifying policy.
6. Add feedback APIs/UI and correction workflows.
7. Do not implement online fine-tuning or self-training.

Exit gate: a later similar shortage surfaces the verified episode as historical evidence and explains how it affected ranking.

### Phase 12 — Evaluation, security, reliability and launch hardening

Evaluation:

- deterministic golden fixtures;
- entity-resolution and retrieval precision;
- tool selection/efficiency;
- numeric grounding;
- recommendation feasibility;
- permission correctness;
- uncertainty behavior;
- action conversion/outcome effectiveness;
- regression scorecards per prompt/model version.

Security:

- cross-tenant and cross-plant denial;
- role tool filtering;
- document ACL enforcement;
- self-approval prevention;
- prompt injection and indirect injection tests;
- no raw SQL/shell/general HTTP tool;
- secret/PII/log redaction;
- rate limits, budgets and emergency shutdown;
- retention/export/delete behavior.

Reliability:

- provider timeout, retry and circuit-breaker behavior;
- safe multi-provider fallback;
- idempotent message submission and background jobs;
- reconnectable SSE using event sequence IDs;
- cancellation and worker-restart recovery;
- bounded context/tool/latency/cost;
- database indexes and PostgreSQL query plans;
- load tests for simultaneous conversations, investigations and brief generation.

Observability:

- run, model and tool latency;
- tokens and cost by tenant/user/role/run type/model;
- tool failures and denials;
- grounding failure rate;
- proactive suppression/dedupe rate;
- recommendation/action/outcome funnel;
- queue age and failed jobs;
- OpenTelemetry correlation from HTTP → run → tool → action/event.

Documentation:

- `GIGI_EXISTING_AI_AUDIT.md`;
- `GIGI_ARCHITECTURE.md`;
- `GIGI_TOOL_REGISTRY.md`;
- `GIGI_ROLE_PROFILES.md`;
- `GIGI_EVALS.md`;
- operations/security/runbook documentation;
- final `GIGI_AI_READINESS.md`.

Production declaration is forbidden until every readiness row has evidence and all P0 security/safety tests pass.

---

## 5. Canonical end-to-end acceptance test

Fixture:

- Plant A and Plant B;
- material MAT-182;
- Honda ECU-A;
- Supplier X;
- work order WO-981;
- Line 3;
- purchase order PO-812;
- healthy baseline;
- PO delayed four days and Honda demand increased 11%;
- resulting four-day shortage;
- candidates: PO pull-in, interplant transfer and production reschedule.

User question:

> Why did MAT-182 become critical and what should we do?

Required assertions:

1. One authenticated conversation and message are persisted.
2. AgentRun records tenant, plant, user, membership, role profile, model and prompt version.
3. Page/entity context resolves MAT-182 canonically.
4. Runtime calls material state, planning comparison, downstream impact and supplier context.
5. Every numerical claim maps to a referenced tool result.
6. Runtime simulates at least two feasible candidates through real domain engines.
7. DecisionService ranks candidates with explicit constraints/evidence.
8. Gigi returns a natural structured response with uncertainty where applicable.
9. User selection produces an ActionIntent, not an external mutation.
10. Policy requires manager approval; planner cannot self-approve.
11. Fake connector execution creates an external receipt.
12. SCM replans from the resulting canonical event/state.
13. Outcome verification proves the shortage removed independently of execution success.
14. `AgentExperience` stores the verified prediction-versus-outcome episode.
15. Correlation trace connects conversation/run/tools/action/event/state/verification.

Failure variants:

- stale supplier commitment;
- missing material mapping;
- one tool timeout;
- simulation failure;
- unauthorized action request;
- successful connector execution but remaining shortage;
- conflicting manual/import source values;
- provider unavailable;
- duplicated user message/event;
- cross-tenant/cross-plant entity injection;
- malicious instructions inside an uploaded SOP.

---

## 6. Release strategy

### Stage 1 — Internal read-only

- Gigi panel and material investigation;
- no mutation/proposal tools;
- deterministic test provider plus one configured provider;
- evaluation logging enabled;
- staff-only feature flag.

### Stage 2 — Design-partner read-only

- real customer data with source freshness warnings;
- approved knowledge retrieval;
- role profiles and persistent conversation;
- shadow evaluation against planner answers;
- explicit feedback collection.

### Stage 3 — Simulations and proposals

- simulation tools;
- ActionIntent proposal only;
- policy/approval UAT;
- fake/simulated connectors;
- action/outcome trace review.

### Stage 4 — Controlled production

- production provider secrets/budgets;
- OPA enforcement where configured;
- approved ERP connector executor categories only;
- monitoring/on-call/runbooks/kill switch;
- per-tenant rollout and rollback flags.

### Stage 5 — Proactive/briefing expansion

- begin with one critical SCM trigger;
- measure usefulness and suppression;
- expand event types only after signal quality is proven.

---

## 7. Production readiness gates

### Functional

- All Phase 0–12 acceptance tests pass.
- Canonical material investigation and cross-domain fixture pass in PostgreSQL.
- Conversation survives navigation/reconnect/restart.
- Action cards track the real ActionIntent lifecycle.
- Briefings and experience reuse work from persisted evidence.

### Safety/security

- Tenant isolation: 100% passing.
- Plant/role/document restrictions: 100% passing.
- Consequential action bypass attempts: 100% blocked.
- Numeric grounding fixture: 100% of checked claims sourced.
- Prompt-injection fixture: no authority/tool escalation.
- No hidden chain-of-thought stored or streamed.

### Reliability/SLO targets

- Simple read-only response begins within 5 seconds at target percentile agreed for pilot.
- Multi-tool investigation begins streaming immediately and targets completion within 20 seconds.
- Provider outage leaves non-AI product fully usable and returns an explicit degraded state.
- No event/message duplication under retries.
- Proactive jobs are recoverable after worker restart.

### Operational

- Per-tenant daily/monthly budgets enforced.
- Provider and model allowlists configurable.
- Kill switch tested.
- Dashboards and alerts available for latency, errors, cost, grounding and queues.
- Retention, export and deletion jobs tested.
- Rollback leaves existing Procurement/SCM/Operations workflows operational.

---

## 8. Recommended implementation order

1. Complete Phase 0 audit and characterization tests.
2. Extend existing persistence and build the gateway.
3. Build read-only Context Engine and typed tools.
4. Deliver the shared panel with the single-material proof.
5. Add role profiles and governed memory.
6. Add deterministic cross-domain DecisionService and simulations.
7. Enable ActionIntent proposals only after safety tests.
8. Implement pgvector knowledge retrieval and injection defenses.
9. Add one high-value proactive SCM investigation.
10. Add briefings, then verified experience learning.
11. Run the complete hardening matrix.
12. Publish `GIGI_AI_READINESS.md`; roll out tenant-by-tenant only if it says `YES` with evidence.

Milestones A, B and C must be delivered sequentially. Phase implementation may use feature flags, but missing functionality must not be labelled complete merely because an interface exists.

---

## 9. Final success condition

The AI plane is complete only when the deterministic fixture proves:

```text
User goal
  → scoped context
  → natural multi-tool investigation
  → authoritative domain evidence
  → cross-domain candidate simulations
  → transparent decision comparison
  → evidence-backed response
  → governed ActionIntent
  → policy and human approval
  → safe execution
  → event/state recomputation
  → independent recovery verification
  → verified experience reuse
```

with tenant isolation, role filtering, source freshness, prompt-injection defense, idempotency, complete traceability, cost controls and safe provider failure.

