from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN, require_role
from app.db import models
from app.domains import workflows
from app import procurement_policy


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_invoice_review_work(db: Session, extraction: models.InvoiceExtractionRun, document: models.Document) -> None:
    semantic_key = f"invoice_extraction:{extraction.id}:review"
    if db.query(models.Task).filter_by(tenant_id=extraction.tenant_id, semantic_key=semantic_key).filter(
        models.Task.status.in_(["open", "in_progress", "blocked"]),
    ).first():
        return
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=extraction.tenant_id, default_plant_id=extraction.plant_id,
        role="purchase_manager", status="active",
    ).order_by(models.WorkspaceMembership.created_at.asc()).first()
    if not membership:
        return
    reviewer = db.get(models.User, membership.user_id)
    task = models.Task(
        tenant_id=extraction.tenant_id, plant_id=extraction.plant_id,
        title="Verify supplier invoice evidence",
        requested_outcome="Review extracted invoice fields against the source document before matching.",
        owner_role="purchase_manager", owner_user_id=reviewer.id if reviewer else None,
        owner_membership_id=membership.id, due_at=utcnow(), status="open", severity="action",
        entity_type="invoice_extraction_runs", entity_id=extraction.id,
        semantic_key=semantic_key, assignment_source="document_pipeline",
    )
    db.add(task)
    if reviewer:
        db.add(models.Notification(
            tenant_id=extraction.tenant_id, plant_id=extraction.plant_id,
            user_id=reviewer.id, membership_id=membership.id,
            category="invoice_review_pending", severity="action",
            title="Supplier invoice needs verification",
            body=f"{document.filename} passed validation and its extracted fields need review.",
            linked_entity_type="invoice_extraction_run", linked_entity_id=extraction.id,
            navigation_target=f"/invoices?extraction={extraction.id}", dedupe_key=semantic_key,
        ))


def sync_invoice_match_work(db: Session, user: models.User, invoice: models.SupplierInvoice, match: models.InvoiceMatchResult) -> None:
    semantic_key = f"invoice_match:{invoice.id}:exception"
    active = workflows.user_scope_query(db, models.Task, user).filter_by(semantic_key=semantic_key).filter(
        models.Task.status.in_(["open", "accepted", "in_progress", "blocked", "review"]),
    ).first()
    if match.result == "matched":
        if active:
            active.status = "completed"; active.completed_at = utcnow()
            active.completion_summary = f"Latest match {match.business_number} passed after corrected source evidence."
        return
    if active:
        active.blocker_reason = ", ".join(match.variances.get("exceptions") or [])
        return
    membership = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status="active",
    ).first()
    task = models.Task(
        tenant_id=user.tenant_id, plant_id=user.plant_id, title=f"Resolve invoice variance {invoice.business_number}",
        requested_outcome="Correct the supplier/source record or receipt evidence, then rerun deterministic matching.",
        owner_role="purchase_manager", owner_user_id=user.id, owner_membership_id=membership.id if membership else None,
        due_at=utcnow(), status="blocked", severity="critical", entity_type="supplier_invoices", entity_id=invoice.id,
        semantic_key=semantic_key, assignment_source="invoice_matching",
        blocker_reason=", ".join(match.variances.get("exceptions") or []),
    )
    db.add(task)
    if membership:
        db.add(models.Notification(
            tenant_id=user.tenant_id, plant_id=user.plant_id, user_id=user.id, membership_id=membership.id,
            category="invoice_match_exception", severity="critical", title="Invoice evidence does not match",
            body=f"{invoice.business_number} needs corrected order, receipt, or supplier-invoice evidence before finance review.",
            linked_entity_type="supplier_invoice", linked_entity_id=invoice.id,
            navigation_target=f"/invoices?invoice={invoice.id}", dedupe_key=semantic_key,
        ))


