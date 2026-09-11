"""Code-defined recovery playbooks. LLMs do not determine applicability."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Candidate:
    strategy_type: str
    title: str
    description: str
    recovery_ratio: float
    implementation_seconds: int
    direct_cost: float
    quality_risk: float
    safety_risk: float
    operational_risk: float
    uncertainty: float
    success_probability: float
    authorities: tuple[str, ...] = ()
    requirements: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    actions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Playbook:
    key: str
    categories: frozenset[str]
    factory: Callable[[Any], list[Candidate]]


def _production(ctx):
    return [
        Candidate("recover_line_rate", "Stabilize the current line and recover rate", "Remove the active constraint, confirm stable rate, then protect the remaining schedule.", .72, 2700, 3500, .08, .05, .12, .18, .76,
                  actions=({"title":"Confirm constraint and stable cycle window","owner_role":"production_supervisor"}, {"title":"Restore and verify current line rate","owner_role":"production_supervisor"})),
        Candidate("overtime", "Reserve controlled overtime after recovery", "Extend the available production window after the constraint is removed.", .55, 5400, 8000, .08, .10, .14, .20, .72, ("recovery.overtime.approve",),
                  actions=({"title":"Approve controlled overtime window","owner_role":"plant_manager"}, {"title":"Publish revised shift plan","owner_role":"production_manager"})),
        Candidate("reroute_work_order", "Reroute compatible quantity to an alternate line", "Validate line, tooling, material and quality compatibility before schedule release.", .82, 2400, 12000, .28, .10, .30, .32, .63, ("recovery.reroute.approve",),
                  requirements=({"type":"line_compatibility","freshness_required":True},),
                  actions=({"title":"Verify alternate-line compatibility","owner_role":"production_manager"}, {"title":"Verify tooling and material staging","owner_role":"store_manager"}, {"title":"Approve and release reroute","owner_role":"production_manager"})),
    ]


def _machine(ctx):
    spare = bool(ctx.get("spare_available", True))
    return [
        Candidate("repair_asset", "Repair the current asset and verify stable production", "Use CMMS work, spare evidence and a healthy signal window before returning to plan.", .78 if spare else .35, 2700 if spare else 7200, 6000 if spare else 9500, .06, .08, .10, .12 if spare else .38, .84 if spare else .48,
                  requirements=({"type":"spare_availability","available":spare},),
                  actions=({"title":"Diagnose and repair constrained asset","owner_role":"maintenance_technician"}, {"title":"Verify healthy signals and production restart","owner_role":"maintenance_manager"})),
        Candidate("reroute_work_order", "Reroute production while the asset is repaired", "Protect output on a compatible line with explicit quality and schedule approval.", .70, 2400, 14000, .30, .10, .32, .30, .62, ("recovery.reroute.approve",),
                  actions=({"title":"Verify alternate-line process compatibility","owner_role":"quality_manager"}, {"title":"Approve temporary production reroute","owner_role":"production_manager"})),
        Candidate("repair_plus_overtime", "Repair asset and reserve recovery overtime", "Combine the lowest quality-risk repair path with a controlled extended production window.", .91 if spare else .58, 3600, 14000, .08, .10, .16, .18, .79 if spare else .51, ("recovery.overtime.approve",),
                  actions=({"title":"Repair and validate constrained asset","owner_role":"maintenance_technician"}, {"title":"Approve recovery overtime","owner_role":"plant_manager"}, {"title":"Verify stable post-repair rate","owner_role":"production_supervisor"})),
    ]


def _material(ctx):
    return [
        Candidate("supplier_expedite", "Expedite the confirmed supplier quantity", "Obtain a governed commitment and protect the need time.", .62, 7200, 5000, .04, .02, .18, .30, .64, ("recovery.supplier_expedite",), actions=({"title":"Obtain expedited supplier commitment","owner_role":"purchase_executive"},)),
        Candidate("alternate_material", "Release an approved alternate material", "Use only a qualified substitution with Quality and Materials approval.", .88, 3600, 9000, .24, .08, .20, .25, .70, ("recovery.alternate_material.approve",), requirements=({"type":"approved_substitution","required":True},), actions=({"title":"Verify alternate material qualification","owner_role":"quality_manager"}, {"title":"Approve and stage alternate material","owner_role":"store_manager"})),
        Candidate("resequence_production", "Resequence production around the shortage", "Protect total shift output by moving a material-ready order forward.", .52, 1800, 2500, .10, .03, .24, .22, .73, ("recovery.resequence.approve",), actions=({"title":"Validate ready replacement order","owner_role":"production_manager"}, {"title":"Publish revised production sequence","owner_role":"production_manager"})),
    ]


def _quality(ctx):
    return [
        Candidate("contain_and_adjust", "Contain the affected lot and restore the approved process window", "Protect downstream flow while Quality verifies stable measurements.", .68, 2400, 6500, .10, .05, .16, .18, .78, ("recovery.quality_containment",), actions=({"title":"Contain affected lot","owner_role":"quality_inspector"}, {"title":"Verify approved process adjustment","owner_role":"quality_manager"}, {"title":"Confirm stable measurement window","owner_role":"quality_inspector"})),
        Candidate("switch_material_lot", "Switch to a released material lot", "Quarantine the suspect lot and verify first-off production from an approved lot.", .74, 1800, 8000, .12, .04, .20, .22, .72, ("recovery.material_lot.release",), actions=({"title":"Select and release alternate lot","owner_role":"quality_manager"}, {"title":"Stage released lot and run first-off inspection","owner_role":"store_manager"})),
        Candidate("inspect_100_percent", "Continue under 100% controlled inspection", "Preserve limited flow with explicit containment and disposition evidence.", .45, 900, 15000, .18, .03, .28, .12, .82, ("recovery.quality_containment",), actions=({"title":"Establish controlled 100% inspection","owner_role":"quality_manager"},)),
    ]


def _supplier(ctx):
    return _material(ctx)


PLAYBOOKS = (
    Playbook("production", frozenset({"production"}), _production),
    Playbook("machine", frozenset({"downtime", "maintenance"}), _machine),
    Playbook("material", frozenset({"material"}), _material),
    Playbook("quality", frozenset({"quality"}), _quality),
    Playbook("supplier", frozenset({"supplier"}), _supplier),
)


def candidates_for(category: str, context: dict[str, Any]) -> list[Candidate]:
    result: list[Candidate] = []
    for playbook in PLAYBOOKS:
        if category in playbook.categories:
            result.extend(playbook.factory(context))
    return result[:4]
