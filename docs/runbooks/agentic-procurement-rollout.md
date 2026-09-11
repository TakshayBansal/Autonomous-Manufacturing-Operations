# Agentic procurement rollout

1. Apply Alembic through `0044_proactive_companion` and verify the active
   requirement/objective counts.
2. Enable `agentic_procurement_cycles` for one tenant. Run the scheduled cycle
   evaluation and confirm one objective per active requirement.
3. Monitor `/admin/events?status=dead_letter`. Replay only after correcting the
   consumer cause; completed consumer receipts are not repeated.
4. Start OPA in `shadow` mode. Compare persisted reason codes and obligations
   with existing authorization before changing to `enforce`.
5. Enable prepared work and asynchronous specialists. Confirm every finding has
   evidence and confidence and every sandbox is terminated or expired.
6. Enable the manager cockpit and autonomy centre. Publish only safe templates;
   do not expose raw Rego to workspace administrators.
7. Keep external supplier communication, awards, PO issuance, and high-impact
   decisions confirmation-bound.
8. Enable Temporal for one pilot workflow only after event replay and evaluator
   idempotency acceptance.
9. Enable Tier 2 coordination before any Tier 3 reversible execution. Keep Tier
   3 disabled if policy, receipt, or rollback evidence is incomplete.

## Companion demo acceptance

1. Restart API, event, specialist, and beat workers after applying migration 0044.
2. Sign in as `purchase.exec@genuinegigs.local`. The bottom-right companion
   presents the once-daily briefing; routine information remains a badge.
3. Create a requirement. Within the outbox interval the mascot changes to
   Preparing while the unchanged manual route remains available.
4. When the bounded specialist completes, the companion announces prepared work
   with evidence and confidence.
5. Add a blocker or overdue commitment. Warnings use a speech bubble; a genuine
   critical risk opens the panel without taking keyboard focus.
6. Demonstrate Do manually, Prepare with AI, Stop, Snooze, Dismiss, and Why now.
7. As Admin, create, simulate, and publish a role-scoped Companion trigger.

The observable chain is event outbox → consumer receipts → companion intervention
→ agent run/attempt → prepared work → SSE update. Inspect correlated records via
the existing admin event and agent-run activity endpoints.

Rollback is performed per tenant by disabling the corresponding feature flag.
Do not delete objectives, events, policy decisions, receipts, sandbox records,
or issued business records. Restore the previous signed policy bundle or return
OPA to shadow mode when policy behavior is under investigation.
