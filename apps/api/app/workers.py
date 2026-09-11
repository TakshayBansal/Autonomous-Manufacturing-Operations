from datetime import datetime, timedelta, timezone
import logging
import random
import time
import json
import os
import urllib.request

from billiard.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_ready

from app.celery_app import celery_app
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.documents import process_document_job
from app.core.metrics import JOB_FAILURES, JOB_LATENCY

REQUIRED_TASKS = {
    "app.workers.process_document",
    "app.workers.recover_queued_jobs",
    "app.workers.dispatch_integration",
    "app.workers.send_email",
    "app.workers.run_sync_job",
    "app.workers.dispatch_domain_event",
    "app.workers.publish_outbox_event",
    "app.workers.sync_connector",
    "app.workers.reconcile_line_performance",
    "app.workers.recompute_material_readiness",
    "app.workers.recompute_v2_material_readiness",
    "app.workers.evaluate_open_deviations",
    "app.workers.evaluate_action_slas",
    "app.workers.generate_shift_briefing",
    "app.workers.generate_shift_handover",
    "app.workers.calculate_value_entries",
    "app.workers.index_knowledge_document",
    "app.workers.run_agent",
    "app.workers.run_v2_agent",
    "app.workers.reconcile_operational_snapshots",
    "app.workers.log_forecast_evaluations",
    "app.workers.apply_simulated_recovery_strategy",
    "app.workers.run_scm_planning",
    "app.workers.dispatch_queued_scm_runs",
    "app.workers.monitor_case_recovery",
    "app.workers.evaluate_gigi_insights",
    "app.workers.evaluate_operational_commitments",
}


@celery_app.task(name="app.workers.monitor_case_recovery")
def monitor_case_recovery() -> int:
    from app.platform.models import OperationalCase
    from app.platform.case_service import verify_recovery
    count = 0
    with SessionLocal() as db:
        cases = db.query(OperationalCase).filter(OperationalCase.recovery_state.in_(("PENDING", "MONITORING"))).limit(250).all()
        for case in cases: verify_recovery(db, case); count += 1
        db.commit()
    return count


@celery_app.task(name="app.workers.evaluate_gigi_insights")
def evaluate_gigi_insights() -> int:
    from app.intelligence.services import refresh_case_insights
    count = 0
    with SessionLocal() as db:
        memberships = db.query(models.WorkspaceMembership).filter_by(status="active").limit(500).all()
        for member in memberships:
            user = db.get(models.User, member.user_id)
            if user: count += len(refresh_case_insights(db, user=user, membership_id=member.id))
        db.commit()
    return count


@celery_app.task(name="app.workers.evaluate_operational_commitments")
def evaluate_operational_commitments() -> int:
    from app.platform.events import DomainEvent, publish
    now = datetime.now(timezone.utc); count = 0
    with SessionLocal() as db:
        rows = db.query(models.Commitment).filter(models.Commitment.status == "active",
            models.Commitment.next_evaluation_at <= now).limit(250).all()
        for row in rows:
            task = db.query(models.Task).filter_by(id=row.task_id, tenant_id=row.tenant_id,
                plant_id=row.plant_id).first()
            evidence_received = bool(task and task.status in {"completed", "verified", "closed"}
                and (task.completion_summary or task.completed_at))
            if evidence_received:
                publish(db, DomainEvent("commitment.completed", row.tenant_id, row.plant_id,
                    "commitment", row.id, {"commitment_id": row.id, "task_id": row.task_id,
                    "evidence": task.completion_summary or "task completion timestamp"},
                    correlation_id=f"commitment:{row.id}"))
                row.status = "completed"
            else:
                publish(db, DomainEvent("commitment.overdue", row.tenant_id, row.plant_id,
                    "commitment", row.id, {"commitment_id": row.id,
                    "dependency_state": row.dependency_state}, correlation_id=f"commitment:{row.id}"))
                row.status = "overdue"
            row.next_evaluation_at = None; count += 1
        db.commit()
    return count


