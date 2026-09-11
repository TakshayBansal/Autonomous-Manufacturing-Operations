# ADR 0001: Modular monolith and deferred infrastructure

Status: accepted

GenuineGigs Core remains FastAPI + PostgreSQL + Redis + Celery + object storage.
Domain packages communicate through platform services and canonical outbox
events. Kafka/Redpanda and Temporal are not deployed until the Phase 9 trigger
conditions are observed. The plant-edge models remain read-only scaffolding;
physical actuation is out of scope without a real safety-reviewed installation.

This decision completes the architecture phases without pretending that
unjustified infrastructure or closed-loop autonomy exists.
