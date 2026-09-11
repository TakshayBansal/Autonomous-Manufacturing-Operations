from datetime import date, timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db import models
from app.db.seed import reset_workspace_database
from app.db.session import SessionLocal
from app.core.config import get_settings
from app import documents
from app.documents import _groq_extract_quote
from app.quotation_intake import accept_intake, apply_extraction_to_intake


@pytest.fixture(autouse=True)
def reset_workspace():
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.commit()


def _manager(db):
    return db.query(models.User).filter_by(email="purchase.manager@genuinegigs.local").one()


def _open_rfq(db):
    return db.query(models.RFQ).filter(models.RFQ.supplier_ids != []).first()


def _intake(db, user, rfq):
    intake = models.QuotationIntake(
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        mode="parsed",
        status="extracting",
        rfq_id=rfq.id,
        created_by_user_id=user.id,
        extracted_fields={},
        evidence=[],
        supplier_candidates=[],
    )
    db.add(intake)
    db.flush()
    return intake


def test_document_job_is_committed_with_task_id_before_worker_dispatch(monkeypatch):
    """A fast worker must not race the API's optimistic-lock update."""
    with SessionLocal() as db:
        user = _manager(db)
        document = models.Document(
            id="DOC-enqueue-order",
            business_number="DOC-ENQUEUE-ORDER",
            tenant_id=user.tenant_id,
            plant_id=user.plant_id,
            filename="quotation.pdf",
            content_type="application/pdf",
            size_bytes=10,
            storage_key="enqueue-order/quotation.pdf",
            storage_bucket="quarantine",
            checksum_sha256="0" * 64,
            status="quarantined",
            validation_errors=[],
            uploaded_by_user_id=user.id,
        )
        job = models.DocumentJob(
            id="DJOB-enqueue-order",
            tenant_id=user.tenant_id,
            plant_id=user.plant_id,
            document_id=document.id,
            status="queued",
        )
        db.add_all([document, job])
        db.commit()

        observed = {}

        def fake_apply_async(*, args, queue, task_id):
            with SessionLocal() as worker_db:
                worker_job = worker_db.get(models.DocumentJob, args[0])
                observed.update(
                    queue=queue,
                    dispatched_task_id=task_id,
                    committed_task_id=worker_job.celery_task_id,
                )
            return SimpleNamespace(id=task_id)

        monkeypatch.setattr("app.workers.process_document.apply_async", fake_apply_async)
        queued = documents.enqueue_document_job(db, document.id)

        assert queued is not None
        assert observed["queue"] == "documents"
        assert observed["dispatched_task_id"] == observed["committed_task_id"]
        assert queued.celery_task_id == observed["committed_task_id"]


def test_extraction_resolves_exact_shortlisted_supplier_without_creating_quote():
    with SessionLocal() as db:
        user = _manager(db)
        rfq = _open_rfq(db)
        supplier = db.get(models.Supplier, rfq.supplier_ids[0])
        intake = _intake(db, user, rfq)
        before = db.query(models.SupplierQuote).count()
        extraction = models.QuoteExtractionRun(
            tenant_id=user.tenant_id,
            plant_id=user.plant_id,
            document_id=None,
            quote_id=None,
            parser_version="llamaparse@1:test+groq-structured@1",
            model_version="test",
            status="needs_review",
            evidence=[{"source": "llamaparse:markdown", "provider_job_id": "job-1"}],
            extracted_fields={"supplier_legal_name": supplier.name, "quote_number": "Q-100"},
        )
        db.add(extraction)
        db.flush()
        apply_extraction_to_intake(db, intake, extraction)
        assert intake.inferred_supplier_id == supplier.id
        assert intake.status == "needs_review"
        assert intake.provider == "llamaparse"
        assert db.query(models.SupplierQuote).count() == before


def test_accept_requires_corrections_then_creates_once():
    with SessionLocal() as db:
        user = _manager(db)
        rfq = _open_rfq(db)
        supplier = db.get(models.Supplier, rfq.supplier_ids[0])
        intake = _intake(db, user, rfq)
        intake.status = "needs_review"
        intake.inferred_supplier_id = supplier.id
        intake.parser_version = "llamaparse@1:test+groq-structured@1"
        intake.extracted_fields = {"quote_number": "Q-200"}
        with pytest.raises(HTTPException) as incomplete:
            accept_intake(db, user, intake.id, {"fields": {}})
        assert incomplete.value.status_code == 422
        fields = {
            "quote_number": "Q-200",
            "quote_date": date.today().isoformat(),
            "validity_date": (date.today() + timedelta(days=30)).isoformat(),
            "currency": "INR",
            "lines": [{"quantity": 1, "unit_price": 99, "gst_rate": 18}],
        }
        accepted, quote = accept_intake(db, user, intake.id, {"fields": fields})
        replayed, replayed_quote = accept_intake(db, user, intake.id, {"fields": fields})
        assert accepted.status == "accepted"
        assert replayed_quote.id == quote.id
        assert replayed.quote_id == quote.id


