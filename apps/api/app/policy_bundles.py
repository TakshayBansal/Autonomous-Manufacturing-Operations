from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models


def _canonical(content: dict) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":")).encode()


def _signature(digest: str) -> str:
    return hmac.new(get_settings().session_secret.encode(), digest.encode(), hashlib.sha256).hexdigest()


def build(db: Session, tenant_id: str, plant_id: str | None, actor_membership_id: str) -> models.PolicyBundle:
    policies = db.query(models.AutonomyPolicy).filter_by(tenant_id=tenant_id, state="published").order_by(
        models.AutonomyPolicy.capability_id.asc(), models.AutonomyPolicy.created_at.asc()).all()
    content = {"policy_version": f"bundle-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "policies": [{key: getattr(row, key) for key in ("id", "name", "capability_id", "roles", "plant_ids",
            "category_ids", "autonomy_ceiling", "spend_limit", "risk_limit", "external_communication",
            "confirmation_required", "policy_version")} for row in policies]}
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    existing = db.query(models.PolicyBundle).filter_by(tenant_id=tenant_id, digest=digest).first()
    if existing:
        return existing
    db.query(models.PolicyBundle).filter_by(tenant_id=tenant_id, state="active").update(
        {models.PolicyBundle.state: "retired"}, synchronize_session=False)
    bundle = models.PolicyBundle(tenant_id=tenant_id, plant_id=plant_id,
        bundle_version=content["policy_version"], content=content, digest=digest,
        signature=_signature(digest), state="active", created_by_membership_id=actor_membership_id,
        activated_at=datetime.now(timezone.utc))
    db.add(bundle)
    db.flush()
    return bundle


def activate(db: Session, bundle: models.PolicyBundle) -> models.PolicyBundle:
    expected = _signature(bundle.digest)
    actual_digest = hashlib.sha256(_canonical(bundle.content)).hexdigest()
    if not hmac.compare_digest(bundle.signature, expected) or actual_digest != bundle.digest:
        raise ValueError("Policy bundle signature verification failed")
    db.query(models.PolicyBundle).filter_by(tenant_id=bundle.tenant_id, state="active").update(
        {models.PolicyBundle.state: "retired"}, synchronize_session=False)
    bundle.state = "active"
    bundle.activated_at = datetime.now(timezone.utc)
    return bundle
