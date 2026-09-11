# Gigi Intelligence Plane

Gigi is one governed intelligence plane shared by Procurement, SCM and Operations. It is not a second source of manufacturing truth and does not own external mutations.

```text
ProductShell / /gigi
        ↓
/api/v1/gigi conversations and runs
        ↓
ContextEngine → authenticated tenant, plant, role, page and entity
        ↓
Typed ToolRegistry → FactoryState, graph, SCM, Procurement, Operations
        ↓
Bounded GigiRuntime → evidence-backed structured response
        ↓
DecisionService → normalized deterministic candidates
        ↓
ActionIntent → policy → human approval → shared execution → verification
```

## Safety boundaries

- Browser scope is a hint. `ContextEngine` resolves it again under the authenticated tenant and plant.
- Tools have typed inputs, fixed versions, role filters and declared side effects.
- `EXTERNAL_ACTION` tools cannot be registered with Gigi.
- No SQL, shell or general HTTP tool is exposed.
- Numeric operational conclusions must originate in state/domain tool results.
- Provider failure returns an explicit deterministic, grounded response; it does not affect non-AI workflows.
- Conversation memory is separate from factory truth. Only evidence-backed records can become durable typed memory.
- An action proposal always becomes the existing platform `ActionIntent`; Gigi cannot approve or execute it.

## Storage

Existing `AgentThread`, `AgentMessage`, `AgentRun`, `AgentEvent`, `AgentToolCall`, `AgentMemory`, `KnowledgeDocument`, `KnowledgeChunk` and `AgentFeedback` records are extended. Migration `0065_gigi_intelligence` adds prompt versions, investigations, briefings, verified experiences and document/entity links.

## Compatibility

Legacy Procurement and Operations assistant endpoints remain available during migration. New product work must use `/api/v1/gigi`. Removal is deferred until behavior and audit parity are proven.
