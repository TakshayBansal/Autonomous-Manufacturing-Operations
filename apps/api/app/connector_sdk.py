"""Provider-neutral, safe connector contract.

Connectors translate approved canonical operations. They never authorize users,
mutate procurement records, or receive database/session/model credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import replace
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ConnectorMode(StrEnum):
    DISCONNECTED = "disconnected"
    READ_ONLY = "read_only"
    SIMULATION = "simulation"
    SHADOW = "shadow"
    UAT = "uat"
    LIMITED_WRITE = "limited_production_write"
    PRODUCTION_WRITE = "production_write"


READ_CAPABILITIES = frozenset({
    "read_materials", "read_suppliers", "read_requirements", "read_purchase_orders",
    "read_receipts", "read_quality", "read_acknowledgements", "read_invoices", "read_payment_status",
    "read_production_plan", "read_production_actual", "read_downtime",
    "read_inventory", "read_supplier_commitments", "read_inspections",
    "read_machine_events", "read_maintenance_work",
    "read_business_events", "read_boms", "read_forecasts", "read_customer_usage",
})
WRITE_CAPABILITIES = frozenset({
    "create_requisition_draft", "create_rfq_draft", "create_purchase_order_draft",
    "attach_document", "write_receipt", "export_reconciliation",
})


@dataclass(frozen=True)
class ConnectorManifest:
    provider: str
    adapter_version: str
    display_name: str
    capabilities: frozenset[str]
    tested_capabilities: frozenset[str]
    protocols: tuple[str, ...]
    live_customer_verified: bool = False

    def __post_init__(self) -> None:
        unknown = self.capabilities - (READ_CAPABILITIES | WRITE_CAPABILITIES)
        if unknown:
            raise ValueError(f"Unknown connector capabilities: {sorted(unknown)}")
        if not self.tested_capabilities <= self.capabilities:
            raise ValueError("Tested capabilities must be declared capabilities")


@dataclass(frozen=True)
class ConnectorContext:
    connection_id: str
    tenant_id: str
    plant_id: str | None
    mode: ConnectorMode
    enabled_capabilities: frozenset[str]
    writes_enabled: bool = False
    secret_ref: str | None = None


@dataclass(frozen=True)
class PreparedWrite:
    provider: str
    capability: str
    external_key: str
    payload: dict[str, Any]
    payload_hash: str
    idempotency_key: str
    expected_external_version: str | None = None
    warnings: tuple[str, ...] = ()
    approval_reference: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    status: str
    external_id: str | None = None
    external_version: str | None = None
    acknowledgement: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    status: str
    external_id: str
    payload_hash_matches: bool
    evidence: dict[str, Any] = field(default_factory=dict)


def canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class Connector(Protocol):
    manifest: ConnectorManifest

    def test_connection(self, context: ConnectorContext) -> dict[str, Any]: ...
    def pull(self, context: ConnectorContext, capability: str, cursor: str | None = None) -> dict[str, Any]: ...
    def prepare_write(self, context: ConnectorContext, capability: str, external_key: str, payload: dict[str, Any], idempotency_key: str, expected_external_version: str | None = None) -> PreparedWrite: ...
    def validate_write(self, context: ConnectorContext, prepared: PreparedWrite) -> dict[str, Any]: ...
    def approve_write(self, context: ConnectorContext, prepared: PreparedWrite, approval_reference: str) -> PreparedWrite: ...
    def dispatch(self, context: ConnectorContext, prepared: PreparedWrite) -> DispatchResult: ...
    def verify(self, context: ConnectorContext, prepared: PreparedWrite, result: DispatchResult) -> VerificationResult: ...
    def reconcile(self, context: ConnectorContext, prepared: PreparedWrite, result: DispatchResult) -> VerificationResult: ...
    def recover_ambiguous(self, context: ConnectorContext, prepared: PreparedWrite) -> VerificationResult: ...
    def classify_error(self, error: Exception | DispatchResult) -> dict[str, Any]: ...
    def health(self, context: ConnectorContext) -> dict[str, Any]: ...
    def capability_report(self, context: ConnectorContext) -> dict[str, Any]: ...


class ReferenceConnector:
    manifest: ConnectorManifest

    def __init__(self) -> None:
        self._records: dict[str, tuple[dict[str, Any], str]] = {}
        self._idempotency: dict[str, DispatchResult] = {}

    def _authorize(self, context: ConnectorContext, capability: str, *, write: bool = False) -> None:
        if context.mode == ConnectorMode.DISCONNECTED:
            raise RuntimeError("Connection is disabled")
        if capability not in self.manifest.tested_capabilities or capability not in context.enabled_capabilities:
            raise PermissionError(f"Connector capability is not enabled: {capability}")
        if write and (capability not in WRITE_CAPABILITIES or context.mode == ConnectorMode.READ_ONLY):
            raise PermissionError("Connection is read-only")
        if write and context.mode in {ConnectorMode.LIMITED_WRITE, ConnectorMode.PRODUCTION_WRITE} and not context.writes_enabled:
            raise PermissionError("Emergency write disable is active")

    def test_connection(self, context: ConnectorContext) -> dict[str, Any]:
        if context.mode == ConnectorMode.DISCONNECTED:
            return {"status": "disabled", "provider": self.manifest.provider}
        return {"status": "available", "provider": self.manifest.provider, "adapter_version": self.manifest.adapter_version, "tested_capabilities": sorted(self.manifest.tested_capabilities)}

    def health(self, context: ConnectorContext) -> dict[str, Any]:
        result = self.test_connection(context)
        return {**result, "mode": context.mode.value, "writes_enabled": context.writes_enabled}

    def capability_report(self, context: ConnectorContext) -> dict[str, Any]:
        return {
            "provider": self.manifest.provider,
            "adapter_version": self.manifest.adapter_version,
            "declared": sorted(self.manifest.capabilities),
            "tested": sorted(self.manifest.tested_capabilities),
            "enabled": sorted(context.enabled_capabilities & self.manifest.tested_capabilities),
            "live_customer_verified": self.manifest.live_customer_verified,
            "secret_configured": bool(context.secret_ref),
            "secret_reference": "configured" if context.secret_ref else None,
        }

    def pull(self, context: ConnectorContext, capability: str, cursor: str | None = None) -> dict[str, Any]:
        self._authorize(context, capability)
        if capability == "read_inspections" and context.tenant_id == "tenant-northstar-mobility":
            return {"records": [], "cursor": cursor, "has_more": False}
        return {"records": [], "cursor": cursor, "has_more": False}

    def prepare_write(self, context: ConnectorContext, capability: str, external_key: str, payload: dict[str, Any], idempotency_key: str, expected_external_version: str | None = None) -> PreparedWrite:
        self._authorize(context, capability, write=True)
        if not idempotency_key or not external_key:
            raise ValueError("Stable external and idempotency keys are required")
        safe_payload = json.loads(json.dumps(payload, default=str))
        return PreparedWrite(self.manifest.provider, capability, external_key, safe_payload, canonical_hash(safe_payload), idempotency_key, expected_external_version)

    def validate_write(self, context: ConnectorContext, prepared: PreparedWrite) -> dict[str, Any]:
        self._authorize(context, prepared.capability, write=True)
        current = self._records.get(prepared.external_key)
        if current and prepared.expected_external_version and current[1] != prepared.expected_external_version:
            return {"valid": False, "error_code": "stale_external_version", "current_version": current[1]}
        return {"valid": True, "payload_hash": prepared.payload_hash, "consequence": "create_or_update_external_draft"}

    def approve_write(self, context: ConnectorContext, prepared: PreparedWrite, approval_reference: str) -> PreparedWrite:
        validation = self.validate_write(context, prepared)
        if not validation["valid"]:
            raise ValueError(str(validation.get("error_code") or "write_validation_failed"))
        if not approval_reference.strip():
            raise ValueError("A persisted approval reference is required")
        return replace(prepared, approval_reference=approval_reference.strip())

    def dispatch(self, context: ConnectorContext, prepared: PreparedWrite) -> DispatchResult:
        validation = self.validate_write(context, prepared)
        if not validation["valid"]:
            return DispatchResult("conflict", error_code=str(validation["error_code"]))
        if context.mode in {ConnectorMode.UAT, ConnectorMode.LIMITED_WRITE, ConnectorMode.PRODUCTION_WRITE} and not prepared.approval_reference:
            raise PermissionError("A persisted approval is required before external dispatch")
        if prepared.idempotency_key in self._idempotency:
            return self._idempotency[prepared.idempotency_key]
        if context.mode in {ConnectorMode.SIMULATION, ConnectorMode.SHADOW}:
            result = DispatchResult("simulated", external_id=prepared.external_key, acknowledgement={"payload_hash": prepared.payload_hash})
        else:
            current = self._records.get(prepared.external_key)
            version = str(int(current[1]) + 1 if current else 1)
            self._records[prepared.external_key] = (prepared.payload, version)
            result = DispatchResult("acknowledged", external_id=prepared.external_key, external_version=version, acknowledgement={"payload_hash": prepared.payload_hash})
        self._idempotency[prepared.idempotency_key] = result
        return result

    def verify(self, context: ConnectorContext, prepared: PreparedWrite, result: DispatchResult) -> VerificationResult:
        if result.status == "simulated":
            return VerificationResult("simulated", result.external_id or prepared.external_key, result.acknowledgement.get("payload_hash") == prepared.payload_hash, {"mode": context.mode.value})
        record = self._records.get(result.external_id or "")
        matches = bool(record and canonical_hash(record[0]) == prepared.payload_hash)
        return VerificationResult("reconciled" if matches else "mismatch", result.external_id or prepared.external_key, matches, {"external_version": record[1] if record else None})

    def reconcile(self, context: ConnectorContext, prepared: PreparedWrite, result: DispatchResult) -> VerificationResult:
        return self.verify(context, prepared, result)

    def recover_ambiguous(self, context: ConnectorContext, prepared: PreparedWrite) -> VerificationResult:
        """Read external state before any retry after a timeout-after-commit."""
        self._authorize(context, prepared.capability, write=True)
        record = self._records.get(prepared.external_key)
        matches = bool(record and canonical_hash(record[0]) == prepared.payload_hash)
        return VerificationResult(
            "reconciled" if matches else "not_found",
            prepared.external_key, matches,
            {"external_version": record[1] if record else None, "retry_safe": not bool(record)},
        )

    def classify_error(self, error: Exception | DispatchResult) -> dict[str, Any]:
        if isinstance(error, DispatchResult):
            retryable = bool(error.retryable) or error.error_code in {"rate_limited", "timeout_before_commit", "temporarily_unavailable"}
            return {"retryable": retryable, "error_code": error.error_code or error.status}
        if isinstance(error, (TimeoutError, ConnectionError)):
            return {"retryable": True, "error_code": "transient_transport"}
        if isinstance(error, PermissionError):
            return {"retryable": False, "error_code": "policy_denied"}
        if isinstance(error, ValueError):
            return {"retryable": False, "error_code": "validation_failed"}
        return {"retryable": False, "error_code": "unknown_failure"}


def _manifest(provider: str, name: str, protocols: tuple[str, ...], capabilities: frozenset[str]) -> ConnectorManifest:
    return ConnectorManifest(provider, "1.0", name, capabilities, capabilities, protocols, False)


BASELINE_CAPABILITIES = frozenset({"read_materials", "read_suppliers", "read_requirements", "read_purchase_orders", "read_receipts", "read_quality", "read_invoices", "read_payment_status", "read_production_plan", "read_production_actual", "read_downtime", "read_inventory", "read_supplier_commitments", "read_inspections", "read_machine_events", "read_maintenance_work", "read_business_events", "read_boms", "read_forecasts", "read_customer_usage", "create_purchase_order_draft", "export_reconciliation"})

SYNC_JOB_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "master_data": ("read_materials", "read_suppliers"),
    "material_needs": ("read_requirements",),
    "open_purchase_orders": ("read_purchase_orders",),
    "receipts": ("read_receipts",),
    "inspections": ("read_quality",),
    "invoices": ("read_invoices",),
    "payment_status": ("read_payment_status",),
    "production_plan": ("read_production_plan",),
    "production_actual": ("read_production_actual",),
    "downtime": ("read_downtime",),
    "inventory": ("read_inventory",),
    "supplier_commitments": ("read_supplier_commitments",),
    "quality_events": ("read_inspections", "read_quality"),
    "machine_events": ("read_machine_events",),
    "maintenance_work": ("read_maintenance_work",),
    "business_events": ("read_business_events",),
    "boms": ("read_boms",),
    "forecasts": ("read_forecasts",),
    "customer_usage": ("read_customer_usage",),
}


class ExcelConnector(ReferenceConnector):
    manifest = _manifest("excel_csv", "Excel / CSV", ("xlsx", "csv", "zip_csv"), BASELINE_CAPABILITIES)


class MockERPConnector(ReferenceConnector):
    manifest = _manifest("mock_erp", "Deterministic SCM Mock ERP", ("in_process", "fixture"), BASELINE_CAPABILITIES)

    def pull(self, context: ConnectorContext, capability: str, cursor: str | None = None) -> dict[str, Any]:
        self._authorize(context, capability)
        fixtures = {
            "read_materials": [{"source_record_key": "MOCK-MAT-1", "code": "SCM-C100", "name": "Connector housing", "uom": "EA"}],
            "read_boms": [{"source_record_key": "MOCK-BOM-1", "parent_code": "SCM-FG100", "component_code": "SCM-C100", "quantity_per": 2, "uom": "EA"}],
            "read_inventory": [{"source_record_key": "MOCK-INV-1", "material_code": "SCM-C100", "available_qty": 30000, "uom": "EA"}],
            "read_forecasts": [{"source_record_key": "MOCK-FC-1", "material_code": "SCM-C100", "quantity": 48000, "uom": "EA"}],
            "read_purchase_orders": [{"source_record_key": "MOCK-PO-1", "material_code": "SCM-C100", "open_qty": 30000, "uom": "EA"}],
        }
        return {"records": fixtures.get(capability, []), "cursor": "complete", "has_more": False}


class GenericRestConnector(ReferenceConnector):
    manifest = _manifest("generic_rest", "Generic REST / OpenAPI", ("https", "openapi"), BASELINE_CAPABILITIES)


class GenericODataConnector(ReferenceConnector):
    manifest = _manifest("generic_odata", "Generic OData", ("https", "odata_v4"), BASELINE_CAPABILITIES)


class SftpFileConnector(ReferenceConnector):
    manifest = _manifest("sftp_file", "SFTP / managed file exchange", ("sftp", "csv", "xlsx"), BASELINE_CAPABILITIES)


class GenericSoapConnector(ReferenceConnector):
    manifest = _manifest("generic_soap", "Generic SOAP service", ("https", "soap_1_2", "wsdl"), BASELINE_CAPABILITIES)


class IpaasConnector(ReferenceConnector):
    manifest = _manifest("ipaas", "Middleware / iPaaS adapter", ("https", "signed_webhook", "managed_queue"), BASELINE_CAPABILITIES)


class PrivateBridgeConnector(ReferenceConnector):
    manifest = _manifest("private_bridge", "Customer-hosted private bridge", ("mutual_tls", "signed_envelope"), BASELINE_CAPABILITIES)


class FactorySimulatorConnector(ReferenceConnector):
    # The baseline contract keeps the connector compatible with the scheduler's
    # common master/procurement jobs; factory capabilities use live cursor streams.
    manifest = _manifest("factory_simulator", "Northstar Factory Simulator", ("https", "cursor_stream"), BASELINE_CAPABILITIES)
    _streams = {
        "read_production_plan": "production", "read_production_actual": "production", "read_downtime": "downtime",
        "read_inventory": "inventory", "read_supplier_commitments": "supplier_commitments", "read_quality": "quality",
        "read_inspections": "quality", "read_machine_events": "machine_events", "read_maintenance_work": "maintenance",
        "read_business_events": "business",
    }

    def _request(self, path: str) -> dict[str, Any]:
        base = os.getenv("FACTORY_SIMULATOR_URL", "http://factory-simulator:8090").rstrip("/")
        token = os.getenv("FACTORY_SIMULATOR_TOKEN", "northstar-local-simulator-token")
        request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def test_connection(self, context: ConnectorContext) -> dict[str, Any]:
        if context.mode == ConnectorMode.DISCONNECTED or context.tenant_id != "tenant-northstar-mobility":
            return super().test_connection(context)
        self._authorize(context, next(iter(context.enabled_capabilities)))
        state = self._request("/sim/v1/state")
        return {"status": "available", "provider": self.manifest.provider, "scenario_time": state["scenario_time"]}

    def pull(self, context: ConnectorContext, capability: str, cursor: str | None = None) -> dict[str, Any]:
        self._authorize(context, capability)
        if capability not in self._streams or context.tenant_id != "tenant-northstar-mobility":
            return super().pull(context, capability, cursor)
        payload = self._request(f"/sim/v1/streams/{self._streams[capability]}?cursor={cursor or '0'}")
        records = []
        for envelope in payload.get("records", []):
            record = dict(envelope.get("payload") or {})
            record.setdefault("occurred_at", envelope.get("occurred_at"))
            record.setdefault("recorded_at", envelope.get("occurred_at"))
            record["source_record_key"] = envelope.get("event_id")
            records.append(record)
        return {"records": records, "cursor": payload.get("next_cursor", cursor), "has_more": len(records) >= 500}


def _unverified_manifest(provider: str, name: str, protocols: tuple[str, ...], capabilities: frozenset[str]) -> ConnectorManifest:
    return ConnectorManifest(provider, "0.1-contract", name, capabilities, frozenset(), protocols, False)


class UnverifiedVendorConnector(ReferenceConnector):
    def test_connection(self, context: ConnectorContext) -> dict[str, Any]:
        return {
            "status": "customer_validation_required", "provider": self.manifest.provider,
            "adapter_version": self.manifest.adapter_version, "tested_capabilities": [],
        }


class OracleFusionConnector(UnverifiedVendorConnector):
    manifest = _unverified_manifest(
        "oracle_fusion", "Oracle Fusion Procurement", ("https", "oracle_rest"),
        frozenset({"read_materials", "read_suppliers", "read_purchase_orders", "read_receipts", "create_purchase_order_draft", "attach_document"}),
    )


class SapS4HanaConnector(UnverifiedVendorConnector):
    manifest = _unverified_manifest(
        "sap_s4hana", "SAP S/4HANA Procurement", ("https", "odata", "idoc_bapi_boundary"),
        frozenset({"read_materials", "read_suppliers", "read_purchase_orders", "read_receipts", "create_requisition_draft", "create_purchase_order_draft"}),
    )


class Dynamics365Connector(UnverifiedVendorConnector):
    manifest = _unverified_manifest(
        "dynamics_365", "Microsoft Dynamics 365", ("https", "odata"),
        frozenset({"read_materials", "read_suppliers", "read_purchase_orders", "read_receipts", "create_purchase_order_draft"}),
    )


class OdooConnector(UnverifiedVendorConnector):
    manifest = _unverified_manifest(
        "odoo", "Odoo Purchase", ("https", "json_rpc"),
        frozenset({"read_materials", "read_suppliers", "read_purchase_orders", "read_receipts", "create_purchase_order_draft"}),
    )


CONNECTOR_REGISTRY: dict[str, type[ReferenceConnector]] = {
    connector.manifest.provider: connector for connector in (
        ExcelConnector, GenericRestConnector, GenericODataConnector, SftpFileConnector,
        GenericSoapConnector, IpaasConnector,
        PrivateBridgeConnector, OracleFusionConnector, SapS4HanaConnector,
        Dynamics365Connector, OdooConnector, FactorySimulatorConnector, MockERPConnector,
    )
}


def get_connector(provider: str) -> ReferenceConnector:
    try:
        return CONNECTOR_REGISTRY[provider]()
    except KeyError as exc:
        raise KeyError(f"Unknown connector provider: {provider}") from exc


def registry_manifests() -> list[ConnectorManifest]:
    return [connector.manifest for connector in CONNECTOR_REGISTRY.values()]


def run_conformance_report() -> dict[str, Any]:
    """Execute the safe provider-neutral acceptance matrix against every reference adapter."""
    adapters: list[dict[str, Any]] = []
    for provider in sorted(CONNECTOR_REGISTRY):
        connector = get_connector(provider)
        capabilities = connector.manifest.tested_capabilities
        if not capabilities:
            adapters.append({
                "provider": provider, "adapter_version": connector.manifest.adapter_version,
                "live_customer_verified": False, "tested_capabilities": [], "checks": {},
                "passed": None, "status": "customer_validation_required",
            })
            continue
        simulation = ConnectorContext(
            connection_id=f"conformance:{provider}", tenant_id="conformance", plant_id="fixture",
            mode=ConnectorMode.SIMULATION, enabled_capabilities=capabilities,
        )
        connection = connector.test_connection(simulation)
        pull = connector.pull(simulation, "read_materials")
        prepared = connector.prepare_write(
            simulation, "create_purchase_order_draft", "PO-CONFORMANCE-1",
            {"business_number": "PO-CONFORMANCE-1", "amount": 1250, "currency": "INR"},
            f"{provider}:PO-CONFORMANCE-1:v1",
        )
        validation = connector.validate_write(simulation, prepared)
        first = connector.dispatch(simulation, prepared)
        repeated = connector.dispatch(simulation, prepared)
        verification = connector.verify(simulation, prepared, first)

        live = ConnectorContext(
            connection_id=f"conformance:{provider}:uat", tenant_id="conformance", plant_id="fixture",
            mode=ConnectorMode.UAT, enabled_capabilities=capabilities, writes_enabled=True,
        )
        live_write = connector.prepare_write(
            live, "create_purchase_order_draft", "PO-CONFORMANCE-2",
            {"business_number": "PO-CONFORMANCE-2", "amount": 2500, "currency": "INR"},
            f"{provider}:PO-CONFORMANCE-2:v1",
        )
        live_write = connector.approve_write(live, live_write, f"approval:{provider}:PO-CONFORMANCE-2")
        acknowledgement = connector.dispatch(live, live_write)
        reconciled = connector.verify(live, live_write, acknowledgement)
        stale = connector.prepare_write(
            live, "create_purchase_order_draft", "PO-CONFORMANCE-2",
            {"business_number": "PO-CONFORMANCE-2", "amount": 2600, "currency": "INR"},
            f"{provider}:PO-CONFORMANCE-2:stale", expected_external_version="0",
        )
        stale_result = connector.dispatch(live, stale)
        disabled = ConnectorContext(
            connection_id=f"conformance:{provider}:disabled", tenant_id="conformance", plant_id="fixture",
            mode=ConnectorMode.LIMITED_WRITE, enabled_capabilities=capabilities, writes_enabled=False,
        )
        emergency_disable_blocked = False
        try:
            connector.prepare_write(
                disabled, "create_purchase_order_draft", "PO-CONFORMANCE-3", {},
                f"{provider}:PO-CONFORMANCE-3:v1",
            )
        except PermissionError:
            emergency_disable_blocked = True
        checks = {
            "connection_available": connection.get("status") == "available",
            "incremental_pull_contract": pull.get("has_more") is False and "cursor" in pull,
            "write_validation": validation.get("valid") is True,
            "simulation_no_external_effect": first.status == "simulated",
            "semantic_idempotency": first == repeated,
            "simulation_verification": verification.status == "simulated" and verification.payload_hash_matches,
            "uat_acknowledged": acknowledgement.status == "acknowledged",
            "read_after_write_reconciled": reconciled.status == "reconciled" and reconciled.payload_hash_matches,
            "ambiguous_commit_recovery": connector.recover_ambiguous(live, live_write).status == "reconciled",
            "retry_classification": connector.classify_error(TimeoutError())["retryable"] is True and connector.classify_error(ValueError())["retryable"] is False,
            "capability_report_redacts_secret": "secret_ref" not in connector.capability_report(live),
            "stale_version_blocked": stale_result.status == "conflict" and stale_result.error_code == "stale_external_version",
            "emergency_write_disable": emergency_disable_blocked,
        }
        adapters.append({
            "provider": provider, "adapter_version": connector.manifest.adapter_version,
            "live_customer_verified": connector.manifest.live_customer_verified,
            "tested_capabilities": sorted(capabilities), "checks": checks, "passed": all(checks.values()),
        })
    return {
        "suite_version": "1.0", "status": "passed" if all(row["passed"] for row in adapters if row["passed"] is not None) else "failed",
        "adapters": adapters,
        "claim_boundary": "Reference conformance only; customer credentials and UAT acceptance remain required.",
    }
