"""Cross-domain case index while domain models retain detailed behavior."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import models
from app.platform.models import OperationalCase


def link_case(db: Session, *, tenant_id: str, plant_id: str | None, domain: str,
              domain_case_type: str, domain_case_id: str, title: str, status: str,
              severity: str, source_event_id: str | None = None, context: dict | None = None) -> OperationalCase:
    context = context or {}
    shared_id = context.get("operational_case_id")
    row = db.query(OperationalCase).filter_by(id=shared_id, tenant_id=tenant_id).first() if shared_id else None
    rows = db.query(OperationalCase).filter_by(tenant_id=tenant_id, case_type=domain_case_type).all() if row is None else []
    row = row or next((item for item in rows if (item.context or {}).get("domain_case_id") == domain_case_id), None)
    if row is None:
        row = OperationalCase(tenant_id=tenant_id, plant_id=plant_id, case_type=domain_case_type,
                              title=title, source_event_id=source_event_id)
        db.add(row)
    row.status, row.severity = status, severity
    domains = sorted(set((row.context or {}).get("domains", [])) | {domain})
    row.context = {**(row.context or {}), **context, "domain": domain, "domains": domains,
                   "domain_case_id": domain_case_id}
    row.responsible_team = row.responsible_team or domain.upper()
    row.aggregation_key = row.aggregation_key or f"{domain}:{domain_case_type}:{domain_case_id}"
    return row


def reconcile_domain_cases(db: Session, tenant_id: str) -> int:
    count = 0
    for row in db.query(models.Case).filter_by(tenant_id=tenant_id).all():
        linked = link_case(db, tenant_id=tenant_id, plant_id=row.plant_id, domain="procurement",
                  domain_case_type="procurement_exception", domain_case_id=row.id,
                  title=row.title, status=row.status, severity=row.severity,
                  context={"operational_case_id": row.operational_case_id, "requirement_id": row.requirement_id, "rfq_id": row.rfq_id,
                           "po_draft_id": row.po_draft_id, "receipt_id": row.receipt_id,
                           "inspection_id": row.inspection_id})
        row.operational_case_id = linked.id
        count += 1
    for row in db.query(models.RecoveryCase).filter_by(tenant_id=tenant_id).all():
        deviation = db.get(models.OperationalDeviation, row.deviation_id)
        status = "closed" if row.status in {"verified", "failed", "abandoned"} else "open"
        linked = link_case(db, tenant_id=tenant_id, plant_id=row.plant_id, domain="operations",
                  domain_case_type="operations_recovery", domain_case_id=row.id,
                  title=deviation.title if deviation else f"Recovery {row.id}", status=status,
                  severity=deviation.severity if deviation else "medium",
                  context={"operational_case_id": row.operational_case_id, "deviation_id": row.deviation_id, "recovery_status": row.status,
                           "verified_at": row.verified_at.isoformat() if row.verified_at else None})
        row.operational_case_id = linked.id
        count += 1
    return count
