# Gigi Tool Registry

| Tool | Version | Domain | Effect | Source |
|---|---:|---|---|---|
| `factory.entity_state` | 1 | Factory | Read only | `FactoryStateService.now` |
| `factory.relationships` | 1 | Factory | Read only | canonical relationship graph |
| `factory.downstream_impact` | 1 | Factory | Read only | bounded graph traversal |

The registry rejects external-action tools. SCM, Procurement and Operations adapters must call domain services and return typed evidence references; they must not accept arbitrary SQL, URLs or executable code.