def create_invoice(db: Session, user: models.User, payload: dict[str, Any]) -> models.SupplierInvoice:
    require_role(user, "purchase_manager", ADMIN)
    supplier = workflows.get_scoped_or_404(db, models.Supplier, user, str(payload["supplier_id"]), "Supplier")
    po = workflows.get_scoped_or_404(db, models.PODraft, user, str(payload["po_draft_id"]), "Purchase order")
    if po.supplier_id != supplier.id:
        raise HTTPException(422, "Invoice supplier does not match the purchase order")
    duplicate = workflows.user_scope_query(db, models.SupplierInvoice, user).filter_by(
        supplier_id=supplier.id, invoice_number=str(payload["invoice_number"]).strip(),
    ).first()
    if duplicate:
        raise HTTPException(409, f"Invoice {duplicate.invoice_number} already exists")
    content_hash = str(payload.get("content_hash") or "").strip() or None
    if content_hash:
        duplicate_document = workflows.user_scope_query(db, models.SupplierInvoice, user).filter_by(
            content_hash=content_hash,
        ).first()
        if duplicate_document:
            raise HTTPException(409, f"This invoice document was already captured as {duplicate_document.business_number}")
    lines = list(payload.get("lines") or [])
    if not lines:
        raise HTTPException(422, "At least one invoice line is required")
    subtotal = sum(float(line["line_total"]) for line in lines)
    tax = sum(float(line.get("tax_amount") or 0) for line in lines)
    declared_total = float(payload.get("total_amount") if payload.get("total_amount") is not None else subtotal + tax)
    if abs(declared_total - (subtotal + tax)) > 0.01:
        raise HTTPException(422, "Invoice total must equal line totals plus tax")
    invoice = models.SupplierInvoice(
        id=workflows.next_id(db, models.SupplierInvoice, "INV"), business_number=workflows.next_business_number(db, "INV", user),
        tenant_id=user.tenant_id, plant_id=user.plant_id, supplier_id=supplier.id, po_draft_id=po.id,
        document_id=payload.get("document_id"), invoice_number=str(payload["invoice_number"]).strip(),
        invoice_date=str(payload["invoice_date"]), currency=str(payload.get("currency") or po.currency),
        subtotal=subtotal, tax_amount=tax, total_amount=declared_total, status="captured",
        source=str(payload.get("source") or "manual"), content_hash=content_hash,
    )
    db.add(invoice); db.flush()
    po_lines = {line.id: line for line in workflows.user_scope_query(db, models.PODraftLine, user).filter_by(po_draft_id=po.id).all()}
    for source in lines:
        po_line = po_lines.get(str(source.get("po_line_id") or ""))
        if po_line is None:
            raise HTTPException(422, "Every invoice line must reference a line from this purchase order")
        db.add(models.SupplierInvoiceLine(
            tenant_id=user.tenant_id, plant_id=user.plant_id, invoice_id=invoice.id,
            po_line_id=po_line.id, item_id=po_line.item_id, description=str(source.get("description") or ""),
            quantity=float(source["quantity"]), uom=str(source.get("uom") or po_line.uom),
            unit_price=float(source["unit_price"]), tax_amount=float(source.get("tax_amount") or 0),
            line_total=float(source["line_total"]),
        ))
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "invoice.captured", "supplier_invoice", invoice.id, actor_user_id=user.id, meta={"invoice_number": invoice.invoice_number, "po": po.business_number})
    return invoice


