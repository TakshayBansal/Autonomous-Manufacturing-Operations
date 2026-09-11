from __future__ import annotations

import hashlib
import csv
import io
import smtplib
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.erp import get_erp_adapter
from app.core.metrics import OUTBOX_ATTEMPTS, EMAIL_DELIVERIES, CONNECTOR_SYNCS
from app.storage import object_storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(payload: Any) -> str:
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def dispatch_event_by_id(event_id: str) -> str:
    with SessionLocal() as db:
        event = db.query(models.IntegrationOutboxEvent).filter_by(id=event_id).with_for_update().first()
        if event is None:
            raise KeyError(event_id)
        if event.status in {"simulated", "dispatched"}:
            return event.status
        if event.status not in {"approved", "dispatching", "failed"}:
            raise RuntimeError("Integration event is not approved")
        event.status = "dispatching"
        event.retry_count += 1
        attempt = models.IntegrationAttempt(
            id=f"IAT-{event.id}-{event.retry_count}", tenant_id=event.tenant_id, plant_id=event.plant_id,
            event_id=event.id, attempt_number=event.retry_count, status="dispatching", request_hash=_hash(event.request_payload),
        )
        db.add(attempt)
        db.commit()
        try:
            adapter = get_erp_adapter(event.provider)
            is_simulated = get_settings().erp_write_mode != "live" or event.provider == "local"
            if event.entity_type == "po_draft" and event.action == "push_purchase_order":
                entity = db.get(models.PODraft, event.entity_id)
                if entity is None:
                    raise RuntimeError("PO draft no longer exists")
                result = adapter.push_purchase_order(db, entity)
            elif event.entity_type == "po_draft" and event.action in {"amend_purchase_order", "cancel_purchase_order"}:
                entity = db.get(models.PODraft, event.entity_id)
                if entity is None:
                    raise RuntimeError("PO change no longer exists")
                if not is_simulated:
                    raise RuntimeError(f"Connector {event.provider} has not declared verified support for {event.action}")
                result = {
                    "external_id": f"SIM-{event.action.upper()}-{entity.root_po_id or entity.id}-V{entity.revision_number}",
                    "operation": event.action, "verified": True,
                }
            elif event.entity_type == "store_receipt" and event.action == "push_receipt":
                entity = db.get(models.StoreReceipt, event.entity_id)
                if entity is None:
                    raise RuntimeError("Receipt no longer exists")
                result = adapter.push_receipt(db, entity)
            else:
                raise RuntimeError(f"Unsupported integration action {event.action}")
            event.status = "simulated" if is_simulated else "dispatched"
            event.response_payload = dict(result)
            event.dispatched_at = _utcnow()
            event.last_error = None
            attempt.status = event.status
            attempt.response_payload = dict(result)
            if event.entity_type == "po_draft":
                po = db.get(models.PODraft, event.entity_id)
                external_id = str(result.get("external_id") or result.get("correlation_id") or event.correlation_id)
                po.status = "simulated_posted" if is_simulated else "posted"
                po.simulated_posting_correlation_id = external_id
                po.issued_at = _utcnow()
                if po.previous_version_id and po.revision_kind in {"amendment", "cancellation"}:
                    previous = db.get(models.PODraft, po.previous_version_id)
                    if previous:
                        previous.status = "cancelled" if po.revision_kind == "cancellation" else "superseded"
                        previous.superseded_at = _utcnow()
                    if po.revision_kind == "cancellation":
                        po.status = "cancelled"
                existing_ref = db.query(models.IntegrationExternalReference).filter_by(provider=event.provider, local_entity_type="po_draft", local_entity_id=po.id).first()
                if existing_ref is None:
                    db.add(models.IntegrationExternalReference(id=f"IER-{event.id}", tenant_id=event.tenant_id, plant_id=event.plant_id, provider=event.provider, local_entity_type="po_draft", local_entity_id=po.id, external_entity_type="purchase_order", external_id=external_id, sync_status=event.status, last_payload_hash=_hash(event.request_payload)))
                if po.revision_kind != "cancellation":
                    gate_membership = db.query(models.WorkspaceMembership).filter_by(
                        tenant_id=event.tenant_id, default_plant_id=event.plant_id,
                        role="gate_operator", status="active",
                    ).first()
                    existing_gate_task = db.query(models.Task).filter_by(
                        tenant_id=event.tenant_id, plant_id=event.plant_id,
                        entity_type="po_draft", entity_id=po.id,
                        owner_role="gate_operator", status="open",
                    ).first()
                    if gate_membership and existing_gate_task is None:
                        db.add(models.Task(
                            id=f"TASK-{secrets.token_hex(8)}", tenant_id=event.tenant_id,
                            plant_id=event.plant_id,
                            title=f"Record gate arrival for {po.business_number or po.id}",
                            owner_role="gate_operator", owner_user_id=gate_membership.user_id,
                            owner_membership_id=gate_membership.id,
                            due_at=_utcnow() + timedelta(days=14), status="open",
                            severity="action", entity_type="po_draft", entity_id=po.id,
                            assignment_source="workflow",
                        ))
                        db.add(models.Notification(
                            id=f"NOT-{secrets.token_hex(8)}", tenant_id=event.tenant_id,
                            plant_id=event.plant_id, user_id=gate_membership.user_id,
                            title="Purchase order ready for gate entry",
                            body=f"{po.business_number or po.id} is issued. Record the vehicle and supplier challan when it arrives.",
                        ))
                existing_token = db.query(models.SupplierPortalToken).filter_by(tenant_id=event.tenant_id, plant_id=event.plant_id, purpose="po_acknowledgement", entity_id=po.id, status="active").first()
                if existing_token is None:
                    raw_token = secrets.token_urlsafe(32)
                    token = models.SupplierPortalToken(id=f"SPT-{secrets.token_hex(8)}", tenant_id=event.tenant_id, plant_id=event.plant_id, rfq_id="", supplier_id=po.supplier_id, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), status="active", expires_at=_utcnow() + timedelta(days=14), purpose="po_acknowledgement", entity_id=po.id)
                    db.add(token)
                    contact = db.query(models.SupplierContact).filter_by(tenant_id=event.tenant_id, plant_id=event.plant_id, supplier_id=po.supplier_id).first()
                    if contact:
                        portal_url = f"{get_settings().web_base_url.rstrip('/')}/supplier/portal?token={raw_token}"
                        po_artifact = db.query(models.GeneratedArtifact).filter(
                            models.GeneratedArtifact.tenant_id == event.tenant_id,
                            models.GeneratedArtifact.plant_id == event.plant_id,
                            models.GeneratedArtifact.entity_id == po.id,
                            models.GeneratedArtifact.status == "final",
                            models.GeneratedArtifact.artifact_type.in_(["po", "po_pdf"]),
                        ).order_by(models.GeneratedArtifact.artifact_version.desc()).first()
                        change_label = "cancellation" if po.revision_kind == "cancellation" else "amendment" if po.revision_kind == "amendment" else "purchase order"
                        db.add(models.OutboxMessage(id=f"OUT-{secrets.token_hex(8)}", tenant_id=event.tenant_id, plant_id=event.plant_id, channel="email", recipient=contact.email, subject=f"Purchase order {change_label} {po.business_number or po.id} acknowledgement", body=f"Please review and respond to the {change_label} for {po.business_number or po.id}: {portal_url}", status="approved_pending_send", payload_hash=_hash(po.oracle_mapping), correlation_id=f"MSG-{secrets.token_hex(5).upper()}", idempotency_key=f"po:{po.id}:acknowledgement", approved_by_user_id=event.approved_by_user_id, approved_at=event.approved_at, attachment_document_ids=[po_artifact.document_id] if po_artifact else [], meta={"po_draft_id": po.id, "portal_token_preview": raw_token[:8], "portal_url": portal_url, "revision_kind": po.revision_kind, "revision_number": po.revision_number}))
            db.commit()
            OUTBOX_ATTEMPTS.labels(event.provider, event.status).inc()
            return event.status
        except httpx.HTTPStatusError as exc:
            attempt.response_status = exc.response.status_code
            attempt.error = f"HTTP {exc.response.status_code}"
            event.last_error = attempt.error
            event.status = "failed"
            if exc.response.status_code == 429 or exc.response.status_code >= 500:
                event.next_attempt_at = _utcnow() + timedelta(seconds=min(300, 2 ** event.retry_count))
            db.commit()
            OUTBOX_ATTEMPTS.labels(event.provider, "failed").inc()
            if exc.response.status_code == 429 or exc.response.status_code >= 500:
                raise ConnectionError(attempt.error) from exc
            return event.status
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            attempt.error = type(exc).__name__
            event.last_error = attempt.error
            event.status = "failed"
            event.next_attempt_at = _utcnow() + timedelta(seconds=min(300, 2 ** event.retry_count))
            db.commit()
            OUTBOX_ATTEMPTS.labels(event.provider, "failed").inc()
            raise ConnectionError(attempt.error) from exc
        except Exception as exc:
            attempt.error = str(exc)[:1000]
            event.last_error = attempt.error
            event.status = "failed"
            db.commit()
            raise


