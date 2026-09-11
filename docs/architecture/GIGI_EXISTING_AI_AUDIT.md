# Existing AI Implementation Audit

## Existing and reused

- Agent thread/message/run/event/tool persistence
- Procurement agent runtime and companion preferences
- Operations Gigi and deterministic recovery services
- canonical state, graph, trace, SCM planning and ActionIntent governance
- Prometheus/OpenTelemetry foundations

## Partially existing and consolidated

- provider routing is now behind `intelligence/gateway.py` for new Gigi work;
- context fragments are wrapped by `ContextEngine`;
- capabilities begin migration to a typed immutable registry;
- ProductShell now exposes one cross-module Gigi panel.

## Legacy/duplicate

- direct provider construction and legacy assistant routes remain compatibility paths;
- Procurement and Operations assistant panels remain until parity is measured;
- JSON embeddings remain during the forward pgvector migration phase.

## Missing after this implementation slice

- full domain-tool breadth and real multi-candidate simulation adapters;
- background proactive workers and scheduled briefings;
- pgvector hybrid indexing/retrieval;
- complete MAT-182 governed-action acceptance proof and production load/security gates.
