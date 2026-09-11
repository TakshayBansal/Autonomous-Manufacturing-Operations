# GenuineGigs documentation

For a single self-contained description of the complete implemented product—
central platform, shared Operational Cases, SCM, Procurement, Operations, Gigi,
frontend, APIs, workers, security, deployment and verification—start with
[`GENUINEGIGS_PLATFORM_AND_SCM_IMPLEMENTATION_HANDOFF.md`](GENUINEGIGS_PLATFORM_AND_SCM_IMPLEMENTATION_HANDOFF.md).
It is the recommended context document to provide to a new engineer or ChatGPT
session before asking for product or architecture changes.

The audited production execution plan for the Gigi intelligence layer is
[`plans/GIGI_AI_INTELLIGENCE_PLANE_EXECUTION_PLAN.md`](plans/GIGI_AI_INTELLIGENCE_PLANE_EXECUTION_PLAN.md).

GenuineGigs is one manufacturing operating system composed of three product
domains. The labels V1, V2/V2.1, and V3 describe the order in which the domains
were developed; they are not replacement releases.

## Product domains

| Domain | Responsibility | Documentation | Runtime |
| --- | --- | --- | --- |
| Procurement | Requirement-to-RFQ-to-PO-to-receipt execution | [`products/procurement`](products/procurement/README.md) | Existing procurement services and workbenches |
| Operations | Production visibility, deviations, recovery, quality, maintenance, and improvement | [`products/operations`](products/operations/README.md) | `apps/api/app/operations`, `/api/v2`, `apps/web/components/operations` |
| Supply chain | Material projections, shortages, pegging, scenarios, imports, and recommendations | [`products/supply-chain`](products/supply-chain/README.md) | `apps/api/app/scm`, `/scm`, `apps/web/components/scm` |

## Shared platform

Cross-domain identity, permissions, agents, connectors, eventing, workers,
storage, audit, observability, and deployment documentation belongs under
[`platform`](platform/README.md), [`architecture`](architecture), and
[`runbooks`](runbooks).

Historical plans are retained inside the relevant product directory instead of
the repository root. Source code and migrations remain the final authority when
historical plans disagree with the implementation.
