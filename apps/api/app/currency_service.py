from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.permissions import ADMIN, require_role
from app.db import models
from app.domains import workflows


def record_rate(db: Session, user: models.User, payload: dict) -> models.ExchangeRateObservation:
    require_role(user, "purchase_manager", ADMIN)
    source = str(payload["source_currency"]).upper().strip()
    target = str(payload.get("target_currency") or "INR").upper().strip()
    if source == target:
        raise HTTPException(422, "Use the canonical rate of 1 for identical currencies")
    try:
        observed_at = datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Observation time must be ISO-8601") from exc
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if observed_at > datetime.now(timezone.utc):
        raise HTTPException(422, "Exchange-rate evidence cannot be future dated")
    observation = models.ExchangeRateObservation(
        business_number=workflows.next_business_number(db, "FX", user), tenant_id=user.tenant_id, plant_id=user.plant_id,
        source_currency=source, target_currency=target, rate=float(payload["rate"]), source_name=str(payload["source_name"]).strip(),
        source_reference=str(payload.get("source_reference") or "").strip(), observed_at=observed_at,
        status="verified", recorded_by_user_id=user.id,
    )
    db.add(observation); db.flush()
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "exchange_rate.recorded", "exchange_rate_observation", observation.id, actor_user_id=user.id, meta={"pair": f"{source}/{target}", "rate": observation.rate, "source": observation.source_name})
    return observation


def apply_rate(db: Session, user: models.User, quote_id: str, observation_id: str) -> models.SupplierQuote:
    require_role(user, "purchase_manager", ADMIN)
    quote = workflows.get_scoped_or_404(db, models.SupplierQuote, user, quote_id, "Supplier quotation")
    observation = workflows.get_scoped_or_404(db, models.ExchangeRateObservation, user, observation_id, "Exchange-rate evidence")
    if observation.status != "verified" or observation.source_currency != quote.currency.upper() or observation.target_currency != "INR":
        raise HTTPException(422, "Exchange-rate evidence does not match the quotation currency")
    quote.exchange_rate_to_inr = observation.rate
    quote.exchange_rate_observation_id = observation.id
    workflows.create_audit(db, user.tenant_id, user.plant_id, user.name, "quote.exchange_rate_verified", "supplier_quote", quote.id, actor_user_id=user.id, meta={"rate_observation": observation.business_number, "source": observation.source_name})
    return quote
