from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN, require_role
from app.db import models
from app.domains import workflows


DEFAULT_RULES: dict[str, Any] = {
    "minimum_quotation_count": 1,
    "quotation_thresholds": [],
    "allowed_currencies": ["INR"],
    "require_unexpired_quotes": False,
    "allow_split_awards": True,
    "require_single_source_justification": True,
    "segregation": {"requester_cannot_submit_comparison": False},
    "approval_matrix": [
        {"minimum_amount": 0, "roles": ["plant_manager", "purchase_executive"]},
    ],
    "over_delivery_tolerance_percent": 0,
    "invoice_quantity_tolerance_percent": 0,
    "invoice_price_tolerance_percent": 0,
}


def policy_rules(policy: models.ProcurementPolicy | None) -> dict[str, Any]:
    merged = dict(DEFAULT_RULES)
    if policy:
        merged.update(policy.rules or {})
    return merged


def active_policy(db: Session, user: models.User) -> models.ProcurementPolicy | None:
    return workflows.user_scope_query(db, models.ProcurementPolicy, user).filter_by(status="active").order_by(
        models.ProcurementPolicy.policy_version.desc(), models.ProcurementPolicy.created_at.desc()
    ).first()


def _minimum_quotes(rules: dict[str, Any], amount: float) -> int:
    result = max(1, int(rules.get("minimum_quotation_count", 1)))
    thresholds = sorted(rules.get("quotation_thresholds") or [], key=lambda row: float(row.get("minimum_amount", 0)))
    for threshold in thresholds:
        if amount >= float(threshold.get("minimum_amount", 0)):
            result = max(result, int(threshold.get("count", result)))
    return result


def _approval_roles(rules: dict[str, Any], amount: float) -> list[str]:
    roles = ["plant_manager", "purchase_executive"]
    matrix = sorted(rules.get("approval_matrix") or [], key=lambda row: float(row.get("minimum_amount", 0)))
    for threshold in matrix:
        if amount >= float(threshold.get("minimum_amount", 0)):
            roles = [str(role) for role in threshold.get("roles") or roles]
    return list(dict.fromkeys(roles))


