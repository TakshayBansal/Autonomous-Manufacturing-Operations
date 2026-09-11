# Change Review Report

Review date: 2026-07-10

Reviewed scope:
- Plans: `PLAN.md`, `PLAN2.md`
- Latest commit: `649aaac Made some changes`
- Working tree: untracked `.gitattributes`

## Executive Summary

The repo now implements a substantial first version of the Manufacturing Agent OS procurement slice: monorepo setup, FastAPI backend, Next.js operations console, PostgreSQL/Redis/MinIO Docker Compose, seeded manufacturing data, procurement workflow models, document validation/extraction paths, integration outbox, Oracle/SAP adapter boundaries, role-based UI surfaces, and API/E2E test scaffolding.

The implementation is directionally aligned with the plans, but it is not yet complete against the production-hardening acceptance bar. The biggest immediate gaps are verification failures, stale generated API contracts, dependency/test setup issues, and several planned areas that are present as skeletons or simulation paths rather than fully hardened production behavior.

## Findings

### High: API tests fail on document upload worker import

`npm run test:api` currently fails with `ModuleNotFoundError: No module named 'billiard'` when `/documents/upload` enqueues document processing.

Relevant code:
- `apps/api/app/main.py:578` uploads the document, then calls `document_service.enqueue_document_job`.
- `apps/api/app/documents.py:236` imports `app.workers.process_document`.
- `apps/api/app/workers.py:5` imports `SoftTimeLimitExceeded` from `billiard.exceptions`.

Impact: document upload/security validation is one of the core hardening-plan requirements, and the local verification path is currently broken.

Recommendation: make the Python dev environment reproducible and ensure `billiard` is installed when tests run. Since the code imports `billiard` directly, either add it as an explicit dependency or adjust the worker import strategy. Then rerun `npm run test:api`.

### High: Generated API contract is stale

`npm run check:api-contract` fails with:

```text
Generated API contract is stale. Start the API and run `npm run generate:api`, then update its OpenAPI hash.
```

Relevant files:
- `packages/shared/src/api.generated.ts:1`
- `apps/api/scripts/check_openapi_contract.py:11`

Impact: frontend/shared TypeScript contracts may not match the current FastAPI surface, which is risky because many workflow APIs were added or changed.

Recommendation: start the API from the current code, regenerate `packages/shared/src/api.generated.ts`, and commit the updated generated contract.

### Medium: Standalone typecheck fails because E2E test dependencies are not installed in the web workspace

`npm run typecheck` fails because `apps/web/e2e/role-workflows.spec.ts` imports `@playwright/test` and `@axe-core/playwright`, but `apps/web/package.json` does not declare those packages.

Relevant code:
- `apps/web/e2e/role-workflows.spec.ts:1`
- `apps/web/e2e/role-workflows.spec.ts:2`
- `apps/web/package.json:17`

Impact: the documented development check in `README.md` does not pass from this workspace. Production `npm run build:web` passes, but the explicit typecheck command fails.

Recommendation: add the E2E dependencies to devDependencies, or exclude `e2e/**/*.ts` from the app typecheck and typecheck E2E through Playwright separately.

### Medium: Supplier and PO portal tokens are exposed in email bodies and API response payloads

RFQ publishing returns raw supplier portal tokens and embeds them in email body text.

Relevant code:
- `apps/api/app/domains/workflows.py:627`
- `apps/api/app/domains/workflows.py:632`
- `apps/api/app/domains/workflows.py:636`
- `apps/api/app/domains/workflows.py:643`

Impact: useful for a pilot, but not production-grade. Raw access tokens can leak through logs, screenshots, browser dev tools, email archives, and support traces.

Recommendation: move toward one-time links, do not return raw tokens from normal API responses, redact token-bearing response bodies from idempotency storage, and add expiry/used/revoked enforcement tests.

### Medium: SAP adapter is contract-only, not a real integration implementation

The plan calls for Oracle-first with SAP supported through the same adapter contract and documented endpoint mappings. Oracle has a partial live path, but SAP currently returns a `contract_only` response for PO push.

