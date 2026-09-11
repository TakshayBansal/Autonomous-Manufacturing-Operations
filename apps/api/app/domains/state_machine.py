from collections.abc import Mapping

from fastapi import HTTPException


TRANSITIONS: Mapping[str, Mapping[str, set[str]]] = {
    "requirement": {"draft": {"approved", "cancelled"}, "approved": {"rfq_drafted", "cancelled"}},
    "rfq": {"draft": {"published", "cancelled"}, "published": {"responses_open", "closed"}, "responses_open": {"closed"}},
    "quote": {"extracting": {"needs_review", "needs_manual_entry", "rejected"}, "needs_review": {"verified", "rejected"}, "verified": {"needs_review", "superseded"}},
    "comparison": {"draft": {"ready_for_manager_review", "no_eligible_supplier"}, "ready_for_manager_review": {"superseded"}},
    "negotiation": {"draft": {"pending_approval"}, "pending_approval": {"manager_approved", "rejected"}, "manager_approved": {"supplier_countered", "closed"}, "supplier_countered": {"accepted_pending_reverification", "closed"}, "accepted_pending_reverification": {"closed"}},
    "award": {"pending_approval": {"approved", "rejected"}},
    "po": {"pending_approval": {"approved_pending_outbox", "rejected"}, "approved_pending_outbox": {"posting"}, "posting": {"simulated_posted", "posted", "failed"}, "failed": {"posting"}},
    "outbox": {"pending_approval": {"approved", "rejected"}, "approved": {"dispatching"}, "dispatching": {"simulated", "dispatched", "failed"}, "failed": {"dispatching"}},
    "case": {"requirement_created": {"receipt_exception", "inspection_exception", "closed"}, "receipt_exception": {"inspection_exception", "closed"}, "inspection_exception": {"closed"}},
}


def ensure_transition(entity_type: str, current: str, target: str) -> None:
    allowed = TRANSITIONS.get(entity_type, {}).get(current, set())
    if target not in allowed:
        raise HTTPException(status_code=409, detail=f"Invalid {entity_type} transition: {current} -> {target}")
