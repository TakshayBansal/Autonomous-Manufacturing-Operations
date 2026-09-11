# GenuineGigs Core Platform

The core platform is an incremental modular-monolith layer. Procurement,
Operations, and SCM retain their existing behaviour and routes while sharing
canonical catalog, provenance, event, state, action, and case contracts under
`/api/v1/platform`.

## Demo workspaces

Run `python -m app.platform.seed_cli` from `apps/api`. The command first applies
pending Alembic migrations, then creates isolated tenants for Procurement,
Operations, SCM, and Core Integration
using one selectable demo account: `demo.admin@genuinegigs.local` /
`Password@123`. Each tenant-local user has an internal unique email alias to
remain compatible with the legacy global `users.email` constraint; users still
sign in with the shared Account email above. The command is idempotent and
intentionally never resets an existing workspace.

Each demo tenant has a separate plant, users, features, source mappings, and
canonical starter material. Module fixture loaders may add richer test data to
their own tenant only. Demo workspaces are development/staging assets and are
blocked by the platform API guard in production.

For Docker, rebuild the one-shot image so code and migrations cannot drift:

```bash
docker compose --profile simulation run --rm --build seed-platform-demos
```

The SCM and Core Integration workspaces also receive a dated mock ERP dataset,
a completed deterministic planning run, canonical material-state projections,
and recommendation candidates. Procurement and Operations retain independent
starter masters so their domain-specific fixture suites can evolve without
changing SCM test expectations.

## First governed vertical slice

`ActionIntent → ActionPolicyEvaluation → ActionApproval → ActionExecution`
is available through the platform API. Its only executor is simulated: it
records a verified-looking outcome but does not change an ERP, supplier, or
production system. This is deliberate until an approved connector executor is
implemented.