def test_groq_quote_extraction_uses_dedicated_20b_low_reasoning_and_bounded_retry(monkeypatch):
    calls = []
    valid = {
        "supplier_legal_name": "Fixture Supplier 5",
        "erp_vendor_id": None,
        "supplier_contact_email": None,
        "supplier_contact_domain": None,
        "quote_number": "Q-500",
        "quote_date": "2026-07-30",
        "validity_date": "2026-08-30",
        "payment_terms": "30 days",
        "currency": "INR",
        "lines": [],
    }

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("json_validate_failed: max completion tokens reached before generating a valid document")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(valid)))]
            )

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_quotation_extraction_model", "openai/gpt-oss-20b")
    monkeypatch.setattr(settings, "groq_quotation_extraction_max_completion_tokens", 3072)
    monkeypatch.setattr(settings, "groq_quotation_extraction_retry_max_completion_tokens", 4096)
    monkeypatch.setattr(settings, "groq_quotation_extraction_reasoning_effort", "low")
    monkeypatch.setattr("groq.Groq", FakeGroq)

    result = _groq_extract_quote("Quotation Q-500 from Fixture Supplier 5")

    assert result["supplier_legal_name"] == "Fixture Supplier 5"
    assert [call["max_completion_tokens"] for call in calls] == [3072, 4096]
    assert all(call["model"] == "openai/gpt-oss-20b" for call in calls)
    assert all(call["reasoning_effort"] == "low" for call in calls)
    assert all(call["response_format"]["json_schema"]["strict"] is True for call in calls)
    strict_schema = calls[0]["response_format"]["json_schema"]["schema"]
    assert strict_schema["required"] == list(strict_schema["properties"])
    line_schema = strict_schema["$defs"]["ExtractedQuotationLine"]
    assert line_schema["required"] == list(line_schema["properties"])
    assert line_schema["additionalProperties"] is False


def test_gemini_extraction_discovers_available_model_after_404(monkeypatch):
    valid = {
        "supplier_legal_name": "Fixture Supplier 5",
        "erp_vendor_id": None,
        "supplier_contact_email": None,
        "supplier_contact_domain": None,
        "quote_number": "Q-500",
        "quote_date": None,
        "validity_date": None,
        "payment_terms": None,
        "currency": None,
        "lines": [],
    }
    posts = []

    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = json.dumps(body)

        @property
        def is_error(self):
            return self.status_code >= 400

        def json(self):
            return self._body

        def raise_for_status(self):
            if self.is_error:
                raise RuntimeError(self.text)

    def post(url, **_kwargs):
        posts.append(url)
        if "gemini-retired" in url:
            return Response(404, {"error": {"message": "model not found"}})
        return Response(200, {
            "candidates": [{"content": {"parts": [{"text": json.dumps(valid)}]}}],
        })

    def get(_url, **_kwargs):
        return Response(200, {"models": [{
            "name": "models/gemini-current-flash",
            "supportedGenerationMethods": ["generateContent"],
        }]})

    settings = get_settings()
    monkeypatch.setattr(settings, "quotation_extraction_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_extraction_model", "gemini-retired")
    monkeypatch.setattr(documents.httpx, "post", post)
    monkeypatch.setattr(documents.httpx, "get", get)
    documents._GEMINI_MODEL_CACHE.clear()

    result = documents._gemini_structured_extract(
        "Quotation Q-500 from Fixture Supplier 5",
        documents.ExtractedQuotation,
        "Extract supplier quotation data.",
    )

    assert result["supplier_legal_name"] == "Fixture Supplier 5"
    assert "gemini-retired" in posts[0]
    assert "gemini-current-flash" in posts[1]


