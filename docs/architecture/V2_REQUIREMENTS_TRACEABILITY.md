# GenuineGigs V2 requirements traceability

Date: 2026-08-12

This is the completion evidence map for the hard execution contracts in
`GenuineGigs_V2_PLAN_IMPLEMENTATION_READY.md` sections 53–73 and
`GenuineGigs_V2_PLAN_UI_IMPLEMENTATION_READY.md` sections 74–101. A local pass
does not claim customer, live-source, live-machine or measured-outcome evidence.

## Engineering and domain contract

| Plan requirement | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| Preserve V1 stack and behavior | Existing FastAPI/SQLAlchemy/Celery API and Next.js application extended additively; `/v2` and `/api/v2`; migrations 0045–0052 | Complete API suite includes V1 and V2: 425 passed | Pass locally |
| PostgreSQL canonical state, Redis/Celery coordination, object storage and outbox | Existing deployment/configuration retained; V2 models use canonical SQLAlchemy store and `EventOutbox` | Migration, outbox, worker and deployment tests | Pass locally |
| No new Kafka/Neo4j/lakehouse/microservice foundation | No prohibited infrastructure introduced; edge agent is the explicitly required Phase 4 boundary service | Repository/deployment audit | Pass |
| Identity/organization/plant modules | V1 tenants, users, memberships and plant access reused; `PlantArea`, `ProductionLine`, `PlantAsset`, `PlantShift` added | role/scoping API tests | Pass locally |
| Production plan/actual/forecast | Canonical work orders and plan/actual points; deterministic recent-rate baseline with confidence | calculation and performance tests | Pass locally |
| Four baseline detectors | behind-plan, downtime, rejection-rate and material-readiness detectors; governed detector rules; SPC extension | lifecycle and operational tests | Pass locally |
| Idempotent deviation lifecycle | recurrence key and active-state uniqueness; explicit assign/acknowledge/resolve/verify commands | lifecycle, concurrency and hard API contract tests | Pass locally |
| Action routing/dependencies/SLA | Operational Action linked to canonical V1 Task; dependency records; deterministic role/SLA routing | action lifecycle, dependency and minute-cadence tests | Pass locally |
| Reproducible Value Ledger | deterministic estimated impact projection, immutable human-verified recovery and authority-scoped APIs | value formula, reconciliation-worker and permission tests | Pass locally |
| Material readiness and V1 procurement linkage | requirement/inventory/commitment snapshots; automatic risk; links to existing V1 procurement lifecycle | readiness and golden procurement scenarios | Pass locally |
| Quality recovery | quality events, lot containment, SPC, governed NCR/CAPA investigation/effectiveness/closure | quality lifecycle/API tests | Pass locally |
| Maintenance recovery | faults, maintenance work, spare dependency, start/wait/complete and linked downtime/deviation progression | maintenance lifecycle test | Pass locally |
| Improvement Studio | evidence-ranked opportunity, experiment and estimated/verified benefit records | operational scenario tests | Pass locally |
| Knowledge/RAG governance | revisions, approval/retirement, ACL/scope/validity, cited chunks and active-only retrieval | retrieval and idempotent indexing-worker tests | Pass locally |
| Objective agents | named production/material/reliability/quality agents; context snapshot, bounded tools, recommendation evidence and idempotent trigger | agent runtime tests | Pass locally |
| Gigi prepare/approve/execute | grounded read/query, expiring prepared action, explicit human execution and activity audit | Gigi API/scenario tests | Pass locally |
| Connector SDK and canonical normalization | health/schema/read/execute/read-back contract; capabilities, mappings, cursors, lineage and read-only defaults | 47 connector conformance tests and ingestion scenarios | Pass locally |
| Required V2 API surface | all context, command, operations, deviations, actions, materials, value, Gigi, integrations and SSE routes | `test_v2_plan_contract.py`: exact 43 method/path pairs; arbitrary action/deviation PATCH forbidden | Pass locally |
| SSE-first live updates | canonical topic stream and TanStack Query invalidation | API and Playwright operating-loop acceptance | Pass locally |
| Required named workers/cadences | canonical task identities including sync, outbox, line/readiness/deviation/SLA/value/briefing/handover/knowledge/agent | worker registry, behavior and cadence tests | Pass locally |
| Canonical demonstration data | Pune Plant, Machining, L1–L4, Shift B, four work orders, plan/actual trajectory, downtime/material/quality/resolved deviations, actions/value | seeded API and browser scenarios | Pass locally |
| OT edge boundary | Go 1.23, local SQLite, outbound HTTPS, signed configuration, allowlisted OPC UA/MQTT sources, durable replay | official Go container passes tamper and outage/restart/replay-once tests | Pass locally |
| Real customer IT source | Connector foundation and simulation exist; no customer system is available in repository scope | Requires customer connection/UAT evidence | External gate |
| Real/representative machine source | Edge runtime and representative mappings exist; no reachable plant machine is available | Requires representative OPC UA source and security/reliability exercise | External gate |
| Predictive performance above baseline | Rolling baseline comparison API/UI exists; repository demonstration data is insufficient for production claims | Requires representative dataset backtest | External gate |
| Pilot/commercial outcomes | Value definitions and evidence capture exist | Requires manufacturer agreement and 30–60 day before/after metrics | External gate |

