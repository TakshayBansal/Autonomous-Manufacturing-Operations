import json
from statistics import quantiles
from time import perf_counter

from app.operations import service as operational_v2
from app.db import models
from app.db.seed import PLANT_ID, TENANT_ID, reset_workspace_database
from app.db.session import SessionLocal


SERVICE_P95_BUDGET_MS = 250
JSON_PAYLOAD_BUDGET_BYTES = 512 * 1024


def _measure(call, runs: int = 20) -> tuple[float, int]:
    durations = []
    payload_size = 0
    for _ in range(runs):
        started = perf_counter()
        payload = call()
        durations.append((perf_counter() - started) * 1000)
        payload_size = max(payload_size, len(json.dumps(payload, default=str).encode()))
    return quantiles(durations, n=20)[18], payload_size


def test_flagship_v2_read_models_stay_inside_local_latency_and_payload_budgets():
    with SessionLocal() as db:
        reset_workspace_database(db)
        db.flush()
        user = db.get(models.User, "usr-plant-001")
        scenarios = {
            "command_center": lambda: operational_v2.command_center(db, TENANT_ID, PLANT_ID),
            "quality": lambda: operational_v2.quality_workspace(db, TENANT_ID, PLANT_ID),
            "corporate": lambda: operational_v2.multi_plant_workspace(db, TENANT_ID),
            "knowledge": lambda: operational_v2.knowledge_workspace(db, user, query="fault 701 BR-28"),
        }
        evidence = {name: _measure(call) for name, call in scenarios.items()}
        print({name: {"p95_ms": round(p95, 2), "max_payload_bytes": size}
               for name, (p95, size) in evidence.items()})
        assert {name: round(p95, 2) for name, (p95, _) in evidence.items()} == {
            name: round(p95, 2) for name, (p95, _) in evidence.items()
            if p95 < SERVICE_P95_BUDGET_MS
        }, evidence
        assert all(size < JSON_PAYLOAD_BUDGET_BYTES for _, size in evidence.values()), evidence
