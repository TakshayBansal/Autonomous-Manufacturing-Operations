from typing import Any, Protocol

import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models


class ERPAdapterResult(dict):
    """Typed result shape for ERP adapter operations without adding a runtime dependency."""


class ERPAdapter(Protocol):
    provider: str

    def pull_master_data(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult: ...
    def pull_material_needs(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult: ...
    def pull_open_purchase_orders(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult: ...
    def push_purchase_order(self, db: Session, po: models.PODraft) -> ERPAdapterResult: ...
    def pull_purchase_order_status(self, db: Session, tenant_id: str, plant_id: str, po_draft_id: str) -> ERPAdapterResult: ...
    def push_receipt(self, db: Session, receipt: models.StoreReceipt) -> ERPAdapterResult: ...
    def pull_receipts(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult: ...
    def pull_inspections(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult: ...
    def reconcile_external_reference(self, db: Session, tenant_id: str, plant_id: str, entity_type: str, entity_id: str) -> ERPAdapterResult: ...


class LocalERPAdapter:
    provider = "local"

    def pull_master_data(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return ERPAdapterResult(
            provider=self.provider,
            mode="simulation",
            suppliers=db.query(models.Supplier).filter_by(tenant_id=tenant_id, plant_id=plant_id).all(),
            items=db.query(models.Item).filter_by(tenant_id=tenant_id, plant_id=plant_id).all(),
        )

    def pull_material_needs(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return ERPAdapterResult(
            provider=self.provider,
            mode="simulation",
            requirements=db.query(models.PurchaseRequirement).filter_by(tenant_id=tenant_id, plant_id=plant_id).all(),
        )

    def pull_open_purchase_orders(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return ERPAdapterResult(
            provider=self.provider,
            mode="simulation",
            open_pos=db.query(models.PODraft).filter_by(tenant_id=tenant_id, plant_id=plant_id).all(),
        )

    def push_purchase_order(self, db: Session, po: models.PODraft) -> ERPAdapterResult:
        return ERPAdapterResult(
            provider=self.provider,
            mode="simulation",
            status="simulated_posted",
            correlation_id=po.simulated_posting_correlation_id,
            payload=po.oracle_mapping,
        )

    def pull_purchase_order_status(self, db: Session, tenant_id: str, plant_id: str, po_draft_id: str) -> ERPAdapterResult:
        po = db.query(models.PODraft).filter_by(id=po_draft_id, tenant_id=tenant_id, plant_id=plant_id).first()
        if po is None:
            raise KeyError(f"Unknown PO draft {po_draft_id}")
        return ERPAdapterResult(provider=self.provider, mode="simulation", status=po.status, correlation_id=po.simulated_posting_correlation_id)

    def push_receipt(self, db: Session, receipt: models.StoreReceipt) -> ERPAdapterResult:
        return ERPAdapterResult(provider=self.provider, mode="simulation", status="receipt_simulated", payload={"receipt_id": receipt.id, "quantity": receipt.received_quantity})

    def pull_receipts(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return ERPAdapterResult(provider=self.provider, mode="simulation", receipts=db.query(models.StoreReceipt).filter_by(tenant_id=tenant_id, plant_id=plant_id).all())

    def pull_inspections(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return ERPAdapterResult(provider=self.provider, mode="simulation", inspections=db.query(models.InspectionResult).filter_by(tenant_id=tenant_id, plant_id=plant_id).all())

    def reconcile_external_reference(self, db: Session, tenant_id: str, plant_id: str, entity_type: str, entity_id: str) -> ERPAdapterResult:
        refs = db.query(models.IntegrationExternalReference).filter_by(tenant_id=tenant_id, plant_id=plant_id, local_entity_type=entity_type, local_entity_id=entity_id).all()
        payload: dict[str, Any] = {}
        if entity_type == "po_draft":
            po = db.query(models.PODraft).filter_by(id=entity_id, tenant_id=tenant_id, plant_id=plant_id).first()
            payload = po.oracle_mapping if po else {}
        return ERPAdapterResult(
            provider=self.provider,
            mode="simulation",
            references=[
                {"external_id": ref.external_id, "sync_status": ref.sync_status, "payload_hash": ref.last_payload_hash}
                for ref in refs
            ],
            payload=payload,
            status="reconciled" if refs else "no_external_reference",
        )

    # Backward-compatible aliases used by older routes/tests.
    def import_master_data(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return self.pull_master_data(db, tenant_id, plant_id)

    def import_open_pos(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return self.pull_open_purchase_orders(db, tenant_id, plant_id)

    def import_receipts(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return self.pull_receipts(db, tenant_id, plant_id)

    def import_inspections(self, db: Session, tenant_id: str, plant_id: str) -> ERPAdapterResult:
        return self.pull_inspections(db, tenant_id, plant_id)

    def simulate_po_posting(self, db: Session, po_draft_id: str, tenant_id: str | None = None, plant_id: str | None = None) -> ERPAdapterResult:
        query = db.query(models.PODraft).filter(models.PODraft.id == po_draft_id)
        if tenant_id:
            query = query.filter(models.PODraft.tenant_id == tenant_id)
        if plant_id:
            query = query.filter(models.PODraft.plant_id == plant_id)
        po = query.first()
        if po is None:
            raise KeyError(f"Unknown PO draft {po_draft_id}")
        return self.push_purchase_order(db, po)


class OracleFusionProcurementAdapter(LocalERPAdapter):
    provider = "oracle_fusion"
    _access_token: str | None = None
    _token_expires_at: float = 0

    def _endpoint(self, path: str) -> str:
        base_url = (get_settings().oracle_base_url or "https://oracle.example.invalid").rstrip("/")
        return f"{base_url}{path}"

    def _token(self) -> str:
        settings = get_settings()
        if self._access_token and self._token_expires_at > time.time() + 30:
            return self._access_token
        if not settings.oracle_token_url or not settings.oracle_client_id or not settings.oracle_client_secret:
            raise RuntimeError("Oracle OAuth client credentials are not configured")
        response = httpx.post(
            settings.oracle_token_url,
            data={"grant_type": "client_credentials", "scope": settings.oracle_scope or ""},
            auth=(settings.oracle_client_id, settings.oracle_client_secret),
            timeout=settings.integration_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return self._access_token

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = httpx.request(
            method,
            self._endpoint(path),
            headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"},
            timeout=get_settings().integration_timeout_seconds,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def _po_payload(self, po: models.PODraft) -> dict[str, Any]:
        settings = get_settings()
        lines = [
            {
                "ItemNumber": line.get("item_code"),
                "Quantity": line.get("quantity"),
                "UOMCode": line.get("uom"),
                "Price": line.get("unit_price"),
                "schedules": [{"NeedByDate": line.get("need_by_date"), "ShipToLocationCode": po.oracle_mapping.get("ship_to_location")}],
            }
            for line in po.oracle_mapping.get("lines", [])
        ]
        return {
            "ProcurementBU": settings.oracle_procurement_bu,
            "RequisitioningBU": settings.oracle_requisitioning_bu,
            "Supplier": po.oracle_mapping.get("supplier_name"),
            "SupplierSite": po.oracle_mapping.get("supplier_site"),
            "CurrencyCode": po.currency,
            "PaymentTerms": po.payment_terms,
            "RequiredAcknowledgmentCode": "D",
            "lines": lines,
        }

    def push_purchase_order(self, db: Session, po: models.PODraft) -> ERPAdapterResult:
        settings = get_settings()
        payload = self._po_payload(po)
        if settings.erp_write_mode != "live":
            return ERPAdapterResult(provider=self.provider, mode=settings.erp_write_mode, status="prepared_no_write", payload=payload)
        if not settings.erp_live_enabled:
            raise RuntimeError("Oracle live dispatch is disabled by ERP_LIVE_ENABLED")
        created = self._request("POST", "/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders", json=payload).json()
        external_id = str(created.get("draftPurchaseOrdersUniqID") or created.get("PoHeaderId") or created.get("OrderNumber"))
        if not external_id or external_id == "None":
            raise RuntimeError("Oracle did not return a draft purchase order identifier")
        action_path = f"/fscmRestApi/resources/11.13.18.05/draftPurchaseOrders/{external_id}/action"
        validation = self._request("POST", f"{action_path}/validateDocument", json={}).json()
        submitted = self._request("POST", f"{action_path}/submit", json={}).json()
        return ERPAdapterResult(provider=self.provider, mode="live", status="submitted", external_id=external_id, payload=payload, validation=validation, response=submitted)

    def pull_purchase_order_status(self, db: Session, tenant_id: str, plant_id: str, po_draft_id: str) -> ERPAdapterResult:
        ref = db.query(models.IntegrationExternalReference).filter_by(tenant_id=tenant_id, plant_id=plant_id, local_entity_type="po_draft", local_entity_id=po_draft_id, provider=self.provider).first()
        if ref is None:
            return ERPAdapterResult(provider=self.provider, status="no_external_reference")
        response = self._request("GET", f"/fscmRestApi/resources/11.13.18.05/purchaseOrders/{ref.external_id}")
        return ERPAdapterResult(provider=self.provider, status="retrieved", external_id=ref.external_id, payload=response.json())

    def push_receipt(self, db: Session, receipt: models.StoreReceipt) -> ERPAdapterResult:
        settings = get_settings()
        payload = {"ReceiptSourceCode": "VENDOR", "lines": [{"DocumentNumber": receipt.po_draft_id, "Quantity": receipt.received_quantity}]}
        if settings.erp_write_mode != "live":
            return ERPAdapterResult(provider=self.provider, mode=settings.erp_write_mode, status="prepared_no_write", payload=payload)
        if not settings.erp_live_enabled:
            raise RuntimeError("Oracle live dispatch is disabled by ERP_LIVE_ENABLED")
        body = self._request("POST", settings.oracle_receipt_resource, json=payload).json()
        return ERPAdapterResult(provider=self.provider, mode="live", status="submitted", external_id=str(body.get("ReceiptHeaderId") or body.get("ReceiptNumber")), payload=payload, response=body)

    def reconcile_external_reference(self, db: Session, tenant_id: str, plant_id: str, entity_type: str, entity_id: str) -> ERPAdapterResult:
        if entity_type == "po_draft":
            return self.pull_purchase_order_status(db, tenant_id, plant_id, entity_id)
        return super().reconcile_external_reference(db, tenant_id, plant_id, entity_type, entity_id)


class SapS4HanaAdapter(LocalERPAdapter):
    provider = "sap_s4hana"

    def _endpoint(self, service: str) -> str:
        base_url = (get_settings().sap_base_url or "https://sap.example.invalid").rstrip("/")
        return f"{base_url}/sap/opu/odata/sap/{service}"

    def push_purchase_order(self, db: Session, po: models.PODraft) -> ERPAdapterResult:
        return ERPAdapterResult(
            provider=self.provider,
            mode=get_settings().erp_write_mode,
            status="contract_only",
            purchase_order_endpoint=self._endpoint("API_PURCHASEORDER_PROCESS_SRV"),
            purchase_requisition_endpoint=self._endpoint("API_PURCHASEREQ_PROCESS_SRV"),
            material_document_endpoint=self._endpoint("API_MATERIAL_DOCUMENT_SRV"),
            correlation_id=po.simulated_posting_correlation_id,
            payload={"PurchaseOrder": po.oracle_mapping},
        )


def get_erp_adapter(provider: str | None = None) -> ERPAdapter:
    selected = (provider or get_settings().erp_provider or "local").lower()
    if selected in {"oracle", "oracle_fusion"}:
        return OracleFusionProcurementAdapter()
    if selected in {"sap", "sap_s4hana"}:
        return SapS4HanaAdapter()
    return LocalERPAdapter()


erp_adapter = get_erp_adapter()
