"""Phase 3 risk lifecycle, readiness, graph impact and run deltas."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.orm import Session

from app.platform.models import OperationalCase, PlatformMaterial
from app.platform.relationships import get_impact
from app.scm import models


ACTIVE_RISK_STATUSES = {"NEW", "ACKNOWLEDGED", "UNDER_REVIEW", "ACTION_PENDING", "WAITING_EXTERNAL", "MONITORING"}


def _material_snapshot(snapshot: models.SCMPlanningInputSnapshot, scm_material_id: str) -> dict:
    return next((row for row in snapshot.payload.get("materials", []) if row["scm_material_id"] == scm_material_id), {})


def _drivers(current: dict, previous: dict | None) -> list[dict]:
    drivers: list[dict] = []
    if previous:
        if current.get("opening_available") != previous.get("opening_available"):
            drivers.append({"type": "INVENTORY_CHANGE", "old_quantity": previous.get("opening_available"),
                            "new_quantity": current.get("opening_available")})
        previous_supply = {row.get("canonical_purchase_order_id") or row["id"]: row
                           for row in previous.get("supplies", [])}
        for supply in current.get("supplies", []):
            supply_key = supply.get("canonical_purchase_order_id") or supply["id"]
            old = previous_supply.get(supply_key)
            if old and old["date"] != supply["date"]:
                drivers.append({"type": "PO_DATE_CHANGE", "entity_id": supply_key,
                                "old_date": old["date"], "new_date": supply["date"]})
        old_demand = sum((Decimal(row["quantity"]) for row in previous.get("demands", [])), Decimal("0"))
        new_demand = sum((Decimal(row["quantity"]) for row in current.get("demands", [])), Decimal("0"))
        if old_demand != new_demand:
            drivers.append({"type": "DEMAND_CHANGE", "old_quantity": str(old_demand), "new_quantity": str(new_demand)})
    if not drivers:
        late = [row for row in current.get("supplies", [])]
        if late:
            drivers.append({"type": "SUPPLY_TIMING", "entity_id": late[0].get("canonical_purchase_order_id") or late[0]["id"],
                            "confirmed_date": late[0]["date"]})
        if current.get("demands"):
            drivers.append({"type": "DEMAND_REQUIREMENT", "source_reference": current["demands"][0].get("source_reference")})
    return drivers


def reconcile_material_risks(db: Session, run: models.SCMPlanningRun,
                             snapshot: models.SCMPlanningInputSnapshot) -> int:
    summaries = db.query(models.SCMMaterialRiskSummary).filter_by(planning_run_id=run.id).all()
    current_keys: set[str] = set()
    created_or_updated = 0
    previous_run = db.query(models.SCMPlanningRun).filter(models.SCMPlanningRun.tenant_id == run.tenant_id,
        models.SCMPlanningRun.plant_id == run.plant_id, models.SCMPlanningRun.status == "COMPLETED",
        models.SCMPlanningRun.id != run.id, models.SCMPlanningRun.completed_at < run.completed_at).order_by(
        models.SCMPlanningRun.completed_at.desc()).first()
    previous_snapshot = db.query(models.SCMPlanningInputSnapshot).filter_by(
        planning_run_id=previous_run.id).first() if previous_run else None
    for summary in summaries:
        material = _material_snapshot(snapshot, summary.material_id)
        canonical_id = material.get("canonical_material_id")
        if not canonical_id or summary.severity in {"GREEN", "UNKNOWN"}:
            continue
        windows = db.query(models.SCMShortageWindow).filter_by(planning_run_id=run.id,
            material_id=summary.material_id).order_by(models.SCMShortageWindow.start_date).all()
        if not windows:
            continue
        window = windows[0]
        semantic_key = f"SHORTAGE:{canonical_id}"
        canonical_material = db.get(PlatformMaterial, canonical_id)
        material_label = canonical_material.code if canonical_material else material.get("material_code") or "Material"
        current_keys.add(semantic_key)
        impact = get_impact(db, run.tenant_id, "material", canonical_id)
        affected = [node for node in impact["nodes"] if node["type"] in {
            "product", "work_order", "work_center", "equipment", "supplier", "purchase_order"}]
        previous_material = _material_snapshot(previous_snapshot, summary.material_id) if previous_snapshot else None
        drivers = _drivers(material, previous_material)
        risk = db.query(models.SCMMaterialRisk).filter_by(tenant_id=run.tenant_id,
            plant_id=run.plant_id, semantic_key=semantic_key).first()
        correlation = run.correlation_id or f"scm-run:{run.id}"
        if risk is None:
            risk = models.SCMMaterialRisk(tenant_id=run.tenant_id, plant_id=run.plant_id,
                latest_planning_run_id=run.id, material_id=summary.material_id,
                canonical_material_id=canonical_id, risk_type="SHORTAGE", severity=summary.severity,
                start_date=window.start_date, end_date=window.end_date, quantity=window.max_shortage_qty,
                confidence=Decimal("0.4") if material.get("stale") else Decimal("1"),
                root_causes=drivers, affected_entities=affected, status="NEW",
                correlation_id=correlation, semantic_key=semantic_key,
                business_impact={"affected_entity_count": len(affected)})
            db.add(risk)
            db.flush()
        else:
            risk.latest_planning_run_id = run.id
            risk.severity, risk.start_date, risk.end_date = summary.severity, window.start_date, window.end_date
            risk.quantity, risk.root_causes, risk.affected_entities = window.max_shortage_qty, drivers, affected
            risk.status, risk.resolved_at = ("NEW" if risk.status == "RESOLVED" else risk.status), None
            risk.correlation_id = correlation
        case = db.get(OperationalCase, risk.operational_case_id) if risk.operational_case_id else None
        if case is None:
            case = OperationalCase(tenant_id=run.tenant_id, plant_id=run.plant_id,
                case_type="material_shortage", title=f"Material shortage: {material_label}",
                severity="critical" if summary.severity == "CRITICAL" else "high", status="open",
                correlation_id=correlation, canonical_entity_type="material", canonical_entity_id=canonical_id,
                context={"scm_material_risk_id": risk.id, "planning_run_id": run.id,
                         "start_date": window.start_date.isoformat(), "end_date": window.end_date.isoformat(),
                         "affected_entities": affected, "drivers": drivers})
            db.add(case)
            db.flush()
            risk.operational_case_id = case.id
        else:
            # Repair titles created by older builds that exposed an internal UUID.
            if canonical_id in case.title or case.title.rstrip().endswith(canonical_id):
                case.title = f"Material shortage: {material_label}"
                if not case.summary or canonical_id in case.summary:
                    case.summary = f"Supply coverage for {material_label} requires a coordinated response."
            case.status = "open"
            case.severity = "critical" if summary.severity == "CRITICAL" else "high"
            case.context = {**case.context, "planning_run_id": run.id,
                            "start_date": window.start_date.isoformat(), "end_date": window.end_date.isoformat(),
                            "affected_entities": affected, "drivers": drivers}
        created_or_updated += 1
    for risk in db.query(models.SCMMaterialRisk).filter_by(tenant_id=run.tenant_id, plant_id=run.plant_id).filter(
            models.SCMMaterialRisk.status.in_(ACTIVE_RISK_STATUSES)).all():
        if risk.semantic_key not in current_keys:
            risk.status = "RESOLVED"
            risk.resolved_at = datetime.now(timezone.utc)
            case = db.get(OperationalCase, risk.operational_case_id) if risk.operational_case_id else None
            if case:
                # A disappeared risk is recovery evidence, not proof of stable recovery.
                # Shared cases with configured targets remain under observation until
                # the required number of distinct fresh planning cycles has passed.
                from app.platform.case_models import RecoveryTarget
                has_targets = db.query(RecoveryTarget.id).filter_by(case_id=case.id).first() is not None
                case.status = "monitoring" if has_targets else "resolved"
                case.recovery_state = "MONITORING" if has_targets else case.recovery_state
                case.resolution_evidence = [{"type": "scm_replan", "planning_run_id": run.id,
                                             "result": "risk_absent"}]
    _record_recovery_observations(db, run)
    return created_or_updated


def synchronize_case_decisions(db: Session, run: models.SCMPlanningRun,
                               snapshot: models.SCMPlanningInputSnapshot) -> int:
    """Project calculated SCM risks/options into the shared case envelope.

    This is intentionally generic: every value comes from this run's immutable
    snapshot, risk summary, graph traversal, and ranked engine recommendations.
    Demo fixtures and LLM output never enter the calculation.
    """
    from app.platform.case_models import (
        BusinessExposure, CaseEntityLink, CaseEvidence, ConstraintResult,
        DecisionAlternative, DecisionRecord, FeasibilityEvaluation, RecoveryTarget,
    )

    now = run.completed_at or datetime.now(timezone.utc)
    synced = 0
    for risk in db.query(models.SCMMaterialRisk).filter_by(
            tenant_id=run.tenant_id, plant_id=run.plant_id,
            latest_planning_run_id=run.id).all():
        if not risk.operational_case_id or risk.status == "RESOLVED":
            continue
        case = db.get(OperationalCase, risk.operational_case_id)
        summary = db.query(models.SCMMaterialRiskSummary).filter_by(
            planning_run_id=run.id, material_id=risk.material_id).first()
        if not case or not summary:
            continue
        material = _material_snapshot(snapshot, risk.material_id)
        case.summary = (f"{risk.quantity:g} EA projected short; "
                        f"{len(risk.affected_entities or [])} connected production entities may be affected.")
        case.priority_score = float(summary.priority_score or 0)
        case.confidence = float(risk.confidence or 0)
        case.detected_at = case.detected_at or now
        case.expected_impact_at = datetime.combine(risk.start_date, datetime.min.time(), timezone.utc)
        case.decision_deadline = case.expected_impact_at - timedelta(days=1)
        case.recovery_state = case.recovery_state or "PENDING"
        case.last_evaluated_at = now
        case.aggregation_key = risk.semantic_key

        if not db.query(CaseEntityLink.id).filter_by(case_id=case.id, entity_type="material",
                                                     entity_id=risk.canonical_material_id,
                                                     relationship="PRIMARY").first():
            db.add(CaseEntityLink(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                entity_type="material", entity_id=risk.canonical_material_id,
                relationship="PRIMARY", importance=1.0))
        for entity in risk.affected_entities or []:
            entity_type, entity_id = entity.get("type"), entity.get("id")
            if not entity_type or not entity_id or db.query(CaseEntityLink.id).filter_by(
                    case_id=case.id, entity_type=entity_type, entity_id=entity_id,
                    relationship="IMPACTED").first():
                continue
            db.add(CaseEntityLink(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                entity_type=entity_type, entity_id=entity_id, relationship="IMPACTED", importance=.8))
        evidence_key = hashlib.sha256(
            f"scm-risk:{run.id}:{summary.id}".encode("utf-8")
        ).hexdigest()
        if not db.query(CaseEvidence.id).filter_by(case_id=case.id, source_event_id=evidence_key).first():
            db.add(CaseEvidence(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                evidence_type="SCM_PLANNING_RESULT", source_entity_type="scm_material_risk_summary",
                source_entity_id=summary.id, source_event_id=evidence_key, observed_at=now,
                recorded_at=now, freshness_state="STALE" if material.get("stale") else "FRESH",
                confidence=float(risk.confidence or 0), payload={"planning_run_id": run.id,
                    "input_snapshot_id": snapshot.id, "input_snapshot_hash": snapshot.payload_hash,
                    "shortage_qty": str(summary.shortage_qty), "drivers": risk.root_causes or []}))
        exposure = db.query(BusinessExposure).filter_by(case_id=case.id,
            metric="production_units_at_risk", input_snapshot_id=snapshot.id).first()
        if not exposure:
            db.add(BusinessExposure(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                metric="production_units_at_risk", baseline=0, projected=float(summary.shortage_qty),
                delta=float(summary.shortage_qty), unit="EA", methodology=(
                    "Peak uncovered component quantity in the deterministic time-phased projection; "
                    "not converted to revenue without customer-value evidence."),
                confidence=float(risk.confidence or 0), attribution_state="PROJECTED",
                calculation_version=run.engine_version, input_snapshot_id=snapshot.id, computed_at=now,
                time_horizon_start=datetime.combine(run.horizon_start, datetime.min.time(), timezone.utc),
                time_horizon_end=datetime.combine(run.horizon_end, datetime.min.time(), timezone.utc)))
        if not db.query(RecoveryTarget.id).filter_by(case_id=case.id,
                                                     metric="confirmed_coverage_ratio").first():
            db.add(RecoveryTarget(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                target_type="STABLE_SUPPLY_COVERAGE", metric="confirmed_coverage_ratio",
                operator=">=", threshold=1, required_duration_seconds=0,
                required_observation_count=2, freshness_requirement="FRESH", baseline=0, target=1))

        recommendations = db.query(models.SCMRecommendation).filter_by(
            planning_run_id=run.id, risk_summary_id=summary.id).order_by(
            models.SCMRecommendation.rank.asc().nullslast()).all()
        if not recommendations:
            synced += 1
            continue
        record = db.query(DecisionRecord).filter_by(case_id=case.id, planning_run_id=run.id).first()
        if not record:
            record = DecisionRecord(tenant_id=run.tenant_id, plant_id=run.plant_id, case_id=case.id,
                baseline_state_snapshot_id=snapshot.id, planning_run_id=run.id,
                decision_deadline=case.decision_deadline, decision="PENDING", ai_assisted=False,
                policy_version="scm-deterministic-ranking@1")
            db.add(record); db.flush()
            alternatives = []
            for index, recommendation in enumerate(recommendations, 1):
                checks = recommendation.constraints_checked or []
                violated = any(check.get("passed") is False for check in checks)
                unknown = any(check.get("passed") is None for check in checks)
                evaluation = FeasibilityEvaluation(tenant_id=run.tenant_id, plant_id=run.plant_id,
                    case_id=case.id, strategy_type=recommendation.action_type,
                    status="VIOLATED" if violated else "UNKNOWN" if unknown else "SATISFIED",
                    approval_requirements=["plant_manager"],
                    freshness_state="STALE" if material.get("stale") else "FRESH",
                    confidence=0.4 if material.get("stale") else 0.9)
                db.add(evaluation); db.flush()
                for check in checks:
                    db.add(ConstraintResult(tenant_id=run.tenant_id, plant_id=run.plant_id,
                        feasibility_evaluation_id=evaluation.id,
                        constraint_key=str(check.get("constraint", "engine_constraint")),
                        state="VIOLATED" if check.get("passed") is False else "UNKNOWN" if check.get("passed") is None else "SATISFIED",
                        blocking=check.get("passed") is False,
                        explanation=str(check.get("reason") or check.get("constraint") or "Evaluated by SCM engine"),
                        evidence=check))
                alternative = DecisionAlternative(tenant_id=run.tenant_id, plant_id=run.plant_id,
                    decision_record_id=record.id, strategy_type=recommendation.action_type,
                    parameters={"recommendation_id": recommendation.id, "quantity": str(recommendation.quantity),
                        "current_date": recommendation.current_date.isoformat() if recommendation.current_date else None,
                        "proposed_date": recommendation.proposed_date.isoformat() if recommendation.proposed_date else None},
                    expected_impact=recommendation.estimated_impact or {}, cost=None,
                    time_to_effect_hours=None, success_probability=None, side_effects=[],
                    feasibility_evaluation_id=evaluation.id, score=float(recommendation.score or 0),
                    score_dimensions=recommendation.score_dimensions or {},
                    ranking=recommendation.rank or index, evidence=recommendation.evidence or [])
                db.add(alternative); db.flush(); alternatives.append(alternative)
            if alternatives:
                record.recommended_alternative_id = min(alternatives, key=lambda row: row.ranking).id
        synced += 1
    return synced


def _record_recovery_observations(db: Session, run: models.SCMPlanningRun) -> int:
    """Turn a completed planning result into replay-safe recovery evidence.

    The initial SCM recovery target is a coverage ratio.  Until a richer service
    metric is configured, this deliberately records a conservative binary value:
    1 only when every projected point for the case material has no shortage.
    """
    from app.platform.case_models import RecoveryObservation, RecoveryTarget
    from app.platform.case_service import verify_recovery

    targets = db.query(RecoveryTarget, OperationalCase).join(
        OperationalCase, OperationalCase.id == RecoveryTarget.case_id).filter(
        RecoveryTarget.tenant_id == run.tenant_id,
        RecoveryTarget.plant_id == run.plant_id,
        RecoveryTarget.metric == "confirmed_coverage_ratio",
        OperationalCase.status.in_(("active", "monitoring", "resolved", "open")),
    ).all()
    recorded = 0
    for target, case in targets:
        material_id = case.canonical_entity_id if case.canonical_entity_type == "material" else None
        if not material_id:
            continue
        points = db.query(models.SCMMaterialProjectionPoint).filter_by(
            planning_run_id=run.id, canonical_material_id=material_id).all()
        if not points:
            continue
        prior = db.query(RecoveryObservation).filter_by(target_id=target.id).all()
        if any((row.source_entity or {}).get("planning_run_id") == run.id for row in prior):
            continue
        stale = any(
            str((point.source_freshness or {}).get("status", "FRESH")).upper() != "FRESH"
            or bool((point.source_freshness or {}).get("stale"))
            for point in points
        )
        covered = all(Decimal(str(point.shortage_qty)) <= 0 for point in points)
        value = Decimal("1") if covered else Decimal("0")
        db.add(RecoveryObservation(
            tenant_id=run.tenant_id, plant_id=run.plant_id, target_id=target.id,
            source_entity={"type": "scm_planning_run", "planning_run_id": run.id},
            observed_value=value, observed_at=run.completed_at or datetime.now(timezone.utc),
            freshness="STALE" if stale else "FRESH",
            evidence={"planning_run_id": run.id, "projection_point_count": len(points),
                      "maximum_shortage_qty": str(max(Decimal(str(point.shortage_qty)) for point in points))},
            satisfied=covered,
        ))
        db.flush()
        verify_recovery(db, case)
        recorded += 1
    return recorded


def build_product_readiness(db: Session, run: models.SCMPlanningRun,
                            snapshot: models.SCMPlanningInputSnapshot) -> int:
    db.query(models.SCMComponentReadiness).filter(models.SCMComponentReadiness.readiness_id.in_(
        db.query(models.SCMProductReadiness.id).filter_by(planning_run_id=run.id))).delete(synchronize_session=False)
    db.query(models.SCMProductReadiness).filter_by(planning_run_id=run.id).delete(synchronize_session=False)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for material in snapshot.payload.get("materials", []):
        for demand in material.get("demands", []):
            lineage = demand.get("lineage") or {}
            product_id = lineage.get("product_id")
            if product_id:
                # One readiness result represents one product/work-order/date.
                # Component-level source references belong in its lineage, not
                # in the identity key, otherwise a multi-component BOM creates
                # duplicate readiness rows for the same production commitment.
                key = (product_id, demand.get("work_order_id"), demand["date"])
                groups[key].append({**demand, "canonical_material_id": material["canonical_material_id"]})
    count = 0
    for (product_id, work_order_id, required_date), components in groups.items():
        component_rows = []
        projection_date = date.fromisoformat(required_date)
        for component in components:
            point = db.query(models.SCMMaterialProjectionPoint).filter_by(planning_run_id=run.id,
                canonical_material_id=component["canonical_material_id"],
                projection_date=projection_date).first()
            available = Decimal(point.projected_after_safety) if point else Decimal("0")
            shortage = max(-available, Decimal("0"))
            status = ("BLOCKED" if not point or available <= 0 or point.planning_status == "CRITICAL"
                      else "AT_RISK" if point.planning_status == "AT_RISK" else "READY")
            component_rows.append((component, available, shortage, status))
        blocking = sum(1 for *_, status in component_rows if status == "BLOCKED")
        at_risk = sum(1 for *_, status in component_rows if status == "AT_RISK")
        status = "BLOCKED" if blocking else ("AT_RISK" if at_risk else "READY")
        readiness = models.SCMProductReadiness(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, product_id=product_id, work_order_id=work_order_id,
            required_date=projection_date, status=status, total_components=len(component_rows),
            covered_components=len(component_rows) - blocking, at_risk_components=at_risk,
            blocking_components=blocking,
            affected_quantity=sum((Decimal(row[0]["quantity"]) for row in component_rows), Decimal("0")),
            explanation={"source_references": sorted({row.get("source_reference") for row in components
                                                       if row.get("source_reference")}),
                         "blocking_material_ids": [row[0]["canonical_material_id"] for row in component_rows if row[3] == "BLOCKED"]})
        db.add(readiness)
        db.flush()
        for component, available, shortage, component_status in component_rows:
            db.add(models.SCMComponentReadiness(tenant_id=run.tenant_id, plant_id=run.plant_id,
                readiness_id=readiness.id, material_id=component["canonical_material_id"],
                required_qty=Decimal(component["quantity"]), projected_available_qty=available,
                shortage_qty=shortage, status=component_status, lineage=component.get("lineage") or {}))
        count += 1
    return count


def build_run_deltas(db: Session, run: models.SCMPlanningRun,
                     snapshot: models.SCMPlanningInputSnapshot) -> int:
    previous = db.query(models.SCMPlanningRun).filter(models.SCMPlanningRun.tenant_id == run.tenant_id,
        models.SCMPlanningRun.plant_id == run.plant_id, models.SCMPlanningRun.status == "COMPLETED",
        models.SCMPlanningRun.id != run.id, models.SCMPlanningRun.completed_at < run.completed_at).order_by(
        models.SCMPlanningRun.completed_at.desc()).first()
    previous_snapshot = db.query(models.SCMPlanningInputSnapshot).filter_by(planning_run_id=previous.id).first() if previous else None
    severity_rank = {"UNKNOWN": 0, "HEALTHY": 1, "AT_RISK": 2, "SHORTAGE": 3, "CRITICAL": 4}

    def worst_status(run_id: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for point in db.query(models.SCMMaterialProjectionPoint).filter_by(planning_run_id=run_id).all():
            if not point.canonical_material_id:
                continue
            current = result.get(point.canonical_material_id, "UNKNOWN")
            if severity_rank.get(point.planning_status, 0) > severity_rank.get(current, 0):
                result[point.canonical_material_id] = point.planning_status
        return result

    previous_status = worst_status(previous.id) if previous else {}
    current_status = worst_status(run.id)
    count = 0
    for canonical_id, status in current_status.items():
        old_status = previous_status.get(canonical_id)
        current_material = next((row for row in snapshot.payload["materials"] if row["canonical_material_id"] == canonical_id), {})
        old_material = next((row for row in previous_snapshot.payload["materials"] if row["canonical_material_id"] == canonical_id), None) if previous_snapshot else None
        drivers = _drivers(current_material, old_material) if old_status != status else []
        db.add(models.SCMPlanningRunDelta(tenant_id=run.tenant_id, plant_id=run.plant_id,
            planning_run_id=run.id, previous_run_id=previous.id if previous else None,
            canonical_material_id=canonical_id, previous_status=old_status, current_status=status,
            drivers=drivers, effect={"status_changed": old_status != status}))
        count += 1
    return count
