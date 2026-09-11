"""Bounded procurement specialists that emit findings and prepared work only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app import cycle_orchestration
from app.agent_schemas import EvidenceCitation, SpecialistFinding, SpecialistRequest, SpecialistResult
from app.db import models


@dataclass(frozen=True)
class Specialist:
    name: str
    work_type: str
    analyze: Callable[[Session, models.ProcurementCycleObjective], tuple[str, float, dict]]


def _cycle_analysis(db: Session, objective: models.ProcurementCycleObjective) -> tuple[str, float, dict]:
    cycle = cycle_orchestration.serialize(db, objective)
    return (f"Cycle is at {cycle['presentation_stage']} with {len(cycle['risks'])} active risk(s).",
            1.0, {"health": cycle["health"], "next": cycle["evaluation"]["conditions_to_advance"]})


def _requirement_analysis(db: Session, objective: models.ProcurementCycleObjective) -> tuple[str, float, dict]:
    requirement = db.get(models.PurchaseRequirement, objective.requirement_id)
    complete = bool(requirement and requirement.item_id and requirement.quantity > 0 and requirement.need_by_date)
    return ("Requirement contains the minimum sourcing fields." if complete else "Requirement needs additional sourcing fields.",
            1.0, {"complete": complete})


SPECIALISTS = {name: Specialist(name, work_type, analyzer) for name, work_type, analyzer in (
    ("requirement_specification", "requirement_review", _requirement_analysis),
    ("supplier_rfq", "rfq_draft", _cycle_analysis),
    ("quotation_normalization", "extraction_review", _cycle_analysis),
    ("comparison_award", "comparison", _cycle_analysis),
    ("fulfilment_monitor", "supplier_reminder", _cycle_analysis),
    ("receipt_quality", "inspection_disposition", _cycle_analysis),
    ("invoice_reconciliation", "invoice_review", _cycle_analysis),
    ("cycle_risk", "risk_escalation", _cycle_analysis),
)}


def run(db: Session, request: SpecialistRequest, owner_membership_id: str | None = None,
        generating_run_id: str | None = None) -> SpecialistResult:
    specialist = SPECIALISTS.get(request.specialist)
    if specialist is None:
        raise ValueError("Unknown procurement specialist")
    objective = db.query(models.ProcurementCycleObjective).filter_by(id=request.objective_id).first()
    if objective is None:
        raise LookupError("Procurement cycle objective not found")
    summary, confidence, content = specialist.analyze(db, objective)
    evidence = [EvidenceCitation(entity_type="purchase_requirement", entity_id=objective.requirement_id,
                                 label=objective.business_number or "Purchase requirement")]
    semantic_key = f"{specialist.name}:{objective.aggregate_version}"
    item = db.query(models.PreparedWorkItem).filter_by(objective_id=objective.id, semantic_key=semantic_key).first()
    if item is None:
        item = models.PreparedWorkItem(
            tenant_id=objective.tenant_id, plant_id=objective.plant_id, objective_id=objective.id,
            task_id=request.task_id, owner_membership_id=owner_membership_id,
            work_type=specialist.work_type, title=summary, content=content,
            evidence=[row.model_dump() for row in evidence], confidence=confidence,
            semantic_key=semantic_key, generating_run_id=generating_run_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(item)
        db.flush()
    finding = SpecialistFinding(finding_type=specialist.work_type, summary=summary,
                                confidence=confidence, evidence=evidence)
    return SpecialistResult(findings=[finding], prepared_work=[{"id": item.id, "type": item.work_type,
        "title": item.title, "confidence": item.confidence, "evidence": item.evidence}],
        deterministic_outputs=content)