Relevant code:
- `apps/api/app/erp.py` `SapS4HanaAdapter.push_purchase_order`

Impact: this satisfies a skeleton/contract placeholder, but not live SAP support.

Recommendation: document SAP as explicitly non-live for V1, or add OData request implementation and contract fixtures before claiming SAP support beyond adapter shape.

## Change Summary

Major changes made in the latest commit:

- Added production-minded API schemas, middleware, rate limiting, metrics, security/session code, document processing, storage support, integration outbox, ERP adapters, background workers, and identifier helpers.
- Expanded database models for workflow transitions, approval decisions, supplier portal tokens, document validation, quote field verification, integration connections/jobs/references/outbox attempts, and reconciliation results.
- Reworked procurement workflow services for requirements, RFQs, quote intake, verification, comparisons, negotiations, awards, PO drafts, ASN/gate/receipt/inspection, inventory impact, exception cases, audit, and role-specific task queues.
- Added Next.js role workbenches and workflow controls for procurement, RFQ builder, quotes, evidence, comparisons, negotiations, approvals, PO drafts, inbound/store/quality, cases, outbox, integrations, audit, and admin.
- Added Docker Compose services for PostgreSQL, Redis, MinIO, Mailpit, migration, seed, API, Celery worker/beat, and web.
- Added API tests for workflow/security contracts and E2E Playwright test scaffolding.
- Updated README, infra notes, environment examples, and product/architecture docs.

Working tree note:

- `.gitattributes` is currently untracked and normalizes text files plus LF endings for TypeScript, JavaScript, JSON, CSS, and Markdown.

## Plan Coverage

Implemented or substantially present:

- Greenfield monorepo with Next.js, FastAPI, PostgreSQL, Redis, MinIO, Docker Compose.
- Core tenant/plant/user/role/task/case/audit/procurement/inbound/integration models.
- Role-based workbench UI for the planned operational roles.
- Simulated RFQ/email and ERP outbox paths.
- Deterministic quote extraction and field verification model.
- Landed cost, quote comparison, award, PO draft, inbound receipt/inspection, inventory impact, and exception workflow paths.
- Oracle adapter boundary and local ERP simulation.
- Redis/Celery worker structure.
- Document quarantine/validation logic for PDF, XLSX, images, encrypted/corrupt files, macro workbook rejection, formula neutralization, and OCR hooks.

Partially implemented or still missing:

- Fresh local verification is not green because API tests, typecheck, and API contract check fail.
- Supplier portal and PO acknowledgement flows exist at API level, but need stronger token handling and UI/test coverage.
- Real ERP dispatch is still mostly local/simulation plus partial Oracle; SAP is a skeleton.
- Document security is implemented, but the worker import failure blocks the upload processing test.
- E2E tests are present but were not run in this review because a full local app stack was not started.
- Broad IDOR/RBAC coverage exists in pieces, but the plan calls for every ID-based endpoint to be covered.
- Backup/restore and deployment docs are light compared with the Week 5 hardening plan.

## Verification Results

Commands run:

```text
npm run test:api
```

Result: failed. 28 tests passed, 1 failed. Failure: missing `billiard` import during document upload worker import.

```text
npm run typecheck
```

Result: failed. Missing `@playwright/test` and `@axe-core/playwright` type/module declarations for E2E tests.

```text
npm run check:api-contract
```

Result: failed. Generated OpenAPI TypeScript contract is stale.

```text
npm run build:web
```

Result: passed when rerun outside the sandbox. The first sandboxed run compiled but failed with a Windows `EPERM` spawn error during TypeScript; the escalated rerun completed successfully.

## Recommended Next Steps

1. Fix the Python worker dependency/test environment issue and rerun `npm run test:api`.
2. Regenerate and commit `packages/shared/src/api.generated.ts`.
3. Fix web typecheck by adding E2E dev dependencies or separating app and E2E typecheck scopes.
4. Harden supplier/PO portal token handling before considering the pilot production-minded.
5. Add missing endpoint-level IDOR/RBAC tests for the expanded API surface.
6. Decide whether SAP is explicitly a documented skeleton for V1 or implement live OData dispatch with fixtures.