def verify_invoice_extraction(
    db: Session, user: models.User, extraction_id: str, payload: dict[str, Any],
) -> models.SupplierInvoice:
    """Accept buyer-reviewed fields and enter the existing invoice workflow."""
    require_role(user, "purchase_manager", ADMIN)
    extraction = workflows.get_scoped_or_404(
        db, models.InvoiceExtractionRun, user, extraction_id, "Invoice extraction",
    )
    if extraction.invoice_id:
        return workflows.get_scoped_or_404(
            db, models.SupplierInvoice, user, extraction.invoice_id, "Supplier invoice",
        )
    if extraction.status != "needs_review":
        raise HTTPException(409, "This invoice extraction is not awaiting review")
    document = workflows.get_scoped_or_404(db, models.Document, user, extraction.document_id, "Invoice document")
    if document.status != "validated_needs_review":
        raise HTTPException(409, "The invoice document has not passed validation")
    po_id = str(payload.get("po_draft_id") or "")
    if extraction.po_draft_id and po_id != extraction.po_draft_id:
        raise HTTPException(422, "The reviewed purchase order differs from the uploaded invoice context")
    reviewed = dict(payload)
    reviewed["document_id"] = document.id
    reviewed["source"] = "upload"
    reviewed["content_hash"] = document.checksum_sha256
    invoice = create_invoice(db, user, reviewed)
    extraction.invoice_id = invoice.id
    extraction.status = "verified"
    extraction.verified_fields = {
        key: value for key, value in reviewed.items()
        if key not in {"content_hash"}
    }
    extraction.verified_by_user_id = user.id
    extraction.verified_at = utcnow()
    review_task = workflows.user_scope_query(db, models.Task, user).filter_by(
        semantic_key=f"invoice_extraction:{extraction.id}:review",
    ).filter(models.Task.status.in_(["open", "accepted", "in_progress", "blocked", "review"])).first()
    if review_task:
        review_task.status = "completed"
        review_task.completed_at = utcnow()
        review_task.completion_summary = f"Verified and captured as {invoice.business_number}."
    document.linked_entity_type = "supplier_invoice"
    document.linked_entity_id = invoice.id
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name,
        "invoice.extraction_verified", "invoice_extraction_run", extraction.id,
        actor_user_id=user.id,
        meta={"invoice": invoice.business_number, "document_id": document.id},
    )
    return invoice


def prepare_invoice_extraction(
    db: Session, user: models.User, document_id: str, po_id: str,
) -> models.InvoiceExtractionRun:
    """Classify a previously validated assistant attachment as an invoice draft."""
    require_role(user, "purchase_manager", ADMIN)
    document = workflows.get_scoped_or_404(db, models.Document, user, document_id, "Invoice document")
    po = workflows.get_scoped_or_404(db, models.PODraft, user, po_id, "Purchase order")
    if document.status != "validated_needs_review":
        raise HTTPException(409, "Wait for the attachment to pass document validation")
    existing = workflows.user_scope_query(db, models.InvoiceExtractionRun, user).filter_by(
        document_id=document.id,
    ).first()
    if existing:
        if existing.po_draft_id != po.id:
            raise HTTPException(409, "This invoice attachment is already linked to another purchase order")
        return existing
    from app import documents
    from app.storage import object_storage

    content = object_storage.get_bytes(document.storage_bucket, document.storage_key)
    extracted, evidence, parser_version = documents.extract_invoice_fields(document.filename, content)
    extraction = models.InvoiceExtractionRun(
        tenant_id=user.tenant_id, plant_id=user.plant_id, document_id=document.id,
        po_draft_id=po.id, parser_version=parser_version,
        model_version="deterministic@2.0" if "groq-invoice" not in parser_version else "groq-structured",
        status="needs_review", evidence=evidence, extracted_fields=extracted, verified_fields={},
    )
    db.add(extraction)
    db.flush()
    ensure_invoice_review_work(db, extraction, document)
    document.linked_entity_type = "supplier_invoice_draft"
    document.linked_entity_id = po.id
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name,
        "invoice.extraction_prepared", "invoice_extraction_run", extraction.id,
        actor_user_id=user.id, meta={"document_id": document.id, "po": po.business_number},
    )
    return extraction


