from typing import Any

import pytest

from app.core.config import get_settings
from app.db import models
from app.erp import OracleFusionProcurementAdapter, SapS4HanaAdapter
from app.domains.workflows import payload_hash


def po() -> models.PODraft:
    return models.PODraft(
        id="00000000-0000-4000-8000-000000000001",
        tenant_id="tenant-apex",
        plant_id="plant-pune-01",
        award_id="award",
        supplier_id="supplier",
        supplier_site_id=None,
        currency="INR",
        payment_terms="30 days",
        status="approved_pending_outbox",
        oracle_mapping={
            "supplier_name": "Apex Alloy Works",
            "supplier_site": "Pune",
            "ship_to_location": "PUNE-01",
            "lines": [
                {
                    "item_code": "SLEEVE-A",
                    "quantity": 10,
                    "uom": "KG",
                    "unit_price": 120,
                    "need_by_date": "2026-07-20",
                }
            ],
        },
    )


def test_payload_hash_accepts_canonical_structured_po_mapping() -> None:
    first = payload_hash({"lines": [{"quantity": 10}], "supplier": "SUP-1"})
    second = payload_hash({"supplier": "SUP-1", "lines": [{"quantity": 10}]})
    assert first == second
    assert len(first) == 24


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


def test_oracle_live_dispatch_uses_official_draft_validate_submit_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "erp_write_mode", "live")
    monkeypatch.setattr(settings, "erp_live_enabled", True)
    monkeypatch.setattr(settings, "oracle_procurement_bu", "Pune Procurement")
    monkeypatch.setattr(settings, "oracle_requisitioning_bu", "Pune Manufacturing")
    adapter = OracleFusionProcurementAdapter()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> FakeResponse:
        calls.append((method, path, kwargs.get("json", {})))
        if path.endswith("draftPurchaseOrders"):
            return FakeResponse({"draftPurchaseOrdersUniqID": "300100999"})
        if path.endswith("validateDocument"):
            return FakeResponse({"Result": "SUCCESS"})
        return FakeResponse({"OrderNumber": "PO-9001"})

    monkeypatch.setattr(adapter, "_request", request)
    result = adapter.push_purchase_order(None, po())  # type: ignore[arg-type]

    assert [path for _method, path, _body in calls] == [
        "/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders",
        "/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders/300100999/action/validateDocument",
        "/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders/300100999/action/submit",
    ]
    assert calls[0][2]["lines"][0]["schedules"][0]["ShipToLocationCode"] == "PUNE-01"
    assert result["external_id"] == "300100999"


def test_oracle_kill_switch_blocks_live_write(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "erp_write_mode", "live")
    monkeypatch.setattr(settings, "erp_live_enabled", False)
    with pytest.raises(RuntimeError, match="ERP_LIVE_ENABLED"):
        OracleFusionProcurementAdapter().push_purchase_order(None, po())  # type: ignore[arg-type]


def test_oracle_read_only_prepares_payload_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "erp_write_mode", "read_only")
    monkeypatch.setattr(settings, "erp_live_enabled", True)
    adapter = OracleFusionProcurementAdapter()
    monkeypatch.setattr(adapter, "_request", lambda *_args, **_kwargs: pytest.fail("HTTP must not run"))
    result = adapter.push_purchase_order(None, po())  # type: ignore[arg-type]
    assert result["status"] == "prepared_no_write"


def test_sap_adapter_exposes_contract_tested_odata_services() -> None:
    result = SapS4HanaAdapter().push_purchase_order(None, po())  # type: ignore[arg-type]
    assert result["status"] == "contract_only"
    assert result["purchase_order_endpoint"].endswith("API_PURCHASEORDER_PROCESS_SRV")
    assert result["purchase_requisition_endpoint"].endswith("API_PURCHASEREQ_PROCESS_SRV")
    assert result["material_document_endpoint"].endswith("API_MATERIAL_DOCUMENT_SRV")
