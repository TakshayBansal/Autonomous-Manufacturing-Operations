"""Small shared simulation envelope; domain engines retain their algorithms."""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.platform.models import PlatformScenarioDefinition, PlatformSimulationRun


def define_scenario(db: Session, *, tenant_id: str, plant_id: str, domain: str, name: str,
                    horizon_start: datetime, horizon_end: datetime, overrides: dict,
                    baseline_snapshot_id: str | None = None, provenance: list[dict] | None = None) -> PlatformScenarioDefinition:
    if horizon_end <= horizon_start:
        raise ValueError("Simulation horizon must end after it starts")
    row = PlatformScenarioDefinition(tenant_id=tenant_id, plant_id=plant_id, domain=domain,
        name=name, baseline_snapshot_id=baseline_snapshot_id, overrides=overrides,
        horizon_start=horizon_start, horizon_end=horizon_end, provenance=provenance or [])
    db.add(row); db.flush(); return row


def run_domain_simulation(db: Session, scenario: PlatformScenarioDefinition, *, algorithm: str,
                          algorithm_version: str, correlation_id: str, inputs: dict, execute) -> PlatformSimulationRun:
    row = PlatformSimulationRun(tenant_id=scenario.tenant_id, plant_id=scenario.plant_id,
        scenario_id=scenario.id, algorithm=algorithm, algorithm_version=algorithm_version,
        status="running", inputs=inputs, correlation_id=correlation_id,
        started_at=datetime.now(timezone.utc))
    db.add(row); db.flush()
    try:
        result = execute(inputs, scenario.overrides)
        row.outputs = result.get("outputs", {})
        row.predicted_metrics = result.get("predicted_metrics", {})
        row.status = "completed"
    except Exception as exc:
        row.status = "failed"
        row.outputs = {"error": str(exc)[:2000]}
    row.completed_at = datetime.now(timezone.utc)
    return row
