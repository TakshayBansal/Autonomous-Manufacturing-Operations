"""Contextual authorization boundary for OPA and local policy simulation."""
from __future__ import annotations

import hashlib
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.agent_schemas import PolicyDecision
from app.core.config import get_settings
from app.db import models


class PolicyUnavailable(RuntimeError):
    pass


class PolicyDecisionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def decide(self, *, actor: models.WorkspaceMembership, capability_id: str,
               resource_type: str, resource_id: str | None, context: dict,
               read_only: bool = False, correlation_id: str) -> tuple[PolicyDecision, models.PolicyDecisionRecord]:
        input_data = {
            "actor": {"membership_id": actor.id, "role": actor.role, "tenant_id": actor.tenant_id,
                      "plant_ids": actor.plant_ids, "manager_membership_id": actor.manager_membership_id},
            "capability": capability_id,
            "resource": {"type": resource_type, "id": resource_id, **context},
        }
        shadow = self.settings.opa_mode == "shadow"
        try:
            decision = self._query_opa(input_data)
        except PolicyUnavailable:
            if read_only:
                decision = PolicyDecision(allow=True, requires_confirmation=False, autonomy_tier=0,
                    obligations=[], reason_code="opa_unavailable_read_fallback",
                    policy_version=self.settings.opa_policy_version, shadow=shadow)
            else:
                decision = PolicyDecision(allow=False, requires_confirmation=False, autonomy_tier=0,
                    obligations=[], reason_code="opa_unavailable_default_deny",
                    policy_version=self.settings.opa_policy_version, shadow=shadow)
        digest = hashlib.sha256(json.dumps(input_data, sort_keys=True, default=str).encode()).hexdigest()
        record = models.PolicyDecisionRecord(
            tenant_id=actor.tenant_id, plant_id=actor.default_plant_id, correlation_id=correlation_id,
            actor_membership_id=actor.id, capability_id=capability_id, resource_type=resource_type,
            resource_id=resource_id, allow=decision.allow, requires_confirmation=decision.requires_confirmation,
            autonomy_tier=decision.autonomy_tier, obligations=decision.obligations,
            reason_code=decision.reason_code, policy_version=decision.policy_version,
            shadow=decision.shadow, input_digest=digest,
        )
        self.db.add(record)
        self.db.flush()
        return decision, record

    def _query_opa(self, input_data: dict) -> PolicyDecision:
        if self.settings.opa_mode == "disabled" or self.settings.app_env == "test":
            raise PolicyUnavailable("OPA disabled")
        body = json.dumps({"input": input_data}).encode()
        request = Request(self.settings.opa_url.rstrip("/") + self.settings.opa_decision_path,
                          data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.settings.opa_timeout_seconds) as response:  # noqa: S310 - configured local sidecar
                payload = json.loads(response.read())
        except (OSError, URLError, ValueError) as exc:
            raise PolicyUnavailable("OPA decision endpoint unavailable") from exc
        result = payload.get("result")
        if not isinstance(result, dict):
            raise PolicyUnavailable("OPA returned no decision")
        return PolicyDecision(
            allow=bool(result.get("allow")), requires_confirmation=bool(result.get("requires_confirmation")),
            autonomy_tier=int(result.get("autonomy_tier", 0)), obligations=list(result.get("obligations") or []),
            reason_code=str(result.get("reason_code") or "policy_default_deny"),
            policy_version=str(result.get("policy_version") or self.settings.opa_policy_version),
            shadow=self.settings.opa_mode == "shadow",
        )


def simulate_template(policy: models.AutonomyPolicy, *, role: str, plant_id: str,
                      capability_id: str, spend: float = 0, risk: str = "low",
                      external_effect: bool = False) -> PolicyDecision:
    matches = capability_id == policy.capability_id and role in (policy.roles or [])
    matches = matches and (not policy.plant_ids or plant_id in policy.plant_ids)
    spend_ok = policy.spend_limit is None or spend <= policy.spend_limit
    risk_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    risk_ok = risk_rank.get(risk, 3) <= risk_rank.get(policy.risk_limit, 0)
    external_ok = not external_effect or policy.external_communication != "deny"
    allow = matches and spend_ok and risk_ok and external_ok and policy.state == "published"
    confirmation = allow and (policy.confirmation_required or (external_effect and policy.external_communication == "confirm"))
    reason = "policy_matched" if allow else "policy_scope_or_limit_mismatch"
    return PolicyDecision(allow=allow, requires_confirmation=confirmation,
        autonomy_tier=policy.autonomy_ceiling if allow else 0,
        obligations=["revalidate_entity_version"] + (["record_human_confirmation"] if confirmation else []),
        reason_code=reason, policy_version=policy.policy_version)