def send_email_by_id(message_id: str) -> str:
    settings = get_settings()
    with SessionLocal() as db:
        message = db.query(models.OutboxMessage).filter_by(id=message_id).with_for_update().first()
        if message is None:
            raise KeyError(message_id)
        if message.status in {"sent", "simulated"}:
            return message.status
        if message.status not in {"approved_pending_send", "failed", "sending"}:
            raise RuntimeError("Email is not approved")
        message.status = "sending"
        message.retry_count += 1
        db.commit()
        if settings.smtp_mode != "smtp":
            message.status = "simulated"
            message.sent_at = _utcnow()
            db.commit()
            EMAIL_DELIVERIES.labels(settings.smtp_mode, "simulated").inc()
            return message.status
        email = EmailMessage()
        email["From"] = settings.smtp_from
        email["To"] = message.recipient
        email["Subject"] = message.subject
        email.set_content(message.body)
        for document_id in message.attachment_document_ids or []:
            document = db.query(models.Document).filter_by(
                id=document_id, tenant_id=message.tenant_id, plant_id=message.plant_id
            ).first()
            if document is None:
                raise RuntimeError("Authorized email attachment is unavailable")
            content_type = document.content_type if "/" in document.content_type else "application/octet-stream"
            maintype, subtype = content_type.split("/", 1)
            email.add_attachment(
                object_storage.get_bytes(document.storage_bucket, document.storage_key),
                maintype=maintype, subtype=subtype, filename=document.filename,
            )
        try:
            with smtplib.SMTP(settings.smtp_host or "localhost", settings.smtp_port, timeout=20) as client:
                if settings.smtp_user:
                    client.starttls()
                    client.login(settings.smtp_user, settings.smtp_password or "")
                client.send_message(email)
            message.status = "sent"
            message.sent_at = _utcnow()
            db.commit()
            EMAIL_DELIVERIES.labels(settings.smtp_mode, "sent").inc()
            return message.status
        except (OSError, smtplib.SMTPException) as exc:
            message.status = "failed"
            message.meta = {**message.meta, "last_error": type(exc).__name__}
            db.commit()
            EMAIL_DELIVERIES.labels(settings.smtp_mode, "failed").inc()
            raise ConnectionError(type(exc).__name__) from exc