## Frontend and interaction contract

| Plan requirement | Implementation evidence | Verification | Status |
| --- | --- | --- | --- |
| Exact `/v2` route map | home, my-work, operations/line/deviation, materials/readiness/procurement, quality, maintenance/asset, improvement, knowledge, integrations and admin routes | Next production build: 42 total routes; Playwright flagship traversal | Pass locally |
| Professional manufacturing visual system | centralized neutral industrial tokens, semantic severity colors, Manrope/Lucide, dense operational layouts; no random gradients or generic marketing hero | screenshot review at required breakpoints | Pass locally |
| Responsive shell/context | desktop sidebar, tablet collapse, mobile navigation/scrim, plant/shift/source freshness, search and Gigi | desktop/tablet/mobile Playwright | Pass locally |
| Exception-first Command Center | operating pulse, role focus, functional units/time/value loss measure, deviations, decisions, Gigi activity and data health | API and browser acceptance | Pass locally |
| Line/deviation/recovery loop | plan/actual/forecast, timeline, causal evidence, dependencies, explicit recovery commands and verification | operating lifecycle plus browser traversal | Pass locally |
| My Work | NOW/NEXT/WAITING/DONE, consequence/deadline/dependency, real commands, contextual Gigi | mobile browser action-context assertion | Pass locally |
| Material/procurement/quality/maintenance/improvement | API-backed operational workspaces; V1 procurement remains canonical detail | typecheck, build, API and browser suites | Pass locally |
| Gigi modes and trust | global panel, contextual prefilled questions, proactive insight structure, confidence/evidence, failure refusal and recoverable errors | browser and API tests | Pass locally |
| Loading/empty/stale/error states | reusable operational primitives plus explicit screen states; global source freshness degrades stale sources | state-contract source audit and browser checks | Pass locally |
| Role-aware routes and financial redaction | persona navigation, backend authorization, financial-field redaction and admin-only infrastructure | role matrix and browser authority test | Pass locally |
| Accessibility | skip link, semantic status text, visible action labels, focus/Escape, touch targets, reduced motion and no critical axe violations | official Playwright desktop/tablet/mobile projects | Pass locally |
| Internationalization | plant locale/timezone/currency through shared formatting provider; no India-only V2 formatting | locale/API and source tests | Pass locally |
| Performance | server read-model budget plus production JS/CSS limits | p95/payload tests; 2.67 MB JS, 385 KB largest JS, 256 KB CSS | Pass locally |
| Final UI data source | all final V2 screens use V2 queries/backend seed; no page-local mock arrays | source audit, API/browser execution | Pass locally |

## Evidence commands

```text
cd apps/api && .venv/bin/pytest -q
npm run typecheck
npm run build:web
npm run check:v2-performance
docker run ... mcr.microsoft.com/playwright:v1.61.1-noble npx playwright test ...
docker run ... golang:1.23 go test ./...
```

The repository can satisfy local implementation and verification. Phase 2 live
IT, Phase 4 live/representative machine, production soak, customer UAT and pilot
outcome gates require external systems and people and remain explicitly open.
