from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Any, Iterable


ZERO = Decimal("0")
ENGINE_VERSION = "scm-deterministic-v1"


def decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class PlanningPolicy:
    horizon_days: int = 210
    safety_stock_qty: Decimal = ZERO
    stockout_inclusive_zero: bool = True
    same_day_order: str = "DEMAND_BEFORE_SUPPLY"
    include_overdue_supply: bool = False
    maximum_coverage_days: int | None = None
    average_demand_window_days: int = 30
    planning_time_fence_days: int = 0
    cancellation_window_days: int = 0
    planned_lead_time_days: int = 0
    minimum_order_qty: Decimal = ZERO
    order_multiple: Decimal = ZERO

    @classmethod
    def from_rules(cls, rules: dict[str, Any] | None, *, safety_stock_qty: Decimal | None = None) -> "PlanningPolicy":
        rules = rules or {}
        return cls(
            horizon_days=int(rules.get("horizon_days", 210)),
            safety_stock_qty=decimal(safety_stock_qty if safety_stock_qty is not None else rules.get("safety_stock_qty", 0)),
            stockout_inclusive_zero=bool(rules.get("stockout_inclusive_zero", True)),
            same_day_order=str(rules.get("same_day_order", "DEMAND_BEFORE_SUPPLY")),
            include_overdue_supply=bool(rules.get("include_overdue_supply", False)),
            maximum_coverage_days=int(rules["maximum_coverage_days"]) if rules.get("maximum_coverage_days") is not None else None,
            average_demand_window_days=int(rules.get("average_demand_window_days", 30)),
            planning_time_fence_days=int(rules.get("planning_time_fence_days", 0)),
            cancellation_window_days=int(rules.get("cancellation_window_days", 0)),
            planned_lead_time_days=int(rules.get("planned_lead_time_days", 0)),
            minimum_order_qty=decimal(rules.get("minimum_order_qty", 0)),
            order_multiple=decimal(rules.get("order_multiple", 0)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "safety_stock_qty": str(self.safety_stock_qty),
            "stockout_inclusive_zero": self.stockout_inclusive_zero,
            "same_day_order": self.same_day_order,
            "include_overdue_supply": self.include_overdue_supply,
            "maximum_coverage_days": self.maximum_coverage_days,
            "average_demand_window_days": self.average_demand_window_days,
            "planning_time_fence_days": self.planning_time_fence_days,
            "cancellation_window_days": self.cancellation_window_days,
            "planned_lead_time_days": self.planned_lead_time_days,
            "minimum_order_qty": str(self.minimum_order_qty),
            "order_multiple": str(self.order_multiple),
        }


@dataclass(frozen=True)
class PlanningEvent:
    event_id: str
    event_type: str
    event_date: date
    quantity_delta: Decimal
    source_entity_type: str
    source_entity_id: str
    firmness: str = "FIRM"
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_supply(self) -> bool:
        return self.quantity_delta > ZERO

    @property
    def is_demand(self) -> bool:
        return self.quantity_delta < ZERO


@dataclass(frozen=True)
class ProjectionPoint:
    projection_date: date
    opening_balance: Decimal
    supply_qty: Decimal
    demand_qty: Decimal
    closing_balance: Decimal
    safety_stock_qty: Decimal
    risk_status: str


@dataclass(frozen=True)
class PlanningWindow:
    start_date: date
    end_date: date
    duration_days: int
    peak_quantity: Decimal
    recovery_date: date | None = None


@dataclass(frozen=True)
class Peg:
    supply_event_id: str
    demand_event_id: str
    quantity: Decimal
    strategy: str = "FIFO_REQUIRED_DATE"


@dataclass(frozen=True)
class Recommendation:
    action_type: str
    quantity: Decimal
    current_date: date | None
    proposed_date: date | None
    source_entity_type: str | None
    source_entity_id: str | None
    reason: str
    constraints_checked: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PlanningResult:
    points: tuple[ProjectionPoint, ...]
    first_breach_date: date | None
    stockout_date: date | None
    peak_shortage_qty: Decimal
    recovery_date: date | None
    runway_days: int | None
    average_coverage_days: Decimal | None
    projected_minimum: Decimal
    ending_balance: Decimal
    excess_qty: Decimal
    severity: str
    priority_score: Decimal
    priority_factors: dict[str, Any]
    pegs: tuple[Peg, ...]
    uncovered_demand: dict[str, Decimal]
    recommendations: tuple[Recommendation, ...]


def _event_order(event: PlanningEvent, policy: PlanningPolicy) -> tuple[date, int, int, str]:
    demand_rank = 0 if policy.same_day_order == "DEMAND_BEFORE_SUPPLY" else 1
    kind_rank = demand_rank if event.is_demand else 1 - demand_rank
    return event.event_date, kind_rank, event.priority, event.event_id


def _is_stockout(balance: Decimal, policy: PlanningPolicy) -> bool:
    return balance <= ZERO if policy.stockout_inclusive_zero else balance < ZERO


def _severity(as_of: date, breach: date | None, stockout: date | None, stale: bool) -> tuple[str, Decimal, dict[str, Any]]:
    if stale:
        return "UNKNOWN", ZERO, {"data_freshness": "stale"}
    target = stockout or breach
    if target is None:
        return "GREEN", ZERO, {"days_to_breach": None}
    days = (target - as_of).days
    if stockout is not None and days <= 7:
        severity, base = "CRITICAL", Decimal("100")
    elif stockout is not None and days <= 30:
        severity, base = "RED", Decimal("80")
    elif stockout is not None:
        severity, base = "ORANGE", Decimal("60")
    else:
        severity, base = "YELLOW", Decimal("40")
    urgency = Decimal(max(0, 30 - days))
    return severity, base + urgency, {"days_to_breach": days, "base_severity_score": str(base), "urgency_score": str(urgency)}


def _round_order(quantity: Decimal, policy: PlanningPolicy) -> Decimal:
    result = max(quantity, policy.minimum_order_qty)
    if policy.order_multiple > ZERO:
        result = (result / policy.order_multiple).to_integral_value(rounding=ROUND_CEILING) * policy.order_multiple
    return result


def fifo_pegging(opening_event: PlanningEvent, events: Iterable[PlanningEvent]) -> tuple[tuple[Peg, ...], dict[str, Decimal]]:
    supplies = [opening_event, *sorted((event for event in events if event.is_supply), key=lambda row: (row.event_date, row.firmness != "FIRM", row.event_id))]
    demands = sorted((event for event in events if event.is_demand), key=lambda row: (row.event_date, row.priority, row.event_id))
    remaining_supply = [[row, row.quantity_delta] for row in supplies]
    pegs: list[Peg] = []
    uncovered: dict[str, Decimal] = {}
    for demand in demands:
        remaining = -demand.quantity_delta
        for supply in remaining_supply:
            if remaining <= ZERO:
                break
            available = supply[1]
            if available <= ZERO:
                continue
            quantity = min(available, remaining)
            pegs.append(Peg(supply[0].event_id, demand.event_id, quantity))
            supply[1] -= quantity
            remaining -= quantity
        if remaining > ZERO:
            uncovered[demand.event_id] = remaining
    return tuple(pegs), uncovered


def plan_material(
    *,
    as_of: date,
    opening_available: Decimal,
    events: Iterable[PlanningEvent],
    policy: PlanningPolicy,
    stale: bool = False,
    opening_event_id: str = "OPENING_INVENTORY",
) -> PlanningResult:
    horizon_end = as_of + timedelta(days=policy.horizon_days - 1)
    included = [event for event in events if as_of <= event.event_date <= horizon_end]
    included.sort(key=lambda row: _event_order(row, policy))
    by_date: dict[date, list[PlanningEvent]] = {}
    for event in included:
        by_date.setdefault(event.event_date, []).append(event)

    balance = decimal(opening_available)
    minimum = balance
    first_breach: date | None = as_of if balance < policy.safety_stock_qty else None
    stockout: date | None = as_of if _is_stockout(balance, policy) else None
    recovery: date | None = None
    points: list[ProjectionPoint] = []
    current = as_of
    while current <= horizon_end:
        opening = balance
        supply = ZERO
        demand = ZERO
        for event in by_date.get(current, []):
            if event.is_supply:
                supply += event.quantity_delta
            elif event.is_demand:
                demand += -event.quantity_delta
            balance += event.quantity_delta
            minimum = min(minimum, balance)
            if first_breach is None and balance < policy.safety_stock_qty:
                first_breach = current
            if stockout is None and _is_stockout(balance, policy):
                stockout = current
            elif stockout is not None and recovery is None and balance > policy.safety_stock_qty:
                recovery = current
        if stale:
            risk = "UNKNOWN"
        elif _is_stockout(balance, policy):
            risk = "RED"
        elif balance < policy.safety_stock_qty:
            risk = "YELLOW"
        else:
            risk = "GREEN"
        points.append(ProjectionPoint(current, opening, supply, demand, balance, policy.safety_stock_qty, risk))
        current += timedelta(days=1)

    demand_window_end = as_of + timedelta(days=max(policy.average_demand_window_days - 1, 0))
    window_demand = sum((-event.quantity_delta for event in included if event.is_demand and event.event_date <= demand_window_end), ZERO)
    average_daily = window_demand / Decimal(policy.average_demand_window_days) if policy.average_demand_window_days > 0 else ZERO
    coverage = opening_available / average_daily if average_daily > ZERO else None
    max_inventory = average_daily * Decimal(policy.maximum_coverage_days) if policy.maximum_coverage_days is not None else None
    excess = max(balance - max_inventory, ZERO) if max_inventory is not None else ZERO
    severity, score, factors = _severity(as_of, first_breach, stockout, stale)
    factors.update({"peak_shortage_qty": str(max(-minimum, ZERO)), "projected_minimum": str(minimum)})

    opening_event = PlanningEvent(
        event_id=opening_event_id,
        event_type="OPENING_INVENTORY",
        event_date=as_of,
        quantity_delta=opening_available,
        source_entity_type="inventory_snapshot",
        source_entity_id="opening",
        priority=0,
    )
    pegs, uncovered = fifo_pegging(opening_event, included)
    recommendations = tuple() if stale else recommend_actions(
        as_of=as_of,
        events=included,
        policy=policy,
        stockout_date=stockout,
        peak_shortage=max(-minimum, ZERO),
        excess_qty=excess,
    )
    return PlanningResult(
        tuple(points), first_breach, stockout, max(-minimum, ZERO), recovery,
        (stockout - as_of).days if stockout else None,
        coverage, minimum, balance, excess, severity, score, factors,
        pegs, uncovered, recommendations,
    )


def shortage_windows(points: Iterable[ProjectionPoint]) -> tuple[PlanningWindow, ...]:
    """Collapse consecutive below-threshold days into one actionable window."""
    ordered = sorted(points, key=lambda row: row.projection_date)
    windows: list[PlanningWindow] = []
    active: list[ProjectionPoint] = []
    for point in ordered:
        shortage = max(point.safety_stock_qty - point.closing_balance, ZERO)
        # The planning policy treats zero available balance as stockout: there
        # is no buffer for the next consumption event even when deficit is 0.
        if point.closing_balance <= ZERO or shortage > ZERO:
            active.append(point)
            continue
        if active:
            windows.append(PlanningWindow(active[0].projection_date, active[-1].projection_date,
                len(active), max(max(active_point.safety_stock_qty - active_point.closing_balance, ZERO) for active_point in active),
                point.projection_date))
            active = []
    if active:
        windows.append(PlanningWindow(active[0].projection_date, active[-1].projection_date,
            len(active), max(max(point.safety_stock_qty - point.closing_balance, ZERO) for point in active), None))
    return tuple(windows)


def excess_windows(points: Iterable[ProjectionPoint], maximum_inventory: Decimal | None,
                   *, minimum_duration_days: int = 2) -> tuple[PlanningWindow, ...]:
    if maximum_inventory is None:
        return ()
    ordered = sorted(points, key=lambda row: row.projection_date)
    windows: list[PlanningWindow] = []
    active: list[ProjectionPoint] = []
    for point in ordered:
        if point.closing_balance > maximum_inventory:
            active.append(point)
            continue
        if len(active) >= minimum_duration_days:
            windows.append(PlanningWindow(active[0].projection_date, active[-1].projection_date,
                len(active), max(item.closing_balance - maximum_inventory for item in active), point.projection_date))
        active = []
    if len(active) >= minimum_duration_days:
        windows.append(PlanningWindow(active[0].projection_date, active[-1].projection_date,
            len(active), max(item.closing_balance - maximum_inventory for item in active), None))
    return tuple(windows)


def recommend_actions(
    *,
    as_of: date,
    events: Iterable[PlanningEvent],
    policy: PlanningPolicy,
    stockout_date: date | None,
    peak_shortage: Decimal,
    excess_qty: Decimal,
) -> tuple[Recommendation, ...]:
    events = list(events)
    recommendations: list[Recommendation] = []
    if stockout_date and peak_shortage > ZERO:
        movable = next((row for row in sorted((item for item in events if item.is_supply and item.event_date > stockout_date), key=lambda item: item.event_date)
                        if row.event_date > as_of + timedelta(days=policy.planning_time_fence_days)), None)
        if movable:
            qty = min(movable.quantity_delta, peak_shortage)
            recommendations.append(Recommendation(
                "PULL_IN", qty, movable.event_date, stockout_date - timedelta(days=1),
                movable.source_entity_type, movable.source_entity_id,
                f"Supply arrives after projected stockout on {stockout_date.isoformat()}.",
                ({"constraint": "planning_time_fence", "passed": True}, {"constraint": "available_supply", "passed": True}),
            ))
        else:
            quantity = _round_order(peak_shortage, policy)
            proposed = max(as_of + timedelta(days=policy.planned_lead_time_days), stockout_date - timedelta(days=1))
            recommendations.append(Recommendation(
                "NEW_BUY", quantity, None, proposed, None, None,
                f"No movable open supply covers the projected shortage on {stockout_date.isoformat()}.",
                ({"constraint": "minimum_order_qty", "passed": True}, {"constraint": "order_multiple", "passed": True}),
            ))
    if excess_qty > ZERO:
        future = next(iter(sorted((row for row in events if row.is_supply and row.event_date > as_of + timedelta(days=policy.cancellation_window_days)), key=lambda row: row.event_date, reverse=True)), None)
        if future:
            quantity = min(excess_qty, future.quantity_delta)
            action = "CANCEL_REDUCE" if future.metadata.get("cancellation_allowed") else "PUSH_OUT"
            recommendations.append(Recommendation(
                action, quantity, future.event_date, None,
                future.source_entity_type, future.source_entity_id,
                "Projected ending inventory exceeds the configured maximum coverage.",
                ({"constraint": "cancellation_window", "passed": True},),
            ))
    return tuple(recommendations)


def aggregate_points(points: Iterable[ProjectionPoint], granularity: str) -> tuple[ProjectionPoint, ...]:
    points = list(points)
    if granularity == "daily":
        return tuple(points)
    if granularity not in {"weekly", "monthly"}:
        raise ValueError("granularity must be daily, weekly, or monthly")
    groups: dict[tuple[int, int], list[ProjectionPoint]] = {}
    for point in points:
        key = point.projection_date.isocalendar()[:2] if granularity == "weekly" else (point.projection_date.year, point.projection_date.month)
        groups.setdefault(key, []).append(point)
    output: list[ProjectionPoint] = []
    rank = {"UNKNOWN": 4, "RED": 3, "YELLOW": 2, "GREEN": 1}
    for group in groups.values():
        output.append(ProjectionPoint(
            group[-1].projection_date,
            group[0].opening_balance,
            sum((row.supply_qty for row in group), ZERO),
            sum((row.demand_qty for row in group), ZERO),
            group[-1].closing_balance,
            group[-1].safety_stock_qty,
            max((row.risk_status for row in group), key=lambda value: rank[value]),
        ))
    return tuple(output)
