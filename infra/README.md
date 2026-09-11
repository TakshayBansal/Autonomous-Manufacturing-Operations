# Infrastructure Notes

Local services use Docker Compose:

- PostgreSQL for transactional workflow state and the Local ERP simulation adapter.
- Redis for rate limits, lockouts, and background job queues.
- MinIO for private document/object storage, with quarantine-style validation before documents enter workflow evidence.
- SMTP/Mailpit-compatible settings for approved supplier RFQ email outbox delivery.

## ERP Integration Posture

ERP access is adapter-driven. Development defaults to `ERP_PROVIDER=local` and `ERP_WRITE_MODE=simulation`, so PO and receipt writes still travel through the approval-required integration outbox before the Local ERP adapter records a simulated result.

Oracle Fusion Procurement is the first real adapter target. The adapter maps PO creation/validation/submission to Fusion Procurement draft purchase order REST resources under `/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders`, including validate and submit actions. SAP S/4HANA is represented by the same adapter contract with endpoint mappings for `API_PURCHASEORDER_PROCESS_SRV`, `API_PURCHASEREQ_PROCESS_SRV`, and `API_MATERIAL_DOCUMENT_SRV` until live credentials and recorded fixtures are available.

## Deployment Checklist

- Set a strong `SESSION_SECRET` and enable `SECURE_COOKIES=true` behind HTTPS.
- Use managed PostgreSQL with daily backups and tested restore drills.
- Run Redis with persistence enabled when queues/rate-limit state must survive restarts.
- Keep MinIO/S3 buckets private; expose documents only through short-lived scoped URLs.
- Set `ERP_WRITE_MODE=read_only` during connector onboarding and switch to `live` only after contract tests and business approval; keep the independent `ERP_LIVE_ENABLED` kill switch off until the final gate.
- Rotate Oracle/SAP/SMTP secrets through the deployment secret manager, not committed env files.
- Run `alembic upgrade head` as a one-shot deployment job before starting API or workers.
- Keep `ERP_LIVE_ENABLED=false` until an Oracle sandbox dispatch, reconciliation, and business approval are recorded.
- Run separate API, Celery worker, Celery beat, and Next.js containers from the supplied production images.
- Alert on `/health/ready`, failed document jobs, terminal outbox failures, reconciliation mismatches, and overdue tasks.

## Backup And Restore

- PostgreSQL: schedule `pg_dump` or provider snapshots; validate restore into a staging database before releases.
- MinIO/S3: enable versioning/lifecycle policies for document buckets and quarantine buckets.
- Redis: treat as reconstructable queue/cache state unless production policy requires RDB/AOF persistence.

## Restore drill

1. Stop API and workers so no new outbox or document jobs are created.
2. Restore PostgreSQL into an isolated environment and run `alembic current`.
3. Restore both private object buckets with version history intact.
4. Start Redis empty, then API, worker, and beat; queued-job recovery reconstructs pending work from PostgreSQL.
5. Reconcile every approved/dispatched integration event before enabling live writes.
6. Run the procure-to-receive smoke workflow and record the drill duration and reconciliation result.