def run_sync_job_by_id(job_id: str) -> str:
    with SessionLocal() as db:
        job = db.get(models.IntegrationSyncJob, job_id)
        if job is None:
            return "missing"
        from app.db.tenant_lock import acquire_tenant_transaction_lock
        tenant_id = job.tenant_id
        acquire_tenant_transaction_lock(db, tenant_id)
        db.expire_all()
        job = db.get(models.IntegrationSyncJob, job_id)
        if job is None:
            return "missing"
        connection = db.get(models.IntegrationConnection, job.connection_id)
        job.status = "running"
        job.started_at = _utcnow()
        from app.connector_sdk import (
            CONNECTOR_REGISTRY, ConnectorContext, ConnectorMode, SYNC_JOB_CAPABILITIES, get_connector,
        )
        if connection and connection.provider in CONNECTOR_REGISTRY:
            try:
                connector = get_connector(connection.provider)
                context = ConnectorContext(
                    connection_id=connection.id, tenant_id=job.tenant_id, plant_id=job.plant_id,
                    mode=ConnectorMode(connection.mode),
                    enabled_capabilities=frozenset(connection.enabled_capabilities or []),
                    writes_enabled=connection.writes_enabled, secret_ref=connection.secret_ref,
                )
                previous_jobs = (db.query(models.IntegrationSyncJob)
                    .filter(models.IntegrationSyncJob.connection_id == connection.id,
                            models.IntegrationSyncJob.id != job.id,
                            models.IntegrationSyncJob.status.in_(("completed", "completed_with_errors")))
                    .order_by(models.IntegrationSyncJob.finished_at.desc()).limit(40).all())
                prior_cursors = {}
                for previous in previous_jobs:
                    for capability, cursor in dict((previous.summary or {}).get("cursors") or {}).items():
                        if capability not in prior_cursors and cursor is not None:
                            prior_cursors[capability] = cursor
                results = {
                    capability: connector.pull(context, capability, prior_cursors.get(capability))
                    for capability in SYNC_JOB_CAPABILITIES[job.job_type]
                }
                from app.operations.normalization import normalize_results
                reconciliation = normalize_results(db, job, connection, results)
                from app.operations import service as operational_v2
                for record in reconciliation.pop("applied_records"):
                    if isinstance(record, models.ProductionActualPoint):
                        order = db.get(models.ProductionWorkOrder, record.work_order_id)
                        operational_v2.evaluate_production_behind_plan(db, order, record.recorded_at)
                        for recovery in db.query(models.OperationalDeviation).filter_by(
                                tenant_id=job.tenant_id, plant_id=job.plant_id,
                                line_id=order.line_id, status="monitoring").all():
                            managed_case = db.query(models.RecoveryCase).filter_by(deviation_id=recovery.id).first()
                            if managed_case:
                                continue  # V2.1 verification requires before/after operational evidence.
                            recovery.status, recovery.verified_at = "verified", record.recorded_at
                            recovery.verified_outcome = {"good_units_after_recovery":record.good_quantity,
                                "source":"mes","production_resumed":record.good_quantity > 0}
                            db.add(models.EventOutbox(tenant_id=job.tenant_id, plant_id=job.plant_id,
                                event_type="deviation.resolved", aggregate_type="operational_deviation",
                                aggregate_id=recovery.id, aggregate_version=recovery.version+1,
                                correlation_id=f"verified-recovery:{recovery.id}:{record.id}"[:80],
                                payload={"deviation_id":recovery.id,"status":"verified","actual_point_id":record.id}))
                    elif isinstance(record, models.MachineSignalSample):
                        operational_v2.evaluate_machine_signals(db, record)
                    elif isinstance(record, models.AssetFaultEvent) and record.cleared_at is not None:
                        operational_v2.reconcile_asset_recovery(db, record)
                    elif isinstance(record, models.ProductionDowntimeEvent):
                        operational_v2.evaluate_downtime_threshold(db, record)
                    elif isinstance(record, models.ProductionQualityEvent):
                        operational_v2.evaluate_rejection_rate(db, record)
                        operational_v2.evaluate_spc_control_limit(db, record)
                    elif isinstance(record, (models.MaterialInventoryPosition, models.ProductionSupplierCommitment)):
                        query = db.query(models.ProductionMaterialRequirement).filter_by(
                            tenant_id=job.tenant_id, plant_id=job.plant_id,
                            material_code=record.material_code)
                        if isinstance(record, models.ProductionSupplierCommitment):
                            query = query.filter_by(work_order_id=record.work_order_id)
                        for requirement in query.all():
                            operational_v2.recompute_material_readiness(db, requirement)
                    elif isinstance(record, models.MaintenanceWorkRecord):
                        deviation = (db.query(models.OperationalDeviation).filter_by(
                            tenant_id=job.tenant_id, plant_id=job.plant_id, asset_id=record.asset_id)
                            .filter(models.OperationalDeviation.status.in_(operational_v2.ACTIVE_DEVIATION_STATUSES))
                            .order_by(models.OperationalDeviation.detected_at.desc()).first())
                        if deviation:
                            action = db.query(models.OperationalAction).filter_by(deviation_id=deviation.id).first()
                            if record.status == "waiting_for_spare" and action:
                                action.status = "waiting"
                                if not db.query(models.OperationalActionDependency).filter_by(
                                        action_id=action.id, title=f"Secure spare {record.spare_code}").first():
                                    db.add(models.OperationalActionDependency(
                                        tenant_id=job.tenant_id, plant_id=job.plant_id, action_id=action.id,
                                        dependency_type="material", title=f"Secure spare {record.spare_code}",
                                        owner_role="store_manager", status="open",
                                        due_at=_utcnow()+timedelta(minutes=30),
                                        evidence_required=[{"type":"inventory_confirmation","spare_code":record.spare_code}]))
                            elif record.status == "completed" and action:
                                now = record.completed_at or _utcnow()
                                action.status, action.completed_at = "completed", now
                                action.completion_outcome = {"resolution":record.resolution,"source":"cmms","verified_machine_state":True}
                                if action.task_id:
                                    task = db.get(models.Task, action.task_id)
                                    if task: task.status, task.completed_at = "completed", now
                                for dependency in db.query(models.OperationalActionDependency).filter_by(action_id=action.id).all():
                                    dependency.status, dependency.resolved_at = "resolved", now
                                deviation.status, deviation.resolved_at = "monitoring", now
                                deviation.resolution = record.resolution
                                db.add(models.EventOutbox(tenant_id=job.tenant_id, plant_id=job.plant_id,
                                    event_type="deviation.updated", aggregate_type="operational_deviation",
                                    aggregate_id=deviation.id, aggregate_version=deviation.version+1,
                                    correlation_id=f"cmms-recovery:{record.id}"[:80],
                                    payload={"deviation_id":deviation.id,"status":"monitoring","maintenance_work_id":record.id}))
                    # Event-triggered shared-state refresh. The periodic worker is only a fallback.
                    line_id = None
                    if isinstance(record, (models.ProductionActualPoint, models.ProductionDowntimeEvent,
                                           models.ProductionQualityEvent)):
                        linked_order = db.get(models.ProductionWorkOrder, record.work_order_id)
                        line_id = linked_order.line_id if linked_order else getattr(record, "line_id", None)
                    elif isinstance(record, (models.MachineSignalSample, models.AssetFaultEvent, models.MaintenanceWorkRecord)):
                        linked_asset = db.get(models.PlantAsset, record.asset_id)
                        line_id = linked_asset.line_id if linked_asset else None
                    elif isinstance(record, models.ProductionSupplierCommitment):
                        linked_order = db.get(models.ProductionWorkOrder, record.work_order_id)
                        line_id = linked_order.line_id if linked_order else None
                    if line_id:
                        from app.operations.state import build_operational_state_snapshot
                        build_operational_state_snapshot(db, "line", line_id, getattr(record, "recorded_at", None) or
                                                         getattr(record, "occurred_at", None) or _utcnow())
                job.status = "completed_with_errors" if reconciliation["counts"]["errors"] else "completed"
                job.summary = {
                    "provider": connection.provider, "mode": connection.mode,
                    "counts": reconciliation["counts"], "targets": reconciliation["targets"],
                    "errors": reconciliation["errors"], "mapping_version": reconciliation["mapping_version"],
                    "source_counts": {capability: len(result.get("records") or []) for capability, result in results.items()},
                    "cursors": {capability: result.get("cursor") for capability, result in results.items()},
                    "has_more": any(bool(result.get("has_more")) for result in results.values()),
                }
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)[:1000]
            job.finished_at = _utcnow()
            db.commit()
            CONNECTOR_SYNCS.labels(connection.provider, job.status).inc()
            return job.status
        adapter = get_erp_adapter(connection.provider if connection else None)
        operations = {
            "master_data": adapter.pull_master_data,
            "material_needs": adapter.pull_material_needs,
            "open_purchase_orders": adapter.pull_open_purchase_orders,
            "receipts": adapter.pull_receipts,
            "inspections": adapter.pull_inspections,
        }
        try:
            result = operations[job.job_type](db, job.tenant_id, job.plant_id or "")
            job.status = "completed"
            job.summary = {"provider": result.get("provider"), "mode": result.get("mode"), "counts": {key: len(value) for key, value in result.items() if isinstance(value, list)}}
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:1000]
        job.finished_at = _utcnow()
        db.commit()
        CONNECTOR_SYNCS.labels(connection.provider if connection else "unconfigured", job.status).inc()
        return job.status


