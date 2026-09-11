from __future__ import annotations

from typing import Any

from app.intelligence.schemas import ActionCandidate, EvidenceReference


class DecisionService:
    """Normalizes authoritative domain candidates; it does not invent quantities."""
    @staticmethod
    def rank(candidates: list[dict[str, Any]], evidence: list[EvidenceReference]) -> list[ActionCandidate]:
        normalized: list[tuple[float, ActionCandidate]] = []
        for raw in candidates:
            # Only the domain engine owns scores. Stable sorting preserves
            # supplied order when no authoritative score is available.
            score = float(raw.get("score") or 0)
            normalized.append((score, ActionCandidate(
                action_type=str(raw["action_type"]), target_type=str(raw["target_type"]),
                target_id=str(raw["target_id"]), parameters=dict(raw.get("parameters", {})),
                reason=str(raw.get("reason", "Domain engine candidate")),
                expected_impact=dict(raw.get("expected_impact", {})), evidence=evidence,
                risk_level=str(raw.get("risk_level", "medium")), requires_approval=True)))
        return [item for _, item in sorted(normalized, key=lambda item: item[0], reverse=True)]