def evaluate_comparison(
    db: Session, user: models.User, comparison: models.BidComparison, rationale: str = "", *, persist: bool = True
) -> dict[str, Any]:
    rfq = workflows.get_scoped_or_404(db, models.RFQ, user, comparison.rfq_id, "RFQ")
    requirement = workflows.get_scoped_or_404(db, models.PurchaseRequirement, user, rfq.requirement_id, "Requirement")
    quotes = workflows.user_scope_query(db, models.SupplierQuote, user).filter(
        models.SupplierQuote.rfq_id == rfq.id,
        models.SupplierQuote.verification_status == "verified",
    ).all()
    policy = active_policy(db, user)
    rules = policy_rules(policy)
    rows = comparison.rows or []
    amount = round(sum(float(row.get("total_net_landed_cost") or 0) for row in rows if row.get("recommendation") == "Recommended"), 2)
    if not amount:
        amount = round(min((float(row.get("total_net_landed_cost") or 0) for row in rows if not row.get("disqualified")), default=0), 2)
    findings: list[dict[str, Any]] = []

    supplier_count = len({quote.supplier_id for quote in quotes})
    required_quotes = _minimum_quotes(rules, amount)
    if supplier_count < required_quotes:
        justified = bool(rationale.strip()) and any(term in rationale.casefold() for term in ("single source", "emergency", "sole source"))
        findings.append({
            "rule": "minimum_quotation_count", "severity": "warning" if justified else "blocker",
            "message": f"{required_quotes} verified supplier quotations are required; {supplier_count} are available.",
            "actual": supplier_count, "required": required_quotes, "justified": justified,
        })

    allowed = {str(value).upper() for value in rules.get("allowed_currencies") or []}
    disallowed = sorted({quote.currency.upper() for quote in quotes if allowed and quote.currency.upper() not in allowed})
    if disallowed:
        findings.append({"rule": "allowed_currencies", "severity": "blocker", "message": f"Currencies not allowed by policy: {', '.join(disallowed)}.", "actual": disallowed})

    if rules.get("require_unexpired_quotes", False):
        today = date.today()
        expired = []
        for quote in quotes:
            if not quote.validity_date:
                expired.append(quote.business_number or quote.quote_number or "quotation")
                continue
            try:
                if date.fromisoformat(quote.validity_date) < today:
                    expired.append(quote.business_number or quote.quote_number or "quotation")
            except ValueError:
                expired.append(quote.business_number or quote.quote_number or "quotation")
        if expired:
            findings.append({"rule": "quote_validity", "severity": "blocker", "message": "Every compared quotation must have a current validity date.", "records": expired})

    segregation = rules.get("segregation") or {}
    membership = db.query(models.WorkspaceMembership).filter_by(user_id=user.id, tenant_id=user.tenant_id, status="active").first()
    if segregation.get("requester_cannot_submit_comparison") and membership and requirement.created_by_membership_id == membership.id:
        findings.append({"rule": "segregation_of_duties", "severity": "blocker", "message": "The requirement requester cannot submit its supplier comparison."})

    blockers = [finding for finding in findings if finding["severity"] == "blocker"]
    warnings = [finding for finding in findings if finding["severity"] == "warning"]
    decision = "blocked" if blockers else "requires_justification" if warnings else "pass"
    roles = _approval_roles(rules, amount)
    result = {
        "decision": decision, "findings": findings, "required_approval_roles": roles,
        "evaluated_amount": amount, "policy_id": policy.id if policy else None,
        "policy_name": policy.name if policy else "Safe default procurement policy",
        "policy_version": policy.policy_version if policy else 1,
    }
    if persist:
        existing = workflows.user_scope_query(db, models.ProcurementPolicyEvaluation, user).filter_by(
            entity_type="bid_comparison", entity_id=comparison.id,
            entity_version=comparison.comparison_version, policy_version=result["policy_version"],
        ).first()
        if existing is None:
            existing = models.ProcurementPolicyEvaluation(
                tenant_id=user.tenant_id, plant_id=user.plant_id, policy_id=result["policy_id"],
                policy_version=result["policy_version"], entity_type="bid_comparison", entity_id=comparison.id,
                entity_version=comparison.comparison_version, decision=decision, findings=findings,
                required_approval_roles=roles, evaluated_by_user_id=user.id,
            )
            db.add(existing)
        else:
            existing.decision = decision
            existing.findings = findings
            existing.required_approval_roles = roles
            existing.evaluated_by_user_id = user.id
            existing.evaluated_at = datetime.now(timezone.utc)
        db.flush()
        result["evaluation_id"] = existing.id
    return result


def enforce_comparison(db: Session, user: models.User, comparison: models.BidComparison, rationale: str) -> dict[str, Any]:
    result = evaluate_comparison(db, user, comparison, rationale)
    if result["decision"] == "blocked":
        raise HTTPException(status_code=409, detail={"message": "Procurement policy requirements are not satisfied", **result})
    return result


def create_policy(db: Session, user: models.User, name: str, rules: dict[str, Any]) -> models.ProcurementPolicy:
    require_role(user, ADMIN)
    latest = workflows.user_scope_query(db, models.ProcurementPolicy, user).filter_by(name=name).order_by(models.ProcurementPolicy.policy_version.desc()).first()
    policy = models.ProcurementPolicy(
        tenant_id=user.tenant_id, plant_id=user.plant_id, name=name,
        policy_version=(latest.policy_version + 1 if latest else 1), status="draft", rules=policy_rules(None) | rules,
    )
    db.add(policy)
    db.flush()
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "procurement_policy.drafted", "procurement_policy", policy.id, actor_user_id=user.id, meta={"policy_version": policy.policy_version})
    return policy


def activate_policy(db: Session, user: models.User, policy_id: str) -> models.ProcurementPolicy:
    require_role(user, ADMIN)
    policy = workflows.get_scoped_or_404(db, models.ProcurementPolicy, user, policy_id, "Procurement policy")
    if policy.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft procurement policy can be activated")
    for active in workflows.user_scope_query(db, models.ProcurementPolicy, user).filter_by(status="active").all():
        active.status = "retired"
    policy.status = "active"
    policy.effective_from = datetime.now(timezone.utc)
    policy.approved_at = policy.effective_from
    policy.approved_by_user_id = user.id
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "procurement_policy.activated", "procurement_policy", policy.id, actor_user_id=user.id, meta={"policy_version": policy.policy_version, "rules": policy.rules})
    return policy