def process_inbound_supplier_email(db, user: models.User, payload) -> tuple[models.SupplierChannelMessage, list[dict[str, Any]]]:
    """Associate verified supplier email evidence with one canonical business context."""
    from app.domains import workflows

    existing = db.query(models.SupplierChannelMessage).filter_by(
        tenant_id=user.tenant_id, channel="email", external_message_id=payload.external_message_id,
    ).first()
    if existing:
        key = {
            "invoice": "invoice_extraction_id", "po_acknowledgement": "acknowledgement_id",
            "delivery_notice": "asn_id",
        }.get(payload.message_type, "quote_id")
        results = [{key: record_id} for record_id in existing.canonical_record_ids]
        return existing, results
    rfq = None
    po = None
    if payload.message_type == "quotation":
        if not payload.rfq_reference:
            raise ValueError("Supplier request reference is required for a quotation email")
        rfq = workflows.user_scope_query(db, models.RFQ, user).filter(
            (models.RFQ.id == payload.rfq_reference) | (models.RFQ.business_number == payload.rfq_reference)
        ).first()
        if rfq is None:
            raise ValueError("Supplier request reference was not found in this workspace")
        eligible_supplier_ids = set(rfq.supplier_ids or [])
    else:
        if not payload.po_reference:
            raise ValueError("Purchase order reference is required for this supplier email")
        po = workflows.user_scope_query(db, models.PODraft, user).filter(
            (models.PODraft.id == payload.po_reference) | (models.PODraft.business_number == payload.po_reference)
        ).first()
        if po is None:
            raise ValueError("Purchase order reference was not found in this workspace")
        eligible_supplier_ids = {po.supplier_id}
    contacts = workflows.user_scope_query(db, models.SupplierContact, user).filter(
        models.SupplierContact.email.ilike(payload.sender_email.strip())
    ).all()
    eligible = [contact for contact in contacts if contact.supplier_id in eligible_supplier_ids]
    if len(eligible) != 1:
        raise ValueError("Sender must match the supplier contact for this business record")
    contact = eligible[0]
    documents = workflows.user_scope_query(db, models.Document, user).filter(
        models.Document.id.in_(list(dict.fromkeys(payload.document_ids)))
    ).all()
    if len(documents) != len(set(payload.document_ids)):
        raise ValueError("One or more email attachments are outside this workspace")
    blocked = [document.filename for document in documents if document.status in {"quarantined", "rejected", "invalid"}]
    if blocked:
        raise ValueError("Email attachments must pass document validation before processing")
    if payload.message_type in {"quotation", "invoice"} and not documents:
        raise ValueError("A validated attachment is required for quotation or invoice email")
    message = models.SupplierChannelMessage(
        tenant_id=user.tenant_id, plant_id=user.plant_id, channel="email", direction="inbound",
        external_message_id=payload.external_message_id, sender=payload.sender_email.strip().casefold(),
        subject=payload.subject, body_preview=payload.body_preview, status="processing",
        rfq_id=rfq.id if rfq else None, supplier_id=contact.supplier_id, document_ids=list(dict.fromkeys(payload.document_ids)),
        canonical_record_ids=[],
    )
    db.add(message)
    db.flush()
    if payload.message_type == "quotation":
        results = workflows.attach_uploaded_quote_documents(
            db, user, rfq_id=rfq.id, supplier_id=contact.supplier_id, document_ids=message.document_ids,
        )
        message.canonical_record_ids = [str(result["quote_id"]) for result in results]
    elif payload.message_type == "invoice":
        from app import invoice_service
        results = []
        for document in documents:
            extraction = invoice_service.prepare_channel_invoice_extraction(db, user, document, po)
            results.append({"invoice_extraction_id": extraction.id, "document_id": document.id})
        message.canonical_record_ids = [str(result["invoice_extraction_id"]) for result in results]
    elif payload.message_type == "po_acknowledgement":
        if payload.acknowledgement_status is None or payload.confirmed_quantity is None or not payload.confirmed_delivery:
            raise ValueError("Acknowledgement status, confirmed quantity, and confirmed delivery are required")
        acknowledgement = workflows.receive_supplier_acknowledgement(
            db, None, payload.acknowledgement_status, payload.confirmed_quantity,
            payload.confirmed_delivery, payload.body_preview,
            po_context=po, supplier_id=contact.supplier_id, source="Supplier Email",
        )
        results = [{"acknowledgement_id": acknowledgement.id}]
        message.canonical_record_ids = [acknowledgement.id]
    else:
        if payload.expected_quantity is None or not payload.expected_delivery or not payload.dispatch_reference:
            raise ValueError("Expected quantity, delivery date, and dispatch reference are required")
        asn = workflows.receive_supplier_delivery_notice(
            db, None, payload.expected_quantity, payload.expected_delivery,
            payload.dispatch_reference, payload.vehicle_number,
            po_context=po, supplier_id=contact.supplier_id, source="supplier_email",
        )
        for document in documents:
            workflows.link_supplier_delivery_document(
                db, asn, document, payload.attachment_purpose, "Supplier Email",
            )
        results = [{"asn_id": asn.id}]
        message.canonical_record_ids = [asn.id]
    message.status = "processed"
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "supplier_email.processed",
        "supplier_channel_message", message.id, actor_user_id=user.id,
        meta={"message_type": payload.message_type, "rfq_id": rfq.id if rfq else None, "po_id": po.id if po else None, "supplier_id": contact.supplier_id, "document_count": len(documents)},
    )
    return message, results