@celery_app.task(bind=True, name="app.workers.run_scm_planning", max_retries=3, soft_time_limit=300, time_limit=330)
def run_scm_planning(self, run_id: str) -> str:
    from app.scm import service as scm_service
    started = time.perf_counter()
    with SessionLocal() as db:
        try:
            run = scm_service.execute_run(db, run_id)
            db.commit()
            JOB_LATENCY.labels("scm", "planning_run").observe(time.perf_counter() - started)
            return run.status
        except Exception as exc:
            db.rollback()
            scm_service.fail_run(db, run_id, exc)
            db.commit()
            JOB_FAILURES.labels("scm", "planning_run", type(exc).__name__).inc()
            if self.request.retries >= self.max_retries:
                return "FAILED"
            raise self.retry(exc=exc, countdown=min(120, 2 ** self.request.retries))


@celery_app.task(name="app.workers.dispatch_queued_scm_runs")
def dispatch_queued_scm_runs() -> int:
    from app.scm import models as scm_models
    with SessionLocal() as db:
        ids = [row.id for row in db.query(scm_models.SCMPlanningRun).filter_by(status="QUEUED").order_by(
            scm_models.SCMPlanningRun.created_at.asc()).limit(25).all()]
    for run_id in ids:
        run_scm_planning.apply_async(args=[run_id], queue="scm")
    return len(ids)


@celery_app.task(bind=True, name="app.workers.dispatch_domain_event", max_retries=5)
def dispatch_domain_event(self, event_id: str) -> str:
    from app.eventing import dispatch_one
    try:
        with SessionLocal() as db:
            result = dispatch_one(db, event_id)
            from app.companion import publish
            interventions = db.query(models.CompanionIntervention).filter_by(source_event_id=event_id).all()
            for row in interventions:
                publish(row.recipient_membership_id, {"type": "intervention.created", "id": row.id})
                run = db.get(models.AgentRun, row.run_id) if row.run_id else None
                if run and run.state == "queued":
                    run_specialist.apply_async(args=[row.run_id], queue="specialists")
            return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(300, 2 ** self.request.retries))


@celery_app.task(name="app.workers.dispatch_pending_domain_events")
def dispatch_pending_domain_events() -> int:
    from app.eventing import pending_event_ids
    with SessionLocal() as db:
        event_ids = pending_event_ids(db)
    for event_id in event_ids:
        dispatch_domain_event.apply_async(args=[event_id], queue="events")
    return len(event_ids)


@celery_app.task(name="app.workers.evaluate_active_cycles")
def evaluate_active_cycles() -> int:
    from app.cycle_orchestration import evaluate
    count = 0
    with SessionLocal() as db:
        requirements = db.query(models.PurchaseRequirement).filter(
            models.PurchaseRequirement.status.notin_(["cancelled", "closed"]),
        ).all()
        for requirement in requirements:
            evaluate(db, requirement)
            count += 1
        db.commit()
    return count


@celery_app.task(name="app.workers.cleanup_sandboxes")
def cleanup_sandboxes() -> int:
    from app.sandbox import LocalSandboxProvider
    cleaned = LocalSandboxProvider().cleanup_expired()
    with SessionLocal() as db:
        expired = db.query(models.SandboxRun).filter(
            models.SandboxRun.state.notin_(["terminated", "expired"]),
            models.SandboxRun.expires_at < datetime.now(timezone.utc),
        ).all()
        for row in expired:
            row.state = "expired"
            row.terminated_at = datetime.now(timezone.utc)
        db.commit()
    return max(cleaned, len(expired))


