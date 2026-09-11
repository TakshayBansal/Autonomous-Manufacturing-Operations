# Operations domain package

| Module | Responsibility |
| --- | --- |
| `service.py` | Operational projections, deviations, workspaces, KPIs, and value |
| `state.py` | Versioned operational-state snapshots |
| `integrations.py` | Operations connector configuration and health |
| `normalization.py` | External records to canonical operations entities |
| `agents.py` | Evidence-recorded operational objective coordination |
| `router.py` | Authenticated `/api/v2` compatibility API |
| `recovery/` | Recovery ranking, lifecycle, verification, and learning |

`V2` and `V2.1` remain in database migration names and public URLs for backward
compatibility. New Python modules should use the `app.operations` namespace.
