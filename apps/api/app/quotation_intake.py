from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN, PURCHASE_EXECUTIVE, PURCHASE_MANAGER, require_role
from app.db import models
from app.repositories import get_scoped_or_404


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _eligible_suppliers(db: Session, intake: models.QuotationIntake) -> list[models.Supplier]:
    rfq = db.get(models.RFQ, intake.rfq_id)
    supplier_ids = list(rfq.supplier_ids or []) if rfq else []
    if not supplier_ids:
        return []
    return db.query(models.Supplier).filter(
        models.Supplier.tenant_id == intake.tenant_id,
        models.Supplier.plant_id == intake.plant_id,
        models.Supplier.id.in_(supplier_ids),
        models.Supplier.status.in_(["approved", "active"]),
    ).all()


def _supplier_resolution(db: Session, intake: models.QuotationIntake, fields: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    suppliers = _eligible_suppliers(db, intake)
    vendor_id = _normalized(fields.get("erp_vendor_id"))
    legal_name = _normalized(fields.get("supplier_legal_name"))
    if vendor_id:
        matches = [supplier for supplier in suppliers if _normalized(supplier.erp_vendor_id) == vendor_id]
        if len(matches) == 1:
            return matches[0].id, [{"supplier_id": matches[0].id, "name": matches[0].name, "confidence": 1.0, "reason": "exact_vendor_id"}]
    if legal_name:
        matches = [supplier for supplier in suppliers if _normalized(supplier.name) == legal_name]
        if len(matches) == 1:
            return matches[0].id, [{"supplier_id": matches[0].id, "name": matches[0].name, "confidence": 1.0, "reason": "exact_legal_name"}]
    ranked = sorted(
        [{
            "supplier_id": supplier.id,
            "name": supplier.name,
            "confidence": round(SequenceMatcher(None, legal_name, _normalized(supplier.name)).ratio(), 4) if legal_name else 0,
            "reason": "name_similarity",
        } for supplier in suppliers],
        key=lambda item: item["confidence"],
        reverse=True,
    )[:3]
    if ranked and ranked[0]["confidence"] >= 0.92 and (
        len(ranked) == 1 or ranked[0]["confidence"] - ranked[1]["confidence"] >= 0.15
    ) and not vendor_id:
        return str(ranked[0]["supplier_id"]), ranked
    return None, ranked


def apply_extraction_to_intake(
    db: Session, intake: models.QuotationIntake, extraction: models.QuoteExtractionRun
) -> models.QuotationIntake:
    supplier_id, candidates = _supplier_resolution(db, intake, extraction.extracted_fields or {})
    intake.extraction_run_id = extraction.id
    intake.extracted_fields = extraction.extracted_fields or {}
    intake.evidence = extraction.evidence or []
    intake.supplier_candidates = candidates
    intake.inferred_supplier_id = supplier_id
    intake.parser_version = extraction.parser_version
    intake.provider = "llamaparse" if extraction.parser_version.startswith("llamaparse") else "local_fallback"
    provider_evidence = next((item for item in intake.evidence if item.get("provider_job_id")), None)
    intake.provider_job_id = str(provider_evidence["provider_job_id"]) if provider_evidence else None
    intake.status = "needs_review" if intake.extracted_fields else "needs_manual_entry"
    return intake


def intake_payload(db: Session, intake: models.QuotationIntake) -> dict[str, Any]:
    document = db.get(models.Document, intake.document_id) if intake.document_id else None
    job = db.get(models.DocumentJob, intake.document_job_id) if intake.document_job_id else None
    return {
        "id": intake.id,
        "version": intake.version,
        "mode": intake.mode,
        "status": intake.status,
        "rfq_id": intake.rfq_id,
        "document": {
            "id": document.id, "filename": document.filename, "status": document.status,
        } if document else None,
        "job": {"id": job.id, "status": job.status, "error_code": job.error_code} if job else None,
        "supplier_id": intake.confirmed_supplier_id or intake.inferred_supplier_id,
        "supplier_candidates": intake.supplier_candidates or [],
        "fields": intake.extracted_fields or {},
        "evidence": intake.evidence or [],
        "parser": {
            "provider": intake.provider,
            "version": intake.parser_version,
            "provider_job_id": intake.provider_job_id,
        },
        "quote_id": intake.quote_id,
        "error": {"code": intake.error_code, "detail": intake.error_detail} if intake.error_code else None,
        "authorized_actions": [] if intake.status == "accepted" else ["accept", "retry"],
    }


def accept_intake(
    db: Session, user: models.User, intake_id: str, payload: dict[str, Any]
) -> tuple[models.QuotationIntake, models.SupplierQuote]:
    from app.domains import workflows

    require_role(user, PURCHASE_EXECUTIVE, PURCHASE_MANAGER, ADMIN)
    intake = get_scoped_or_404(db, models.QuotationIntake, user, intake_id, "Quotation intake")
    if intake.status == "accepted" and intake.quote_id:
        quote = get_scoped_or_404(db, models.SupplierQuote, user, intake.quote_id, "Quote")
        return intake, quote
    if intake.status not in {"needs_review", "needs_manual_entry"}:
        raise HTTPException(409, "Quotation extraction is not ready for acceptance")
    fields = {**(intake.extracted_fields or {}), **(payload.get("fields") or {})}
    supplier_id = str(payload.get("supplier_id") or intake.inferred_supplier_id or "")
    lines = fields.get("lines") or ([{
        key: fields.get(key) for key in (
            "quantity", "uom", "unit_price", "gst_rate", "freight", "packaging",
            "lead_time_days", "promised_date", "moq", "certificates", "deviation_notes",
        )
    }] if fields else [])
    missing: list[str] = []
    for field in ("quote_number", "quote_date", "validity_date"):
        if not fields.get(field):
            missing.append(field)
    if not supplier_id:
        missing.append("supplier_id")
    if not lines or not lines[0].get("quantity") or lines[0].get("unit_price") is None:
        missing.append("lines[0].quantity/unit_price")
    if missing:
        raise HTTPException(422, detail={"message": "Correct the required quotation fields before accepting", "missing_fields": missing})
    quote_payload = {
        "rfq_id": intake.rfq_id,
        "supplier_id": supplier_id,
        "quote_number": fields["quote_number"],
        "quote_date": fields["quote_date"],
        "validity_date": fields["validity_date"],
        "payment_terms": fields.get("payment_terms") or "30 days from GRN",
        "currency": fields.get("currency") or "INR",
        "line": lines[0],
        "lines": lines,
        "parser_version": intake.parser_version,
    }
    quote = workflows.receive_buyer_quote(db, user, quote_payload)
    if intake.document_id:
        document = db.get(models.Document, intake.document_id)
        if document:
            document.linked_entity_type = "supplier_quote"
            document.linked_entity_id = quote.id
    extraction = db.get(models.QuoteExtractionRun, intake.extraction_run_id) if intake.extraction_run_id else None
    if extraction:
        extraction.quote_id = quote.id
        extraction.status = "needs_review"
    intake.confirmed_supplier_id = supplier_id
    intake.extracted_fields = fields
    intake.quote_id = quote.id
    intake.status = "accepted"
    intake.accepted_by_user_id = user.id
    intake.accepted_at = datetime.now(timezone.utc)
    return intake, quote