def import_master_data_by_id(job_id: str, document_id: str) -> str:
    with SessionLocal() as db:
        job = db.get(models.IntegrationSyncJob, job_id)
        document = db.get(models.Document, document_id)
        if job is None or document is None:
            raise KeyError(job_id)
        job.status = "running"
        job.started_at = _utcnow()
        processed = 0
        errors: list[dict[str, Any]] = []
        content = object_storage.get_bytes(document.storage_bucket, document.storage_key).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        for row_number, row in enumerate(reader, start=2):
            try:
                if any(str(value).startswith(("=", "+", "-", "@")) for value in row.values() if value is not None):
                    raise ValueError("formula-like value rejected")
                record_type = (row.get("record_type") or "").strip().lower()
                if record_type == "supplier":
                    vendor_id = (row.get("erp_vendor_id") or "").strip()
                    if not vendor_id:
                        raise ValueError("erp_vendor_id is required")
                    supplier = db.query(models.Supplier).filter_by(tenant_id=job.tenant_id, plant_id=job.plant_id, erp_vendor_id=vendor_id).first()
                    if supplier is None:
                        supplier = models.Supplier(id=f"SUP-{hashlib.sha256(vendor_id.encode()).hexdigest()[:16]}", tenant_id=job.tenant_id, plant_id=job.plant_id, name=row.get("name") or vendor_id, status=row.get("status") or "conditional", quality_score=int(row.get("quality_score") or 0), delivery_score=int(row.get("delivery_score") or 0), erp_vendor_id=vendor_id)
                        db.add(supplier)
                    else:
                        supplier.name = row.get("name") or supplier.name
                        supplier.status = row.get("status") or supplier.status
                elif record_type == "item":
                    erp_code = (row.get("erp_item_code") or "").strip()
                    if not erp_code:
                        raise ValueError("erp_item_code is required")
                    item = db.query(models.Item).filter_by(tenant_id=job.tenant_id, plant_id=job.plant_id, erp_item_code=erp_code).first()
                    if item is None:
                        item = models.Item(id=f"ITEM-{hashlib.sha256(erp_code.encode()).hexdigest()[:16]}", tenant_id=job.tenant_id, plant_id=job.plant_id, code=row.get("code") or erp_code, name=row.get("name") or erp_code, uom_id=row.get("uom") or "EA", erp_item_code=erp_code)
                        db.add(item)
                    else:
                        item.name = row.get("name") or item.name
                else:
                    raise ValueError("record_type must be supplier or item")
                processed += 1
            except Exception as exc:
                errors.append({"row": row_number, "error": str(exc)})
        job.status = "completed_with_errors" if errors else "completed"
        job.summary = {"processed": processed, "errors": errors, "document_id": document.id}
        job.finished_at = _utcnow()
        db.commit()
        return job.status