def prepare_channel_invoice_extraction(
    db: Session, user: models.User, document: models.Document, po: models.PODraft,
) -> models.InvoiceExtractionRun:
    """Prepare validated supplier-channel evidence for mandatory buyer review."""
    if document.tenant_id != user.tenant_id or document.plant_id != user.plant_id:
        raise HTTPException(403, "Invoice document is outside this workspace")
    if po.tenant_id != user.tenant_id or po.plant_id != user.plant_id:
        raise HTTPException(403, "Purchase order is outside this workspace")
    if document.status not in {"available", "validated_needs_review"}:
        raise HTTPException(409, "Invoice attachment must pass document validation")
    existing = workflows.user_scope_query(db, models.InvoiceExtractionRun, user).filter_by(
        document_id=document.id,
    ).first()
    if existing:
        if existing.po_draft_id != po.id:
            raise HTTPException(409, "This invoice attachment is already linked to another purchase order")
        return existing
    from app import documents
    from app.storage import object_storage

    content = object_storage.get_bytes(document.storage_bucket, document.storage_key)
    extracted, evidence, parser_version = documents.extract_invoice_fields(document.filename, content)
    extraction = models.InvoiceExtractionRun(
        tenant_id=user.tenant_id, plant_id=user.plant_id, document_id=document.id,
        po_draft_id=po.id, parser_version=f"{parser_version}+supplier-email@1",
        model_version="deterministic@2.0" if "groq-invoice" not in parser_version else "groq-structured",
        status="needs_review", evidence=evidence, extracted_fields=extracted, verified_fields={},
    )
    db.add(extraction); db.flush()
    ensure_invoice_review_work(db, extraction, document)
    document.linked_entity_type = "supplier_invoice_draft"
    document.linked_entity_id = po.id
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name,
        "invoice.email_extraction_prepared", "invoice_extraction_run", extraction.id,
        actor_user_id=user.id, meta={"document_id": document.id, "po": po.business_number},
    )
    return extraction


