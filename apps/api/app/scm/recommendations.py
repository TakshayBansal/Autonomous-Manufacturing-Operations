"""Explainable ranking and before/after simulation for SCM interventions."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.scm import models
from app.scm.engine import PlanningEvent, PlanningPolicy, plan_material


def rank_run_recommendations(db: Session, run_id: str) -> None:
    rows = db.query(models.SCMRecommendation).filter_by(planning_run_id=run_id).all()
    action_feasibility = {"PULL_IN": 25, "RESCHEDULE_PURCHASE_ORDER": 25, "PUSH_OUT": 20, "CANCEL_REDUCE": 18,
                          "INTERPLANT_TRANSFER": 22, "NEW_BUY": 12}
    scored = []
    for row in rows:
        risk = db.get(models.SCMMaterialRiskSummary, row.risk_summary_id)
        shortage_removed = min(100, int((row.quantity / risk.shortage_qty) * 100)) if risk and risk.shortage_qty else 0
        urgency = min(25, max(0, 30 - ((risk.stockout_date - date.today()).days if risk and risk.stockout_date else 30)))
        feasibility = action_feasibility.get(row.action_type, 10)
        complexity = 5 if row.action_type in {"PULL_IN", "PUSH_OUT"} else 2
        score = Decimal(shortage_removed) + Decimal(urgency + feasibility + complexity)
        row.score = score
        row.score_dimensions = {"shortage_removed_pct": shortage_removed, "urgency": urgency,
            "supplier_feasibility": feasibility, "approval_simplicity": complexity,
            "estimated_cost": "LOW" if row.action_type in {"PULL_IN", "PUSH_OUT", "CANCEL_REDUCE"} else "MEDIUM"}
        row.estimated_impact = {"shortage_removed_qty": str(min(row.quantity, risk.shortage_qty) if risk else 0),
            "resolves_full_shortage": bool(risk and row.quantity >= risk.shortage_qty),
            "inventory_side_effect": "earlier inventory" if row.action_type == "PULL_IN" else "reduced excess"}
        scored.append(row)
    for rank, row in enumerate(sorted(scored, key=lambda item: (-item.score, item.id)), 1):
        row.rank = rank


def simulate(db: Session, recommendation: models.SCMRecommendation) -> models.SCMRecommendationSimulation:
    existing = db.query(models.SCMRecommendationSimulation).filter_by(
        recommendation_id=recommendation.id).order_by(models.SCMRecommendationSimulation.created_at.desc()).first()
    if existing:
        return existing
    run = db.get(models.SCMPlanningRun, recommendation.planning_run_id)
    snapshot = db.query(models.SCMPlanningInputSnapshot).filter_by(planning_run_id=run.id).one()
    material = next(row for row in snapshot.payload["materials"] if row["scm_material_id"] == recommendation.material_id)
    events = []
    for demand in material["demands"]:
        events.append(PlanningEvent(demand["id"], demand.get("demand_type", "DEMAND"),
            date.fromisoformat(demand["date"]), -Decimal(demand["quantity"]), "demand", demand["id"]))
    for supply in material["supplies"]:
        supply_date = date.fromisoformat(supply["date"])
        supply_qty = Decimal(supply["quantity"])
        supply_id = supply.get("canonical_purchase_order_id") or supply["id"]
        if recommendation.source_entity_id == supply_id or recommendation.source_entity_id == supply["id"]:
            if recommendation.action_type in {"PULL_IN", "RESCHEDULE_PURCHASE_ORDER"} and recommendation.proposed_date:
                supply_date = recommendation.proposed_date
            elif recommendation.action_type == "PUSH_OUT":
                supply_date = recommendation.proposed_date or supply_date
            elif recommendation.action_type == "CANCEL_REDUCE":
                supply_qty = max(Decimal("0"), supply_qty - recommendation.quantity)
        events.append(PlanningEvent(supply["id"], "SUPPLY", supply_date, supply_qty,
            "purchase_order", supply_id, metadata=supply))
    if recommendation.action_type == "NEW_BUY" and recommendation.proposed_date:
        events.append(PlanningEvent(f"simulation:{recommendation.id}", "NEW_BUY",
            recommendation.proposed_date, recommendation.quantity, "recommendation", recommendation.id))
    if recommendation.action_type == "INTERPLANT_TRANSFER" and recommendation.proposed_date:
        events.append(PlanningEvent(f"simulation:{recommendation.id}", "INTERPLANT_TRANSFER",
            recommendation.proposed_date, recommendation.quantity, "inventory_position",
            recommendation.source_entity_id or recommendation.id))
    rules = material.get("policy") or {}
    result = plan_material(as_of=run.horizon_start, opening_available=Decimal(material["opening_available"]),
        events=events, policy=PlanningPolicy.from_rules({"horizon_days": (run.horizon_end-run.horizon_start).days+1},
            safety_stock_qty=Decimal(rules.get("safety_stock_qty", "0"))), stale=material.get("stale", False))
    risk = db.get(models.SCMMaterialRiskSummary, recommendation.risk_summary_id)
    resolves = result.stockout_date is None
    row = models.SCMRecommendationSimulation(tenant_id=run.tenant_id, plant_id=run.plant_id,
        recommendation_id=recommendation.id, baseline_run_id=run.id, status="COMPLETED",
        input_overrides={"action_type": recommendation.action_type, "quantity": str(recommendation.quantity),
                         "proposed_date": recommendation.proposed_date.isoformat() if recommendation.proposed_date else None},
        before_metrics={"stockout_date": risk.stockout_date.isoformat() if risk.stockout_date else None,
                        "shortage_qty": str(risk.shortage_qty)},
        after_metrics={"stockout_date": result.stockout_date.isoformat() if result.stockout_date else None,
                       "shortage_qty": str(result.peak_shortage_qty), "ending_balance": str(result.ending_balance)},
        resolves_risk=resolves, explanation={"classification": "DETERMINISTIC_SIMULATION",
            "message": "Candidate is evaluated against the immutable planning snapshot."},
        algorithm_version=run.engine_version)
    db.add(row)
    db.flush()
    return row
