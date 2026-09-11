"""First replay-safe Temporal procurement workflow boundary.

Temporal remains feature-flagged. Activities call canonical services outside the
workflow; signals carry human and external events into deterministic state.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProcurementWorkflowState:
    objective_id: str
    stage: str = "requirement"
    aggregate_version: int = 1
    pending_signals: list[dict] = field(default_factory=list)
    completed: bool = False


class ProcurementCycleWorkflowContract:
    """Provider-neutral contract also used when Temporal is not installed."""

    def __init__(self) -> None:
        self.state: ProcurementWorkflowState | None = None

    async def run(self, objective_id: str) -> dict:
        self.state = ProcurementWorkflowState(objective_id=objective_id)
        return {"objective_id": objective_id, "state": "waiting_for_signals"}

    async def business_event(self, event: dict) -> None:
        if self.state is None:
            raise RuntimeError("Workflow has not started")
        self.state.pending_signals.append(event)

    async def human_decision(self, decision: dict) -> None:
        await self.business_event({"type": "human_decision", **decision})

    def snapshot(self) -> dict:
        return vars(self.state) if self.state else {"state": "not_started"}


try:  # Optional SDK: deployment installs it only when the feature is enabled.
    from temporalio import workflow

    @workflow.defn(name="GenuineGigsProcurementCycle")
    class TemporalProcurementCycleWorkflow(ProcurementCycleWorkflowContract):
        @workflow.run
        async def run(self, objective_id: str) -> dict:
            return await super().run(objective_id)

        @workflow.signal
        async def business_event(self, event: dict) -> None:
            await super().business_event(event)

        @workflow.signal
        async def human_decision(self, decision: dict) -> None:
            await super().human_decision(decision)

        @workflow.query
        def snapshot(self) -> dict:
            return super().snapshot()
except ImportError:
    TemporalProcurementCycleWorkflow = None
