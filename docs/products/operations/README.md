# Operations and recovery product domain

This domain covers live production context, plan-versus-actual state,
deviations, operational actions, recovery intelligence, quality, maintenance,
shift briefings, knowledge, and multi-plant learning.

- Product plans: `plans/`
- Backend package: `apps/api/app/operations/`
- HTTP compatibility prefix: `/api/v2`
- Frontend compatibility prefix: `/v2`
- Frontend components: `apps/web/components/operations/`

The `/v2` names are retained as public compatibility routes. New internal code
should call this the `operations` domain rather than a replacement product
version.
