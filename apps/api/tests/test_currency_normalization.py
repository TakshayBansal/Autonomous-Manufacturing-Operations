from datetime import datetime, timezone

import pytest

from app import agent_service, currency_service
from app.agent_schemas import AgentMessageRequest, IntentEnvelope, ThreadCreateRequest
from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.domains import workflows


@pytest.fixture(autouse=True)
def reset_workspace() -> None:
    with SessionLocal() as db:
        reset_workspace_database(db); db.commit()


def test_foreign_quote_cannot_influence_recommendation_without_sourced_rate() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="purchase.manager@genuinegigs.local").one()
        quote = db.query(models.SupplierQuote).filter_by(verification_status="verified").first()
        assert quote is not None
        quote.currency = "USD"; quote.exchange_rate_to_inr = 1; quote.exchange_rate_observation_id = None
        db.flush()
        rows = workflows.compare_quotes(db, quote.rfq_id, user)
        row = next(item for item in rows if item.quote_id == quote.id)
        assert row.disqualified is True
        assert "lacks verified source evidence" in " ".join(row.reasons)

        observation = currency_service.record_rate(db, user, {
            "source_currency": "USD", "target_currency": "INR", "rate": 83.25,
            "source_name": "Customer treasury daily rate", "source_reference": "FX-2026-07-22",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
        currency_service.apply_rate(db, user, quote.id, observation.id); db.flush()
        rows = workflows.compare_quotes(db, quote.rfq_id, user)
        normalized = next(item for item in rows if item.quote_id == quote.id)
        assert "lacks verified source evidence" not in " ".join(normalized.reasons)
        line = db.query(models.QuoteLine).filter_by(id=normalized.quote_line_id).one()
        assert normalized.total_net_landed_cost == round(workflows.landed_cost_breakdown(line)["total_net_landed_cost"] * 83.25, 2)
        assert quote.exchange_rate_to_inr == 83.25
        assert db.query(models.AuditEvent).filter_by(action="quote.exchange_rate_verified", entity_id=quote.id).one()


def test_rate_currency_must_match_quote() -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="purchase.manager@genuinegigs.local").one()
        quote = db.query(models.SupplierQuote).first(); quote.currency = "EUR"
        observation = currency_service.record_rate(db, user, {
            "source_currency": "USD", "rate": 83, "source_name": "Treasury",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
        with pytest.raises(Exception) as mismatch:
            currency_service.apply_rate(db, user, quote.id, observation.id)
        assert getattr(mismatch.value, "status_code", None) == 422


def test_agent_records_then_applies_sourced_rate_as_separate_mutations(monkeypatch) -> None:
    with SessionLocal() as db:
        user = db.query(models.User).filter_by(email="purchase.manager@genuinegigs.local").one()
        quote = db.query(models.SupplierQuote).first(); quote.currency = "USD"; db.flush()
        thread = agent_service.create_thread(db, user, ThreadCreateRequest(thread_type="personal", title="FX evidence")); db.flush()
        observed_at = datetime.now(timezone.utc).isoformat()
        monkeypatch.setattr(agent_service, "provider_response", lambda *_args, **_kwargs: (
            IntentEnvelope(intent="record_exchange_rate", requested_outcome="Record treasury rate", entities={"source_currency": "USD", "rate": 83.5, "source_name": "Treasury", "source_reference": "FX-42", "observed_at": observed_at}, confidence=1), "groq", "test-model", None,
        ))
        first_run, first_message = agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="Record USD rate 83.5 from Treasury reference FX-42"))
        observation = db.query(models.ExchangeRateObservation).one()
        assert observation.rate == 83.5 and "recorded sourced" in first_message.content.casefold()
        assert db.query(models.AgentActionReceipt).filter_by(run_id=first_run.id).count() == 1

        monkeypatch.setattr(agent_service, "provider_response", lambda *_args, **_kwargs: (
            IntentEnvelope(intent="apply_exchange_rate", requested_outcome="Apply rate", entities={"quote_id": quote.id, "observation_id": observation.id}, confidence=1), "groq", "test-model", None,
        ))
        second_run, _message = agent_service.run_message(db, user, thread.id, AgentMessageRequest(content="Apply that sourced rate to the quotation"))
        assert quote.exchange_rate_observation_id == observation.id
        assert db.query(models.AgentActionReceipt).filter_by(run_id=second_run.id).count() == 1
