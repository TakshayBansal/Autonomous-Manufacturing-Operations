from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.scm.bom import BOMComponent, BOMCycleError, explode_bom
from app.scm.engine import (PlanningEvent, PlanningPolicy, aggregate_points,
                            excess_windows, plan_material, shortage_windows)
from app.scm.risks import _drivers


def event(event_id: str, at: date, quantity: str, *, priority: int = 100) -> PlanningEvent:
    return PlanningEvent(event_id, "TEST", at, Decimal(quantity), "fixture", event_id, priority=priority)


def test_projection_stockout_recovery_pegging_and_pull_in_are_deterministic():
    as_of = date(2026, 8, 20)
    events = [
        event("D1", as_of + timedelta(days=1), "-10"),
        event("D2", as_of + timedelta(days=2), "-10"),
        event("D3", as_of + timedelta(days=3), "-10"),
        event("D4", as_of + timedelta(days=4), "-10"),
        event("S1", as_of + timedelta(days=5), "20"),
    ]
    result = plan_material(as_of=as_of, opening_available=Decimal("30"), events=events, policy=PlanningPolicy(horizon_days=7))
    repeated = plan_material(as_of=as_of, opening_available=Decimal("30"), events=events, policy=PlanningPolicy(horizon_days=7))
    assert result == repeated
    assert result.stockout_date == as_of + timedelta(days=3)
    assert result.peak_shortage_qty == Decimal("10")
    assert result.recovery_date == as_of + timedelta(days=5)
    assert result.recommendations[0].action_type == "PULL_IN"
    assert sum(peg.quantity for peg in result.pegs) == Decimal("40")


def test_stale_source_suppresses_confident_risk_and_actions():
    as_of = date(2026, 8, 20)
    result = plan_material(
        as_of=as_of, opening_available=Decimal("0"),
        events=[event("D1", as_of + timedelta(days=1), "-10")],
        policy=PlanningPolicy(horizon_days=3), stale=True,
    )
    assert result.severity == "UNKNOWN"
    assert result.recommendations == ()
    assert all(point.risk_status == "UNKNOWN" for point in result.points)


def test_new_buy_rounds_to_moq_and_order_multiple():
    as_of = date(2026, 8, 20)
    result = plan_material(
        as_of=as_of, opening_available=Decimal("1"),
        events=[event("D1", as_of + timedelta(days=1), "-1101")],
        policy=PlanningPolicy(horizon_days=3, minimum_order_qty=Decimal("1000"), order_multiple=Decimal("500")),
    )
    assert result.recommendations[0].action_type == "NEW_BUY"
    assert result.recommendations[0].quantity == Decimal("1500")


def test_daily_points_aggregate_without_hiding_worst_risk():
    as_of = date(2026, 8, 20)
    result = plan_material(
        as_of=as_of, opening_available=Decimal("10"),
        events=[event("D1", as_of + timedelta(days=1), "-12"), event("S1", as_of + timedelta(days=2), "5")],
        policy=PlanningPolicy(horizon_days=10),
    )
    weekly = aggregate_points(result.points, "weekly")
    assert sum(point.demand_qty for point in weekly) == Decimal("12")
    assert any(point.risk_status == "RED" for point in weekly)


def test_nested_bom_retains_lineage_and_rejects_cycle():
    tree = {
        "FG": [BOMComponent("SUB", Decimal("2"))],
        "SUB": [BOMComponent("C", Decimal("3"), Decimal("0.1"))],
    }
    exploded = explode_bom("FG", Decimal("10"), date(2026, 8, 20), "P1", lambda key, *_: tree.get(key, []))
    assert exploded[0].material_id == "C"
    assert exploded[0].quantity == Decimal("66.0")
    assert exploded[0].path == ("FG", "SUB", "C")

    cyclic = {"A": [BOMComponent("B", Decimal("1"))], "B": [BOMComponent("A", Decimal("1"))]}
    with pytest.raises(BOMCycleError, match="A -> B -> A"):
        explode_bom("A", Decimal("1"), date(2026, 8, 20), "P1", lambda key, *_: cyclic.get(key, []))


def test_shortage_days_collapse_into_one_recoverable_window():
    as_of = date(2026, 8, 20)
    result = plan_material(as_of=as_of, opening_available=Decimal("30"), events=[
        event("D1", as_of + timedelta(days=1), "-10"),
        event("D2", as_of + timedelta(days=2), "-10"),
        event("D3", as_of + timedelta(days=3), "-20"),
        event("S1", as_of + timedelta(days=6), "20"),
    ], policy=PlanningPolicy(horizon_days=10))
    windows = shortage_windows(result.points)
    assert len(windows) == 1
    assert windows[0].start_date == as_of + timedelta(days=3)
    assert windows[0].end_date == as_of + timedelta(days=5)
    assert windows[0].recovery_date == as_of + timedelta(days=6)
    assert windows[0].peak_quantity == Decimal("10")


def test_excess_requires_a_sustained_inventory_window():
    as_of = date(2026, 8, 20)
    result = plan_material(as_of=as_of, opening_available=Decimal("100"), events=[],
                           policy=PlanningPolicy(horizon_days=4))
    windows = excess_windows(result.points, maximum_inventory=Decimal("50"), minimum_duration_days=2)
    assert len(windows) == 1
    assert windows[0].duration_days == 4
    assert windows[0].peak_quantity == Decimal("50")


def test_risk_delta_accepts_manual_supply_without_purchase_order_identity():
    previous = {"opening_available": "100", "demands": [], "supplies": [
        {"id": "manual-entry-1", "date": "2026-08-30", "quantity": "500"}]}
    current = {"opening_available": "100", "demands": [], "supplies": [
        {"id": "manual-entry-1", "date": "2026-08-28", "quantity": "500",
         "canonical_purchase_order_id": None}]}
    assert _drivers(current, previous) == [{"type": "PO_DATE_CHANGE", "entity_id": "manual-entry-1",
        "old_date": "2026-08-30", "new_date": "2026-08-28"}]
