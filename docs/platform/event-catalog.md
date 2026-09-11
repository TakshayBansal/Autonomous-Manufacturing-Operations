# Canonical event catalog

Canonical events use lower-case dotted names, an explicit integer version,
tenant/site scope, actor, correlation/causation identifiers, subject, source,
occurred/recorded timestamps, and a JSON payload validated by
`app.platform.event_registry`.

| Event | Owner | Purpose |
|---|---|---|
| `master.material.mapped` | Platform | External material identity mapped to canonical material |
| `inventory.position.updated` | Platform | Authoritative inventory position changed |
| `procurement.po.created` | Procurement | Purchase order approved/created |
| `procurement.po.delivery_rescheduled` | Procurement | Approved delivery date amendment |
| `scm.planning.completed` | SCM | Deterministic planning results committed |
| `scm.shortage.detected` | SCM | Material shortage warrants coordination |
| `operations.material.readiness.changed` | Operations | Work-order material readiness changed |
| `operations.recovery.case_opened` | Operations | Recovery case opened from a deviation |
| `operations.recovery.strategy_selected` | Operations | Authorized recovery strategy selected |
| `operations.recovery.verified` | Operations | Recovery verified against post-action evidence |
| `platform.action.*` | Platform | Governed action lifecycle |
| `platform.work.created` | Platform | Shared work entered the common queue |

Legacy event names remain consumable during migration, but new cross-module
consumers must subscribe to canonical names. Consumer receipts guarantee one
successful side effect per `(event_id, consumer_name)` and replay resets only
the delivery state, never the domain result.