def match_invoice(db: Session, user: models.User, invoice_id: str) -> models.InvoiceMatchResult:
    require_role(user, "purchase_manager", ADMIN)
    invoice = workflows.get_scoped_or_404(db, models.SupplierInvoice, user, invoice_id, "Supplier invoice")
    if not invoice.po_draft_id:
        raise HTTPException(422, "Link the invoice to a purchase order before matching")
    po = workflows.get_scoped_or_404(db, models.PODraft, user, invoice.po_draft_id, "Purchase order")
    invoice_lines = workflows.user_scope_query(db, models.SupplierInvoiceLine, user).filter_by(invoice_id=invoice.id).all()
    po_lines = workflows.user_scope_query(db, models.PODraftLine, user).filter_by(po_draft_id=po.id).all()
    # Replacement receipts restore rejected stock; they are not additional
    # payable delivery quantity against the original purchase order.
    receipts = workflows.user_scope_query(db, models.StoreReceipt, user).filter_by(
        po_draft_id=po.id, supplier_return_id=None,
    ).order_by(models.StoreReceipt.created_at.desc()).all()
    receipt = receipts[0] if receipts else None
    po_subtotal = sum(line.quantity * line.unit_price for line in po_lines)
    po_tax = sum(line.quantity * line.unit_price * line.gst_rate / 100 for line in po_lines)
    po_total = po_subtotal + po_tax
    invoiced_quantity = sum(line.quantity for line in invoice_lines)
    ordered_quantity = sum(line.quantity for line in po_lines)
    received_quantity = sum(row.received_quantity for row in receipts)
    amount_variance = round(invoice.total_amount - po_total, 2)
    order_quantity_variance = round(invoiced_quantity - ordered_quantity, 6)
    receipt_quantity_variance = round(invoiced_quantity - received_quantity, 6) if receipts else None
    match_type = "three_way" if receipts else "two_way"
    policy = procurement_policy.active_policy(db, user)
    rules = procurement_policy.policy_rules(policy)
    amount_tolerance = round(po_total * float(rules.get("invoice_price_tolerance_percent", 0)) / 100, 2)
    order_quantity_tolerance = round(ordered_quantity * float(rules.get("invoice_quantity_tolerance_percent", 0)) / 100, 6)
    receipt_quantity_tolerance = round(received_quantity * float(rules.get("invoice_quantity_tolerance_percent", 0)) / 100, 6)
    exceptions = []
    if abs(amount_variance) > max(0.01, amount_tolerance): exceptions.append("invoice_total_differs_from_order")
    if order_quantity_variance > order_quantity_tolerance: exceptions.append("invoice_quantity_exceeds_order")
    if receipts and receipt_quantity_variance is not None and receipt_quantity_variance > receipt_quantity_tolerance: exceptions.append("invoice_quantity_exceeds_received")
    result_value = "matched" if not exceptions else "exception"
    variance_evidence = {"amount": amount_variance, "ordered_quantity": order_quantity_variance, "received_quantity": receipt_quantity_variance, "exceptions": exceptions, "tolerances": {"amount": amount_tolerance, "ordered_quantity": order_quantity_tolerance, "received_quantity": receipt_quantity_tolerance}, "policy_version": policy.policy_version if policy else 1}
    previous = workflows.user_scope_query(db, models.InvoiceMatchResult, user).filter_by(invoice_id=invoice.id).order_by(models.InvoiceMatchResult.created_at.desc()).first()
    if previous and previous.status == "current" and previous.variances == variance_evidence:
        sync_invoice_match_work(db, user, invoice, previous)
        return previous
    if previous and previous.status == "current": previous.status = "superseded"
    match = models.InvoiceMatchResult(
        id=workflows.next_id(db, models.InvoiceMatchResult, "MATCH"), business_number=workflows.next_business_number(db, "MATCH", user),
        tenant_id=user.tenant_id, plant_id=user.plant_id, invoice_id=invoice.id, po_draft_id=po.id,
        receipt_id=receipt.id if receipt else None, match_type=match_type, result=result_value, status="current",
        variances=variance_evidence,
        evidence=[{"record": "invoice", "business_number": invoice.business_number, "amount": invoice.total_amount}, {"record": "purchase_order", "business_number": po.business_number, "amount": round(po_total, 2)}, {"record": "receipts", "count": len(receipts), "received_quantity": received_quantity}],
        performed_at=utcnow(),
    )
    db.add(match)
    invoice.status = "matched" if result_value == "matched" else "match_exception"
    db.flush()
    sync_invoice_match_work(db, user, invoice, match)
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "invoice.matched", "invoice_match_result", match.id, actor_user_id=user.id, meta={"result": result_value, "exceptions": exceptions})
    return match


def prepare_finance_handoff(db: Session, user: models.User, match_id: str) -> models.FinanceHandoff:
    require_role(user, "purchase_manager", ADMIN)
    match = workflows.get_scoped_or_404(db, models.InvoiceMatchResult, user, match_id, "Invoice match")
    if match.result != "matched" or match.status != "current":
        raise HTTPException(409, "Resolve invoice matching exceptions before finance handoff")
    invoice = workflows.get_scoped_or_404(db, models.SupplierInvoice, user, match.invoice_id, "Supplier invoice")
    existing = workflows.user_scope_query(db, models.FinanceHandoff, user).filter_by(invoice_id=invoice.id, match_result_id=match.id).first()
    if existing: return existing
    handoff = models.FinanceHandoff(
        id=workflows.next_id(db, models.FinanceHandoff, "FIN"), business_number=workflows.next_business_number(db, "FIN", user),
        tenant_id=user.tenant_id, plant_id=user.plant_id, invoice_id=invoice.id, match_result_id=match.id,
        status="prepared_for_finance_review", prepared_by_user_id=user.id,
        payload={"invoice_number": invoice.invoice_number, "invoice_business_number": invoice.business_number, "amount": invoice.total_amount, "currency": invoice.currency, "match_type": match.match_type, "payment_release": "not_authorized"},
    )
    db.add(handoff); invoice.status = "finance_handoff_prepared"
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "finance_handoff.prepared", "finance_handoff", handoff.id, actor_user_id=user.id, meta={"payment_release": False})
    return handoff
