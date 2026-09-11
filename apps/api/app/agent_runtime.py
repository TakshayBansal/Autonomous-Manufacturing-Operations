"""Bounded server-controlled tool/observation loop.

The loop is deliberately business-service agnostic: adapters remain responsible for
scope, authorization, persistence, and receipts.
"""

from collections.abc import Callable
from time import monotonic
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class RuntimeState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    next_request: dict[str, Any] | None
    final: dict[str, Any] | None
    decision_count: int
    read_count: int
    mutation_count: int
    proposal_count: int
    termination_reason: str | None


Decision = Callable[[RuntimeState], dict[str, Any]]
Executor = Callable[[dict[str, Any]], dict[str, Any]]


def run_bounded_tool_loop(
    initial: RuntimeState,
    *,
    decide: Decision,
    execute: Executor,
    tool_categories: dict[str, Literal['read', 'mutation', 'proposal']],
    max_decisions: int = 6,
    max_reads: int = 5,
    max_tool_calls: int = 8,
    max_candidates: int = 5,
    max_seconds: float = 45,
) -> RuntimeState:
    started_at = monotonic()

    def time_exceeded() -> bool:
        return monotonic() - started_at >= max_seconds

    def model_decide(state: RuntimeState) -> RuntimeState:
        if time_exceeded():
            return {**state, 'termination_reason': 'time_budget_exceeded', 'next_request': None}
        if state.get('decision_count', 0) >= max_decisions:
            return {**state, 'termination_reason': 'decision_budget_exceeded', 'next_request': None}
        request = decide(state)
        if request.get('type') == 'final':
            return {
                **state, 'decision_count': state.get('decision_count', 0) + 1,
                'final': request, 'next_request': None, 'termination_reason': 'final_answer',
            }
        return {
            **state, 'decision_count': state.get('decision_count', 0) + 1,
            'next_request': request,
        }

    def execute_request(state: RuntimeState) -> RuntimeState:
        if time_exceeded():
            return {**state, 'next_request': None, 'termination_reason': 'time_budget_exceeded'}
        request = state.get('next_request') or {}
        tool = str(request.get('tool') or '')
        category = tool_categories.get(tool)
        if category is None:
            return {**state, 'next_request': None, 'termination_reason': 'unknown_tool'}
        total_calls = (
            state.get('read_count', 0) + state.get('mutation_count', 0)
            + state.get('proposal_count', 0)
        )
        if total_calls >= max_tool_calls:
            return {**state, 'next_request': None, 'termination_reason': 'tool_budget_exceeded'}
        if category == 'read' and state.get('read_count', 0) >= max_reads:
            return {**state, 'next_request': None, 'termination_reason': 'read_budget_exceeded'}
        if category == 'mutation' and state.get('mutation_count', 0) >= 1:
            return {**state, 'next_request': None, 'termination_reason': 'mutation_budget_exceeded'}
        if category == 'proposal' and state.get('proposal_count', 0) >= 1:
            return {**state, 'next_request': None, 'termination_reason': 'proposal_budget_exceeded'}
        observation = execute(request)
        candidate_count = len(observation.get('candidates') or [])
        if candidate_count > max_candidates:
            observation = {
                **observation,
                'candidates': list(observation.get('candidates') or [])[:max_candidates],
                'candidate_truncated': True,
            }
        result_status = str(observation.get('status') or '')
        has_receipt = isinstance(observation.get('receipt'), dict) and bool(observation['receipt'])
        # ``ok`` is retained only for direct callers of this low-level loop
        # during the V2 rollout. The live executor always emits ToolResult.
        legacy_completed = result_status == 'ok' and 'business_summary' not in observation
        completed_mutation = category == 'mutation' and (
            (result_status == 'completed' and has_receipt) or legacy_completed
        )
        created_proposal = category == 'proposal' and result_status == 'proposal_created'
        next_state = {
            **state, 'next_request': None,
            'observations': [*(state.get('observations') or []), observation],
            'read_count': state.get('read_count', 0) + (category == 'read'),
            'mutation_count': state.get('mutation_count', 0) + completed_mutation,
            'proposal_count': state.get('proposal_count', 0) + created_proposal,
        }
        if completed_mutation:
            next_state['termination_reason'] = 'mutation_completed'
        elif created_proposal:
            next_state['termination_reason'] = 'proposal_created'
        elif result_status == 'needs_clarification':
            next_state['termination_reason'] = 'needs_clarification'
        elif result_status == 'processing':
            next_state['termination_reason'] = 'processing'
        elif result_status in {'blocked', 'failed'}:
            next_state['termination_reason'] = result_status
        return next_state

    def after_decide(state: RuntimeState) -> str:
        return END if state.get('termination_reason') or state.get('final') else 'execute'

    def after_execute(state: RuntimeState) -> str:
        return END if state.get('termination_reason') else 'decide'

    graph = StateGraph(RuntimeState)
    graph.add_node('decide', model_decide)
    graph.add_node('execute', execute_request)
    graph.add_edge(START, 'decide')
    graph.add_conditional_edges('decide', after_decide, {'execute': 'execute', END: END})
    graph.add_conditional_edges('execute', after_execute, {'decide': 'decide', END: END})
    compiled = graph.compile()
    return compiled.invoke({
        'messages': initial.get('messages', []), 'observations': initial.get('observations', []),
        'decision_count': 0, 'read_count': 0, 'mutation_count': 0, 'proposal_count': 0,
    })