def test_gemini_extraction_retries_malformed_json_once(monkeypatch):
    valid = {
        "supplier_legal_name": "Fixture Supplier 6",
        "erp_vendor_id": None,
        "supplier_contact_email": None,
        "supplier_contact_domain": None,
        "quote_number": "Q-600",
        "quote_date": None,
        "validity_date": None,
        "payment_terms": None,
        "currency": "INR",
        "lines": [],
    }
    calls = []

    class Response:
        status_code = 200
        is_error = False

        def __init__(self, content):
            self.content = content
            self.text = content

        def json(self):
            return {"candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": self.content}]},
            }]}

        def raise_for_status(self):
            return None

    def post(_url, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return Response('{"supplier_legal_name": "Fixture Supplier 6", bad}')
        return Response(json.dumps(valid))

    settings = get_settings()
    monkeypatch.setattr(settings, "quotation_extraction_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_extraction_model", "gemini-test-flash")
    monkeypatch.setattr(documents.httpx, "post", post)
    documents._GEMINI_MODEL_CACHE.clear()

    result = documents._gemini_structured_extract(
        "Quotation Q-600 from Fixture Supplier 6",
        documents.ExtractedQuotation,
        "Extract supplier quotation data.",
    )

    assert result["supplier_legal_name"] == "Fixture Supplier 6"
    assert result["quote_number"] == "Q-600"
    assert len(calls) == 2
    retry_prompt = calls[1]["contents"][0]["parts"][0]["text"]
    assert "strictly valid JSON" in retry_prompt


def test_gemini_extraction_recovers_truncated_quotation_in_split_calls(monkeypatch):
    header = {
        "supplier_legal_name": "Fixture Supplier 4",
        "erp_vendor_id": "VENDOR-4",
        "supplier_contact_email": "quotes@supplier4.test",
        "supplier_contact_domain": "supplier4.test",
        "quote_number": "Q-400",
        "quote_date": "2026-07-30",
        "validity_date": None,
        "payment_terms": "Net 30",
        "currency": "INR",
    }
    lines = {"lines": [{
        "material": "Steel plate",
        "quantity": 10,
        "uom": "EA",
        "unit_price": 125,
        "gst_rate": 18,
        "freight": 0,
        "packaging": 0,
        "lead_time_days": 7,
        "promised_date": None,
        "moq": 1,
        "certificates": [],
        "deviation_notes": None,
    }]}
    calls = []

    class Response:
        status_code = 200
        is_error = False

        def __init__(self, content, finish_reason="STOP"):
            self.content = content
            self.finish_reason = finish_reason
            self.text = content

        def json(self):
            return {"candidates": [{
                "finishReason": self.finish_reason,
                "content": {"parts": [{"text": self.content}]},
            }]}

        def raise_for_status(self):
            return None

    def post(_url, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) <= 2:
            return Response('{"supplier_legal_name":"Fixture Supplier 4', "MAX_TOKENS")
        if len(calls) == 3:
            return Response(json.dumps(header))
        return Response(json.dumps(lines))

    settings = get_settings()
    monkeypatch.setattr(settings, "quotation_extraction_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_extraction_model", "gemini-test-flash")
    monkeypatch.setattr(documents.httpx, "post", post)
    documents._GEMINI_MODEL_CACHE.clear()

    result = documents._gemini_structured_extract(
        "Quotation Q-400 from Fixture Supplier 4",
        documents.ExtractedQuotation,
        "Extract supplier quotation data.",
    )

    assert result["supplier_legal_name"] == "Fixture Supplier 4"
    assert result["payment_terms"] == "Net 30"
    assert result["lines"][0]["material"] == "Steel plate"
    assert len(calls) == 4
    assert "only the quotation header" in calls[2]["contents"][0]["parts"][0]["text"]
    assert "only quotation line items" in calls[3]["contents"][0]["parts"][0]["text"]


def test_gemini_extraction_preserves_header_when_line_recovery_is_truncated(monkeypatch):
    header = {
        "supplier_legal_name": "Fixture Supplier 2",
        "erp_vendor_id": None,
        "supplier_contact_email": None,
        "supplier_contact_domain": None,
        "quote_number": "Q-200",
        "quote_date": None,
        "validity_date": None,
        "payment_terms": None,
        "currency": "INR",
    }
    calls = []

    class Response:
        status_code = 200
        is_error = False

        def __init__(self, content):
            self.content = content
            self.text = content

        def json(self):
            return {"candidates": [{
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": self.content}]},
            }]}

        def raise_for_status(self):
            return None

    def post(_url, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 3:
            return Response(json.dumps(header))
        return Response('{"lines":[{"material":"unfinished')

    settings = get_settings()
    monkeypatch.setattr(settings, "quotation_extraction_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_extraction_model", "gemini-test-flash")
    monkeypatch.setattr(documents.httpx, "post", post)
    documents._GEMINI_MODEL_CACHE.clear()

    result = documents._gemini_structured_extract(
        "Quotation Q-200 from Fixture Supplier 2",
        documents.ExtractedQuotation,
        "Extract supplier quotation data.",
    )

    assert result["supplier_legal_name"] == "Fixture Supplier 2"
    assert result["lines"] == []
    assert len(calls) == 5
