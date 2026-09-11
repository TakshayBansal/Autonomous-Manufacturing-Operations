# GenuineGigs V2 completion audit

Date: 2026-08-12

This matrix treats both implementation-ready plans as authoritative. “Pass”
means the current worktree contains direct implementation and relevant local
verification. “Partial” does not satisfy an external/live phase gate.
Requirement-level evidence is recorded in `V2_REQUIREMENTS_TRACEABILITY.md`.

| Programme area | Status | Current evidence | Remaining proof/work |
| --- | --- | --- | --- |
| Phase 0 audit and V1 reuse | Pass | `V2_TECHNICAL_AUDIT.md`; additive `0045`; V1 Task, Notification, procurement and connector reuse | None locally identified |
| Plant operational core | Pass | Plant/area/line/asset/shift/work-order models, plan/actual, four detectors, idempotent deviations; measured flagship p95/payload budgets | Production traffic/load evidence |
| Recovery loop | Pass | Deviation → Task/Action → monitoring → verified Value Ledger scenario; scheduled SLA escalation and the complete named API contract | Production worker soak evidence |
| Command Center and line operations | Pass | API-backed home, overview, line, loss, deviation and My Work routes; SSE invalidation; desktop/tablet/mobile browser acceptance | Production-user UAT |
| Gigi grounding | Pass locally | Grounded briefing/query plus expiring prepare-action, explicit human confirmation, immutable execution audit and activity APIs | Live model/provider evaluation remains deployment evidence |
| Connector platform | Partial | SDK/conformance, audited read-only setup, versioned mappings, health/staleness, cursor-based sync, canonical normalization for production/quality/inventory/machine/maintenance records, ingestion lineage and duplicate protection | Phase 2 still requires a real customer source and no parallel critical copy; customer UAT absent |
| Material Readiness / Procurement V2 | Pass locally | Canonical requirements/inventory/commitments, V1 links, automatic recompute, shortage deviation | Phase 3 real-world earlier-detection outcome measurement |
| Quality recovery | Pass locally | Inspection/rejection and SPC detectors, lot containment, value Pareto, governed NCR/CAPA investigation → action → effectiveness verification → closure, audit/outbox evidence and responsive recovery UI | Live repeatable measured-outcome gate remains external |
| Maintenance recovery | Pass locally | Faults, repeat analysis, spares and governed start/wait/complete recovery; completion closes linked fault/downtime, advances deviation to monitoring and writes audit/outbox evidence | Live CMMS/customer history and measurable response/resolution gate |
| Improvement Studio | Pass locally | Evidence-ranked opportunities, experiments and separate estimated/verified benefit records | Statistical evaluation beyond seeded example |
| Predictive intelligence | Partial | Actionable baseline output/material risk with confidence/evidence | Dataset backtests proving performance above simple baseline; failure/quality/bottleneck models await data |
| Notifications/search/briefings | Pass locally | Grouped notifications, entity search, persistent verified start briefing, and governed end-of-shift generation/edit/verify/publish | Broader model-backed natural-language retrieval remains deployment evidence |
| Operational setup | Pass locally | Staged setup profile plus responsive create/edit interactions for scoped areas, lines, use case, data domains and KPI rules; every mutation audited/outboxed | Customer-specific activation UAT |
| OT edge | Pass locally | Go outbound-only/store-forward source, Ed25519 config verification, canonical mappings, health, idempotent alarm → deviation test; reproducible module checksums; official Go 1.23 container passes signed-config tamper rejection and durable outage/restart/replay-once tests | Real/representative OPC UA source and live reliability/security gate |
| Multi-plant | Pass locally | Context-preserving site projection, versioned KPI definitions/context dimensions, distinct-site systemic-loss proof, governed best-practice transfer with target-site outcome, and evidence/limitation-aware corporate Gigi briefing | Real comparable second-site operating data remains an external gate |
| Knowledge layer | Pass locally | Governed revisions, validity/scope metadata, approval retirement, cited chunks, active-only structured/lexical retrieval and `/v2/knowledge` UX | Production embeddings/vector backend and document extraction security soak |
| Bounded autonomy | Pass locally | Mature governed runtime primitives, recovery orchestration, expiring V2 prepared actions, explicit confirmation, execution audit and named V2 agent trigger | Production policy/UAT evidence |
| Value APIs | Pass locally | Authority-scoped summary/deviation/verify endpoints, reproducible inputs and estimated/verified separation | External finance acceptance |
| Worker/schedules | Pass locally | Canonically named connector/outbox/line/readiness/deviation/SLA/value/briefing/handover/knowledge/agent tasks; idempotent knowledge/value behavior; 1/5/15 minute safety-net cadences | Production broker/worker soak evidence |
| Security/permissions/audit | Pass locally | Tenant/plant scoping, admin/corporate/quality/financial authority boundaries, role-matrix tests, financial-field redaction, mutation audit/outbox and edge identity/config checks | Edge certificate cryptographic verification and external security review remain deployment gates |
| Accessibility/responsive UX | Pass locally | Semantic status text/icons, skip navigation, functional labelled mobile navigation/scrim, keyboard focus treatment, touch targets, contextual Gigi focus/Escape behavior, reduced-motion and responsive CSS; official Playwright container passed flagship axe checks and workflows at desktop, tablet and mobile breakpoints, including mobile overflow assertions and screenshots | Broader assistive-technology and production-user UAT |
| Internationalization/performance | Pass locally | Plant-scoped locale/timezone/currency contract and shared V2 format provider; no hardcoded regional formats; measured flagship read-model p95/payload and production JS/CSS asset gates | Production traffic/load testing remains deployment evidence |
| Pilot and commercial gates | External | Honest limitations documented | Manufacturer agreement, redacted/live data, before/after metrics and 30–60 day outcome cannot be proven by repository code |

## Immediate closure order

1. Run the live source, representative machine, customer UAT and measured-outcome phase gates.
2. Perform production broker/worker, object-storage and security soak testing.
3. Keep customer/live phase gates explicitly open until external evidence exists.

The full objective is therefore not yet complete. Passing local builds cannot be
used to claim the customer, live-integration, live-machine, or measured-outcome
gates.
