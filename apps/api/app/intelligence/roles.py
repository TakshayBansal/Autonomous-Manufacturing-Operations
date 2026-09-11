from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleProfile:
    key: str
    response_depth: str
    domains: frozenset[str]
    tool_groups: frozenset[str]
    can_propose_actions: bool
    memory_scopes: frozenset[str]


PROFILES = {
    "scm_planner": RoleProfile("scm_planner", "operational", frozenset({"factory", "scm", "procurement"}), frozenset({"factory", "scm", "procurement", "action"}), True, frozenset({"user", "plant", "team"})),
    "purchase_executive": RoleProfile("procurement_buyer", "operational", frozenset({"factory", "procurement", "scm"}), frozenset({"factory", "procurement", "scm", "action"}), True, frozenset({"user", "team"})),
    "purchase_manager": RoleProfile("manager", "management", frozenset({"factory", "procurement", "scm", "operations"}), frozenset({"factory", "procurement", "scm", "operations", "action"}), True, frozenset({"user", "team", "plant"})),
    "plant_manager": RoleProfile("manager", "management", frozenset({"factory", "procurement", "scm", "operations"}), frozenset({"factory", "procurement", "scm", "operations", "action"}), True, frozenset({"user", "team", "plant"})),
    "admin": RoleProfile("leadership", "executive", frozenset({"factory", "procurement", "scm", "operations"}), frozenset({"factory", "procurement", "scm", "operations", "action", "knowledge"}), True, frozenset({"user", "team", "plant", "tenant"})),
}
DEFAULT = RoleProfile("operator", "concise", frozenset({"factory", "operations"}), frozenset({"factory", "operations"}), False, frozenset({"user"}))


def profile_for(role: str) -> RoleProfile:
    return PROFILES.get(role, DEFAULT)
