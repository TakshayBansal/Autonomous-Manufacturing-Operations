"""Deterministic SCM recovery contracts and the canonical MAT-182 fixture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.db import models as core
from app.platform.models import OperationalCase, PlatformMaterial, PlatformProduct
from app.platform.case_models import (
    BusinessExposure, CaseCause, CaseEntityLink, ConstraintResult, DecisionAlternative,
    DecisionRecord, FeasibilityEvaluation, NetworkConstraint, RecoveryTarget,
)
from app.platform.case_service import aggregate_case


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def evaluate_strategy(*, strategy: str, shortage_qty: float, stale_inventory: bool = False,
                      origin_available: float | None = None, origin_future_demand: float = 0,
                      transfer_qty: float = 0, lead_time_days: int = 2) -> dict:
    checks = []
    if strategy not in {"INTERPLANT_TRANSFER", "SUPPLIER_PULL_IN", "PRODUCTION_RESEQUENCE"}:
        raise ValueError("Unsupported recovery strategy")
    if shortage_qty < 0 or transfer_qty < 0 or origin_future_demand < 0 or lead_time_days < 0:
        raise ValueError("Recovery quantities and lead times must be non-negative")
    if strategy == "INTERPLANT_TRANSFER":
        if stale_inventory:
            checks.append(("origin_inventory_fresh", "UNKNOWN", True, "Plant B inventory is stale and must be confirmed."))
        else:
            checks.append(("origin_inventory_fresh", "SATISFIED", False, "Plant B inventory is fresh."))
        remaining = None if origin_available is None else origin_available - transfer_qty
        safe = remaining is not None and remaining >= origin_future_demand
        checks.append(("plant_b_future_demand", "UNKNOWN" if remaining is None else "SATISFIED" if safe else "VIOLATED", True,
                       f"Plant B retains {remaining if remaining is not None else 'unknown'} units against {origin_future_demand} future demand."))
        checks.append(("transfer_lead_time", "SATISFIED" if lead_time_days <= 3 else "VIOLATED", True,
                       f"Transfer lead time is {lead_time_days} days."))
    elif strategy == "SUPPLIER_PULL_IN":
        checks = [("supplier_expedite_allowed", "SATISFIED", False, "Supplier X is approved for expedite."),
                  ("confirmation_required", "UNKNOWN", True, "Supplier confirmation is not yet recorded.")]
    else:
        checks = [("material_ready_replacement_order", "SATISFIED", False, "A material-ready order can run before WO-981."),
                  ("honda_commitment_preserved", "SATISFIED", False, "WO-981 remains inside the Honda commitment window.")]
    unavailable = any(state == "VIOLATED" and blocking for _, state, blocking, _ in checks)
    confirmation = any(state == "UNKNOWN" and blocking for _, state, blocking, _ in checks)
    return {"status": "UNAVAILABLE" if unavailable else "REQUIRES_CONFIRMATION" if confirmation else "AVAILABLE",
            "constraints": checks, "shortage_qty": shortage_qty}


def create_mat182_case(db: Session, user: core.User) -> OperationalCase:
    """Idempotently materialize the commercial release scenario."""
    now = _now(); plant = db.get(core.Plant, user.plant_id); company_id = plant.company_id
    material = db.query(PlatformMaterial).filter_by(company_id=company_id, code="MAT-182").first()
    if material is None:
        material = PlatformMaterial(tenant_id=user.tenant_id, plant_id=user.plant_id, company_id=company_id,
            code="MAT-182", name="Automotive ECU control component", material_type="COMPONENT", attributes={"fixture": "mat182"})
        db.add(material); db.flush()
    product = db.query(PlatformProduct).filter_by(company_id=company_id, code="ECU-A").first()
    if product is None:
        product = PlatformProduct(tenant_id=user.tenant_id, plant_id=user.plant_id, company_id=company_id,
            code="ECU-A", name="Honda ECU-A", attributes={"customer": "Honda", "fixture": "mat182"})
        db.add(product); db.flush()
    aggregation_key = f"MAT-182:{user.plant_id}:H421:WO-981"
    from app.scm.models import SCMMaterial, SCMMaterialRisk
    legacy_material = db.query(SCMMaterial).filter_by(tenant_id=user.tenant_id,
        company_id=company_id, material_code="MAT-182").first()
    source_risk = db.query(SCMMaterialRisk).filter_by(tenant_id=user.tenant_id,
        plant_id=user.plant_id, material_id=legacy_material.id).filter(
        SCMMaterialRisk.status.notin_(("RESOLVED", "DISMISSED"))).first() if legacy_material else None
    converged = db.get(OperationalCase, source_risk.operational_case_id) if source_risk and source_risk.operational_case_id else None
    if converged:
        converged.aggregation_key = aggregation_key
        converged.case_type = "SCM_MATERIAL_RISK"
    case = aggregate_case(db, tenant_id=user.tenant_id, plant_id=user.plant_id,
        aggregation_key=aggregation_key, title="MAT-182 shortage threatens Honda H421",
        case_type="SCM_MATERIAL_RISK", source_event_id="PO-812:eta:+4d",
        evidence={"type": "purchase_order.eta_changed", "entity_type": "purchase_order", "entity_id": "PO-812",
                  "old_eta": (now + timedelta(days=2)).isoformat(), "new_eta": (now + timedelta(days=6)).isoformat(),
                  "freshness": "FRESH", "confidence": 1}, severity="critical", decision_deadline=now + timedelta(days=1))
    aggregate_case(db, tenant_id=user.tenant_id, plant_id=user.plant_id,
        aggregation_key=case.aggregation_key, title=case.title, case_type=case.case_type,
        source_event_id="H421:demand:+11pct", evidence={"type": "customer_order.changed",
        "entity_type": "customer_order", "entity_id": "H421", "change_percent": 11,
        "freshness": "FRESH", "confidence": 1}, severity="critical", decision_deadline=case.decision_deadline)
    case.title = "MAT-182 shortage threatens Honda H421"
    case.summary = "PO-812 moved four days while Honda H421 demand rose 11%, creating an approximately four-day component gap."
    case.priority_score, case.confidence, case.expected_impact_at = 98, .94, now + timedelta(days=3)
    case.responsible_team, case.correlation_id = "SCM", f"mat182:{case.id}"
    supplier = db.query(core.Supplier).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, name="Supplier X").first()
    purchase_order = db.query(core.PODraft).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, business_number="PO-812").first()
    work_order = db.query(core.ProductionWorkOrder).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, external_reference="WO-981").first()
    line = db.query(core.ProductionLine).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id, code="LINE-3").first()
    if not db.query(CaseCause).filter_by(case_id=case.id).first():
        db.add(CaseCause(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
            cause_type="SUPPLIER_DELAY", entity_type="purchase_order", entity_id="PO-812",
            description="Supplier X moved PO-812 ETA by four days.", confidence=1, evidence_ids=[]))
        for entity_type, entity_id, relationship, importance in [
            ("material", material.id, "MATERIAL", 1), ("purchase_order", purchase_order.id if purchase_order else "PO-812", "PURCHASE_ORDER", 1),
            ("supplier", supplier.id if supplier else "Supplier X", "SUPPLIER", .9), ("product", product.id, "IMPACTED", 1),
            ("production_order", work_order.id if work_order else "WO-981", "PRODUCTION_ORDER", 1), ("work_center", line.id if line else "Line 3", "IMPACTED", .9),
            ("customer_order", "H421", "CUSTOMER_COMMITMENT", 1)]:
            db.add(CaseEntityLink(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
                entity_type=entity_type, entity_id=entity_id, relationship=relationship, importance=importance))
        db.add(BusinessExposure(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
            metric="production_units_at_risk", baseline=0, projected=440, delta=440, unit="EA",
            methodology="Pegged MAT-182 shortage to WO-981 quantity in the active planning snapshot.", confidence=.92,
            attribution_state="PROJECTED", computed_at=now))
        db.add(NetworkConstraint(tenant_id=user.tenant_id, plant_id=user.plant_id, constraint_type="TRANSFER_LANE",
            subject_type="material", subject_id=material.id, values={"origin": "Plant B", "destination": "Plant A", "lead_time_days": 2, "cost": 18000},
            source="fixture", provenance={"record": "LANE-B-A"}, observed_at=now, freshness_policy={"max_age_hours": 24}))
    db.flush()
    if not db.query(DecisionRecord).filter_by(case_id=case.id).first():
        from app.scm.models import SCMPlanningRun
        planning = db.query(SCMPlanningRun).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id,
            status="COMPLETED").order_by(SCMPlanningRun.completed_at.desc()).first()
        baseline_id = planning.id if planning else "MAT182-DEMO-BASELINE"
        record = DecisionRecord(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
            planning_run_id=baseline_id, decision_deadline=case.decision_deadline, decision="PENDING",
            policy_version="scm-recovery@1", ai_assisted=False)
        db.add(record); db.flush()
        definitions = [
            ("INTERPLANT_TRANSFER", dict(origin_available=950, origin_future_demand=300, transfer_qty=440), 18000, 48, .93, 92),
            ("SUPPLIER_PULL_IN", {}, 26000, 72, .76, 78),
            ("PRODUCTION_RESEQUENCE", {}, 6000, 12, .62, 69),
        ]
        for rank, (strategy, kwargs, cost, hours, probability, score) in enumerate(definitions, 1):
            result = evaluate_strategy(strategy=strategy, shortage_qty=440, **kwargs)
            evaluation = FeasibilityEvaluation(tenant_id=user.tenant_id, plant_id=user.plant_id,
                case_id=case.id, strategy_type=strategy, status=result["status"], estimated_cost=cost,
                time_to_effect_hours=hours, approval_requirements=["PLANT_MANAGER"],
                freshness_state="FRESH", confidence=probability)
            db.add(evaluation); db.flush()
            for key, state, blocking, explanation in result["constraints"]:
                db.add(ConstraintResult(tenant_id=user.tenant_id, plant_id=user.plant_id,
                    feasibility_evaluation_id=evaluation.id, constraint_key=key, state=state,
                    blocking=blocking, explanation=explanation, evidence={"fixture": "MAT-182"}))
            alternative = DecisionAlternative(tenant_id=user.tenant_id, plant_id=user.plant_id,
                decision_record_id=record.id, strategy_type=strategy, parameters=kwargs,
                expected_impact={"protected_units": 440, "customer_order": "H421"}, cost=cost,
                time_to_effect_hours=hours, success_probability=probability,
                side_effects=[], feasibility_evaluation_id=evaluation.id, score=score,
                score_dimensions={"service_protection": score, "cost": max(0, 100-cost/500)}, ranking=rank,
                evidence=[{"type": "planning_snapshot", "ref": baseline_id}])
            db.add(alternative); db.flush()
            if rank == 1: record.recommended_alternative_id = alternative.id
        db.add(RecoveryTarget(tenant_id=user.tenant_id, plant_id=user.plant_id, case_id=case.id,
            target_type="STABILITY", metric="confirmed_coverage_ratio", operator=">=", threshold=1,
            target=1, baseline=.73, required_observation_count=2, freshness_requirement="FRESH"))
    if case.current_strategy_id is None:
        case.status = "decision_required"
    return case