@celery_app.task(bind=True, name="app.workers.run_specialist", max_retries=2, soft_time_limit=180, time_limit=200)
def run_specialist(self, run_id: str) -> str:
    from app.agent_schemas import SpecialistRequest
    from app.specialists import run as execute_specialist
    with SessionLocal() as db:
        agent_run = db.query(models.AgentRun).filter_by(id=run_id).with_for_update().first()
        if agent_run is None:
            return "missing"
        attempt_number = db.query(models.AgentRunAttempt).filter_by(run_id=run_id).count() + 1
        attempt = models.AgentRunAttempt(
            tenant_id=agent_run.tenant_id, plant_id=agent_run.plant_id, run_id=run_id,
            attempt_number=attempt_number, state="running", celery_task_id=self.request.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(attempt)
        agent_run.state = "running"
        db.add(models.AgentEvent(tenant_id=agent_run.tenant_id, plant_id=agent_run.plant_id,
            run_id=run_id, sequence=attempt_number * 10, event_type="specialist_started",
            payload={"label": "Analyzing authorized cycle evidence", "progress": 20}, visibility="private"))
        db.commit()
        if agent_run.cancellation_requested:
            attempt.state = agent_run.state = "cancelled"
            attempt.completed_at = agent_run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return "cancelled"
        try:
            request = SpecialistRequest.model_validate(agent_run.active_context["specialist_request"])
            sandbox_row = None
            sandbox_provider_id = None
            if request.specialist in {"quotation_normalization", "comparison_award", "invoice_reconciliation"}:
                from app.sandbox import ManagedSandbox
                manager = ManagedSandbox(db, agent_run.tenant_id, agent_run.plant_id, agent_run.correlation_id)
                sandbox_row, sandbox_provider_id = manager.create("quotation_analysis",
                    {"authorized_artifact_ids": request.authorized_artifact_ids}, ["validated-input.json"], agent_run.id)
                request_body = request.model_dump_json().encode()
                upload = manager.provider.upload(sandbox_provider_id, "request.json", request_body, "application/json")
                execution = manager.provider.execute(sandbox_provider_id, "validate_json",
                    {"input_path": "request.json", "output_path": "validated-input.json"})
                sandbox_row.state = "completed"
                sandbox_row.output_manifest = {"input": upload, "output": execution}
            result = execute_specialist(db, request, agent_run.membership_id, agent_run.id)
            if sandbox_row and sandbox_provider_id:
                manager.terminate(sandbox_row, sandbox_provider_id)
            attempt.state = "completed"
            attempt.completed_at = datetime.now(timezone.utc)
            agent_run.state = "completed"
            agent_run.completed_at = attempt.completed_at
            db.add(models.AgentEvent(tenant_id=agent_run.tenant_id, plant_id=agent_run.plant_id,
                run_id=run_id, sequence=attempt_number * 10 + 1, event_type="specialist_completed",
                payload={"label": "Prepared work is ready for review", "progress": 100,
                         "result": result.model_dump()}, visibility="private"))
            prepared = result.prepared_work[0] if result.prepared_work else None
            interventions = db.query(models.CompanionIntervention).filter_by(run_id=run_id).all()
            for intervention in interventions:
                intervention.delivery_state = "delivered"
                intervention.delivery_mode = "bubble"
                intervention.severity = "action"
                intervention.title = "Prepared work is ready"
                intervention.message = prepared.get("title", "Review the prepared result.") if prepared else "Review the prepared result."
                intervention.prepared_work_id = prepared.get("id") if prepared else None
                intervention.confidence = prepared.get("confidence") if prepared else None
                intervention.evidence = prepared.get("evidence", []) if prepared else []
                intervention.actions = [
                    {"id": "manual", "label": "Review prepared work", "mode": "manual", "href": "/control-centre"},
                    {"id": "explain", "label": "Why now?", "mode": "explain"},
                ]
            db.commit()
            from app.companion import publish
            for intervention in interventions:
                publish(intervention.recipient_membership_id, {"type": "prepared_work.ready", "id": intervention.id})
            return "completed"
        except Exception as exc:
            db.rollback()
            attempt = db.query(models.AgentRunAttempt).filter_by(run_id=run_id, attempt_number=attempt_number).one()
            agent_run = db.get(models.AgentRun, run_id)
            attempt.state = "failed"
            attempt.error_code = type(exc).__name__
            attempt.error_detail = str(exc)[:2000]
            attempt.completed_at = datetime.now(timezone.utc)
            agent_run.state = "failed"
            agent_run.error_code = attempt.error_code
            interventions = db.query(models.CompanionIntervention).filter_by(run_id=run_id).all()
            for intervention in interventions:
                intervention.delivery_state = "delivered"
                intervention.delivery_mode = "bubble"
                intervention.severity = "warning"
                intervention.title = "AI preparation needs attention"
                intervention.message = "The background run did not complete. The manual workflow is still available."
            db.commit()
            from app.companion import publish
            for intervention in interventions:
                publish(intervention.recipient_membership_id, {"type": "run.failed", "id": intervention.id})
            raise

logger = logging.getLogger(__name__)


def _resume_agent_quotation_batch(db, job_id: str) -> None:
    """Keep an agent continuation failure from corrupting a completed parse."""
    try:
        from app.agent_service import resume_quotation_batch_after_document
        resume_quotation_batch_after_document(db, job_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Quotation extraction completed but agent continuation will be retried; job_id=%s",
            job_id,
        )


@worker_ready.connect
def verify_required_task_registry(**_kwargs) -> None:
    missing = REQUIRED_TASKS.difference(celery_app.tasks)
    if missing:
        raise RuntimeError(f"Worker is missing required tasks: {', '.join(sorted(missing))}")


@celery_app.task(
    bind=True,
    name="app.workers.process_document",
    autoretry_for=(TimeoutError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=max(get_settings().parser_timeout_seconds, get_settings().llamaparse_timeout_seconds + 15),
    time_limit=max(get_settings().parser_timeout_seconds, get_settings().llamaparse_timeout_seconds + 15) + 10,
)
def process_document(self, job_id: str) -> str:
    started = time.perf_counter()
    with SessionLocal() as db:
        try:
            queued_job = db.get(models.DocumentJob, job_id)
            if queued_job:
                queued_job.status = "processing"
                queued_job.started_at = datetime.now(timezone.utc)
                intake = db.query(models.QuotationIntake).filter_by(document_job_id=queued_job.id).first()
                if intake:
                    intake.status = "extracting"
                db.commit()
            job = process_document_job(db, job_id)
            attachment_status = {
                "processing": "extracting", "completed": "needs_review",
                "needs_review": "needs_review", "failed": "failed",
                "needs_manual_entry": "needs_review",
            }.get(job.status, job.status)
            db.query(models.AgentMessageAttachment).filter_by(
                document_job_id=job.id,
            ).update({
                models.AgentMessageAttachment.status: attachment_status,
                models.AgentMessageAttachment.error_code: job.error_code,
                models.AgentMessageAttachment.user_explanation: job.error_detail,
            }, synchronize_session=False)
            db.commit()
            # Agent uploads return immediately while parsing continues.  Once
            # the last file in that immutable batch finishes, resume the
            # canonical quotation tool without asking the employee to type
            # another message or upload the files again.
            _resume_agent_quotation_batch(db, job.id)
            JOB_LATENCY.labels("documents", "validate_extract").observe(time.perf_counter() - started)
            return job.status
        except SoftTimeLimitExceeded:
            db.rollback()
            job = db.get(models.DocumentJob, job_id)
            if job:
                job.status = "needs_manual_entry"
                job.error_code = "parser_timeout"
                job.error_detail = "Document parser exceeded its configured hard deadline"
                job.finished_at = datetime.now(timezone.utc)
                document = db.get(models.Document, job.document_id)
                if document:
                    document.status = "needs_manual_entry"
                db.query(models.AgentMessageAttachment).filter_by(
                    document_job_id=job.id,
                ).update({
                    models.AgentMessageAttachment.status: "needs_review",
                    models.AgentMessageAttachment.error_code: "parser_timeout",
                    models.AgentMessageAttachment.user_explanation: "Extraction timed out; retry or enter the fields manually.",
                }, synchronize_session=False)
                intake = db.query(models.QuotationIntake).filter_by(document_job_id=job.id).first()
                if intake:
                    intake.status = "needs_manual_entry"
                    intake.error_code = "parser_timeout"
                    intake.error_detail = job.error_detail
                db.commit()
                _resume_agent_quotation_batch(db, job.id)
            JOB_FAILURES.labels("documents", "validate_extract", "timeout").inc()
            JOB_LATENCY.labels("documents", "validate_extract").observe(time.perf_counter() - started)
            return "needs_manual_entry"
        except Exception as exc:
            db.rollback()
            job = db.get(models.DocumentJob, job_id)
            if job:
                job.status = "failed"
                job.error_code = type(exc).__name__
                job.error_detail = str(exc)[:1000]
                job.finished_at = datetime.now(timezone.utc)
                db.query(models.AgentMessageAttachment).filter_by(
                    document_job_id=job.id,
                ).update({
                    models.AgentMessageAttachment.status: "failed",
                    models.AgentMessageAttachment.error_code: type(exc).__name__,
                    models.AgentMessageAttachment.user_explanation: "Document processing failed. You can retry without uploading the file again.",
                }, synchronize_session=False)
                intake = db.query(models.QuotationIntake).filter_by(document_job_id=job.id).first()
                if intake:
                    intake.status = "failed"
                    intake.error_code = type(exc).__name__
                    intake.error_detail = str(exc)[:1000]
                db.commit()
                _resume_agent_quotation_batch(db, job.id)
            JOB_FAILURES.labels("documents", "validate_extract", type(exc).__name__).inc()
            JOB_LATENCY.labels("documents", "validate_extract").observe(time.perf_counter() - started)
            raise


@celery_app.task(name="app.workers.recover_queued_jobs")
def recover_queued_jobs() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    with SessionLocal() as db:
        jobs = db.query(models.DocumentJob).filter(
            models.DocumentJob.status.in_(["queued", "processing"]),
            models.DocumentJob.updated_at < cutoff,
        ).with_for_update(skip_locked=True).limit(100).all()
        for job in jobs:
            job.status = "queued"
            db.query(models.AgentMessageAttachment).filter_by(
                document_job_id=job.id,
            ).update({
                models.AgentMessageAttachment.status: "retrying",
            }, synchronize_session=False)
            result = process_document.apply_async(args=[job.id], queue="documents")
            job.celery_task_id = result.id
        db.commit()
        try:
            from app.agent_service import resume_ready_quotation_batches
            resume_ready_quotation_batches(db)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Ready quotation batch recovery will retry on the next schedule")
        return len(jobs)


@celery_app.task(bind=True, name="app.workers.dispatch_integration", max_retries=5)
def dispatch_integration(self, event_id: str) -> str:
    from app.integrations import dispatch_event_by_id

    try:
        return dispatch_event_by_id(event_id)
    except (TimeoutError, ConnectionError) as exc:
        base_delay = min(300, 2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=base_delay + random.uniform(0, max(1, base_delay * 0.25)))


@celery_app.task(bind=True, name="app.workers.send_email", max_retries=5)
def send_email(self, message_id: str) -> str:
    from app.integrations import send_email_by_id

    try:
        return send_email_by_id(message_id)
    except (TimeoutError, ConnectionError) as exc:
        base_delay = min(300, 2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=base_delay + random.uniform(0, max(1, base_delay * 0.25)))


@celery_app.task(name="app.workers.run_sync_job")
def run_sync_job(job_id: str) -> str:
    from app.integrations import run_sync_job_by_id

    return run_sync_job_by_id(job_id)


@celery_app.task(name="app.workers.import_master_data")
def import_master_data(job_id: str, document_id: str) -> str:
    from app.integrations import import_master_data_by_id

    return import_master_data_by_id(job_id, document_id)


@celery_app.task(name='app.workers.run_internal_followups')
def run_internal_followups() -> int:
    from app.task_service import run_internal_followups as sweep
    with SessionLocal() as db:
        count = sweep(db)
        db.commit()
        return count


@celery_app.task(name="app.workers.enforce_retention")
def enforce_retention() -> int:
    """Apply configured workspace retention only after deployment opt-in."""
    if not get_settings().retention_enforcement_enabled:
        return 0
    from app.retention_service import enforce
    processed = 0
    with SessionLocal() as db:
        tenant_ids = [row[0] for row in db.query(models.Tenant.id).filter_by(status="active").all()]
        for tenant_id in tenant_ids:
            admin = db.query(models.User).filter_by(tenant_id=tenant_id, role="admin", is_active=True).first()
            if admin is None:
                continue
            enforce(db, admin, "ENFORCE_RETENTION")
            processed += 1
        db.commit()
    return processed


@celery_app.task(name="app.workers.publish_outbox_event")
def publish_outbox_event(event_id: str) -> str:
    """Named V2 contract alias over the canonical V1 outbox dispatcher."""
    from app.eventing import dispatch_one
    with SessionLocal() as db:
        return dispatch_one(db, event_id)


@celery_app.task(name="app.workers.sync_connector")
def sync_connector(connection_id: str, job_type: str = "operational_reconciliation") -> str:
    from app.integrations import run_sync_job_by_id
    from app.db.tenant_lock import acquire_tenant_transaction_lock
    with SessionLocal() as db:
        connection = db.get(models.IntegrationConnection, connection_id)
        if connection is None:
            return "missing"
        acquire_tenant_transaction_lock(db, connection.tenant_id)
        db.expire_all()
        connection = db.get(models.IntegrationConnection, connection_id)
        if connection is None:
            return "missing"
        job = models.IntegrationSyncJob(
            tenant_id=connection.tenant_id, plant_id=connection.plant_id,
            connection_id=connection.id, job_type=job_type, status="queued", summary={})
        db.add(job)
        db.commit()
        job_id = job.id
    return run_sync_job_by_id(job_id)


@celery_app.task(name="app.workers.sync_factory_simulators")
def sync_factory_simulators() -> dict[str, int]:
    """Continuously drain every simulated source domain through normal connectors."""
    # Beat fires frequently to keep live manufacturing data fresh. If one
    # reconciliation cycle takes longer than its cadence, coalesce the next
    # cycle instead of letting identical drains contend for PostgreSQL.
    lease = None
    try:
        from redis import Redis
        from app.core.config import get_settings
        lease = Redis.from_url(get_settings().redis_url).lock(
            "genuinegigs:factory-simulator-sync", timeout=120, blocking_timeout=0)
        if not lease.acquire(blocking=False):
            return {"connections": 0, "completed_jobs": 0, "failed_jobs": 0, "coalesced": 1}
    except Exception:
        # Unit tests and maintenance commands may intentionally run without
        # Redis; tenant transaction locks still preserve database correctness.
        lease = None
    job_types = ("production_actual", "downtime", "inventory", "supplier_commitments",
                 "quality_events", "machine_events", "maintenance_work", "business_events")
    try:
        connection_ids: list[str]
        with SessionLocal() as db:
            connection_ids = [row.id for row in db.query(models.IntegrationConnection).filter_by(
                provider="factory_simulator", status="active").all()]
        completed = failed = 0
        for connection_id in connection_ids:
            for job_type in job_types:
                result = sync_connector(connection_id, job_type)
                if result in {"completed", "completed_with_errors"}: completed += 1
                else: failed += 1
        return {"connections": len(connection_ids), "completed_jobs": completed, "failed_jobs": failed, "coalesced": 0}
    finally:
        if lease is not None:
            try:
                lease.release()
            except Exception:
                pass


@celery_app.task(name="app.workers.apply_simulated_recovery_strategy")
def apply_simulated_recovery_strategy(strategy_type: str) -> str:
    base=os.getenv("FACTORY_SIMULATOR_URL","http://factory-simulator:8090").rstrip("/")
    token=os.getenv("FACTORY_SIMULATOR_TOKEN","northstar-local-simulator-token")
    body=json.dumps({"strategy_type":strategy_type}).encode()
    request=urllib.request.Request(base+"/sim/v1/recovery-strategies",data=body,method="POST",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=5) as response:
        return "accepted" if response.status==202 else f"status:{response.status}"


@celery_app.task(name="app.workers.reconcile_line_performance")
def reconcile_line_performance(line_id: str, shift_id: str) -> int:
    from app.operations import service as operational_v2
    with SessionLocal() as db:
        orders = db.query(models.ProductionWorkOrder).filter_by(
            line_id=line_id, shift_id=shift_id, status="in_progress").all()
        for order in orders:
            operational_v2.evaluate_production_behind_plan(db, order)
        db.commit()
        return len(orders)


def _recompute_material_readiness(work_order_id: str) -> int:
    from app.operations import service as operational_v2
    with SessionLocal() as db:
        requirements = db.query(models.ProductionMaterialRequirement).filter_by(
            work_order_id=work_order_id).all()
        for requirement in requirements:
            operational_v2.recompute_material_readiness(db, requirement)
        db.commit()
        return len(requirements)


@celery_app.task(name="app.workers.recompute_material_readiness")
def recompute_material_readiness(work_order_id: str) -> int:
    """Canonical V2 task identity from the implementation contract."""
    return _recompute_material_readiness(work_order_id)


@celery_app.task(name="app.workers.recompute_v2_material_readiness")
def recompute_v2_material_readiness(work_order_id: str) -> int:
    """Compatibility alias retained for already-enqueued rollout messages."""
    return _recompute_material_readiness(work_order_id)


@celery_app.task(name="app.workers.evaluate_open_deviations")
def evaluate_open_deviations(plant_id: str) -> int:
    from app.operations import service as operational_v2
    with SessionLocal() as db:
        orders = db.query(models.ProductionWorkOrder).filter_by(
            plant_id=plant_id, status="in_progress").all()
        for order in orders:
            operational_v2.evaluate_production_behind_plan(db, order)
        db.commit()
        return len(orders)


@celery_app.task(name="app.workers.reconcile_operational_snapshots")
def reconcile_operational_snapshots() -> dict[str, int]:
    """Fallback reconciliation and observed-outcome monitoring for V2.1."""
    from app.operations.state import build_operational_state_snapshot
    from app.operations.recovery import service as recovery
    snapshots = verified = monitoring = 0
    with SessionLocal() as db:
        lines = db.query(models.ProductionLine).all()
        for line in lines:
            try:
                build_operational_state_snapshot(db, "line", line.id)
                snapshots += 1
            except LookupError:
                continue
        cases = db.query(models.RecoveryCase).filter(
            models.RecoveryCase.status.in_(("executing", "monitoring", "recovered", "partially_recovered"))).all()
        for case in cases:
            links = (db.query(models.RecoveryStrategyAction).filter_by(strategy_id=case.selected_strategy_id).all()
                     if case.selected_strategy_id else [])
            actions = [db.get(models.OperationalAction, link.operational_action_id) for link in links]
            if case.status == "executing" and actions and all(row and row.status == "completed" for row in actions):
                recovery.begin_monitoring(db, case); monitoring += 1
            if case.status in {"monitoring", "recovered", "partially_recovered"}:
                _, outcome, _ = recovery.verify(db, case)
                verified += int(outcome is not None)
        db.commit()
    return {"snapshots":snapshots,"monitoring_started":monitoring,"verified":verified}


@celery_app.task(name="app.workers.log_forecast_evaluations")
def log_forecast_evaluations() -> dict[str, int]:
    from app.operations.service import production_forecast
    current=datetime.now(timezone.utc); logged=settled=0
    with SessionLocal() as db:
        active=db.query(models.ProductionWorkOrder).filter_by(status="in_progress").all()
        for order in active:
            forecast=production_forecast(db,order,current)
            planned_end=order.planned_end_at.replace(tzinfo=timezone.utc) if order.planned_end_at.tzinfo is None else order.planned_end_at
            db.add(models.ForecastEvaluation(tenant_id=order.tenant_id,plant_id=order.plant_id,
                work_order_id=order.id,forecast_at=current,
                horizon_seconds=max(int((planned_end-current).total_seconds()),0),
                forecast_quantity=forecast["forecast_quantity"],context={"model":"bounded_monotonic_rate","confidence":forecast["confidence"]}))
            logged+=1
        pending=db.query(models.ForecastEvaluation).filter(models.ForecastEvaluation.actual_eventual_quantity.is_(None)).all()
        for row in pending:
            order=db.get(models.ProductionWorkOrder,row.work_order_id)
            end=order.planned_end_at.replace(tzinfo=timezone.utc) if order.planned_end_at.tzinfo is None else order.planned_end_at
            if end>current: continue
            actual=db.query(models.ProductionActualPoint).filter_by(work_order_id=order.id).order_by(models.ProductionActualPoint.recorded_at.desc()).first()
            row.actual_eventual_quantity=float(actual.good_quantity if actual else 0)
            row.absolute_error=abs(row.forecast_quantity-row.actual_eventual_quantity)
            row.percentage_error=row.absolute_error/max(row.actual_eventual_quantity,1)
            settled+=1
        db.commit()
    return {"logged":logged,"settled":settled}


@celery_app.task(name="app.workers.evaluate_action_slas")
def evaluate_action_slas(plant_id: str) -> int:
    now = datetime.now(timezone.utc)
    escalated = 0
    with SessionLocal() as db:
        actions = db.query(models.OperationalAction).filter(
            models.OperationalAction.plant_id == plant_id,
            models.OperationalAction.status.notin_(["completed", "cancelled"]),
            models.OperationalAction.due_at.is_not(None),
            models.OperationalAction.due_at < now).all()
        for action in actions:
            action.priority = "urgent"
            owner = db.get(models.User, action.owner_user_id) if action.owner_user_id else db.query(models.User).filter_by(
                tenant_id=action.tenant_id, plant_id=plant_id, role="plant_manager", is_active=True).first()
            if owner:
                existing = db.query(models.Notification).filter_by(
                    tenant_id=action.tenant_id, dedupe_key=f"v2:action-sla:{action.id}", status="unread").first()
                if not existing:
                    db.add(models.Notification(
                        tenant_id=action.tenant_id, plant_id=plant_id, user_id=owner.id,
                        category="escalation", severity="critical", title="Recovery action overdue",
                        body=action.title, linked_entity_type="operational_action",
                        linked_entity_id=action.id, task_id=action.task_id,
                        navigation_target=f"/v2/deviations/{action.deviation_id}",
                        dedupe_key=f"v2:action-sla:{action.id}"))
            escalated += 1
        db.commit()
    return escalated


@celery_app.task(name="app.workers.evaluate_all_v2_action_slas")
def evaluate_all_v2_action_slas() -> int:
    with SessionLocal() as db:
        plant_ids = [row[0] for row in db.query(models.Plant.id).all()]
    return sum(evaluate_action_slas.run(plant_id) for plant_id in plant_ids)


@celery_app.task(name="app.workers.reconcile_all_v2_lines")
def reconcile_all_v2_lines() -> int:
    with SessionLocal() as db:
        pairs = db.query(models.ProductionWorkOrder.line_id, models.ProductionWorkOrder.shift_id).filter_by(
            status="in_progress").distinct().all()
    return sum(reconcile_line_performance.run(line_id, shift_id) for line_id, shift_id in pairs)


@celery_app.task(name="app.workers.recompute_all_v2_material_readiness")
def recompute_all_v2_material_readiness() -> int:
    with SessionLocal() as db:
        work_order_ids = [row[0] for row in db.query(models.ProductionMaterialRequirement.work_order_id).distinct().all()]
    return sum(recompute_v2_material_readiness.run(work_order_id) for work_order_id in work_order_ids)


def _upsert_shift_briefing(db, plant_id: str, shift_id: str, briefing_type: str) -> models.ShiftBriefing:
    from app.operations import service as operational_v2
    shift = db.query(models.PlantShift).filter_by(id=shift_id, plant_id=plant_id).one()
    return operational_v2.generate_shift_record(
        db, shift.tenant_id, plant_id, shift_id, briefing_type, shift.ends_at)


@celery_app.task(name="app.workers.generate_shift_briefing")
def generate_shift_briefing(plant_id: str, shift_id: str) -> str:
    with SessionLocal() as db:
        row = _upsert_shift_briefing(db, plant_id, shift_id, "start")
        db.commit()
        return row.id


@celery_app.task(name="app.workers.generate_shift_handover")
def generate_shift_handover(plant_id: str, shift_id: str) -> str:
    with SessionLocal() as db:
        row = _upsert_shift_briefing(db, plant_id, shift_id, "handover")
        db.commit()
        return row.id


@celery_app.task(name="app.workers.calculate_value_entries")
def calculate_value_entries(deviation_id: str) -> int:
    from app.operations import service as operational_v2
    with SessionLocal() as db:
        deviation = db.get(models.OperationalDeviation, deviation_id)
        if deviation is None:
            return 0
        count = operational_v2.recalculate_value_entries(db, deviation)
        db.commit()
        return count


@celery_app.task(name="app.workers.index_knowledge_document")
def index_knowledge_document(document_id: str) -> int:
    """Idempotently rebuild the canonical searchable chunks for one document."""
    with SessionLocal() as db:
        document = db.get(models.KnowledgeDocument, document_id)
        if document is None:
            return 0
        chunks = [document.content[index:index + 1200]
                  for index in range(0, len(document.content), 1200)]
        db.query(models.KnowledgeChunk).filter_by(
            knowledge_document_id=document.id).delete(synchronize_session=False)
        for index, content in enumerate(chunks):
            db.add(models.KnowledgeChunk(
                tenant_id=document.tenant_id, plant_id=document.plant_id,
                knowledge_document_id=document.id, chunk_index=index,
                content=content, embedding=[],
                token_count=max(1, len(content.split())),
            ))
        db.commit()
        return len(chunks)


def _run_v2_agent(agent_type: str, trigger: dict) -> str:
    """Run the deterministic context/tool/evidence pipeline; never physical control."""
    from app.operations.agents import run
    with SessionLocal() as db:
        row = run(db, agent_type, trigger)
        db.commit()
        return row.id


@celery_app.task(name="app.workers.run_agent")
def run_agent(agent_type: str, trigger: dict) -> str:
    """Canonical V2 task identity from the objective-agent contract."""
    return _run_v2_agent(agent_type, trigger)


@celery_app.task(name="app.workers.run_v2_agent")
def run_v2_agent(agent_type: str, trigger: dict) -> str:
    """Compatibility alias retained for already-enqueued rollout messages."""
    return _run_v2_agent(agent_type, trigger)
