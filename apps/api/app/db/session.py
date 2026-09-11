from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def normalized_database_url() -> str:
    url = get_settings().database_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(
    normalized_database_url(),
    connect_args={"check_same_thread": False} if normalized_database_url().startswith("sqlite") else {},
    pool_pre_ping=True,
)


if normalized_database_url().startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Session, "before_flush")
def capture_domain_changes(session: Session, _flush_context, _instances) -> None:
    from app.db import models
    watched = (
        models.PurchaseRequirement, models.RFQ, models.SupplierQuote, models.BidComparison,
        models.AwardDecision, models.PODraft, models.ASN, models.GateEntry,
        models.StoreReceipt, models.InspectionResult, models.SupplierInvoice, models.Task,
        models.Commitment, models.AgentProposal, models.PreparedWorkItem,
    )
    changes = session.info.setdefault("domain_changes", [])
    known = {id(row) for row in changes}
    for row in list(session.new) + list(session.dirty):
        if isinstance(row, watched) and id(row) not in known and session.is_modified(row, include_collections=True):
            changes.append(row)
            known.add(id(row))


@event.listens_for(Session, "after_flush_postexec")
def append_transactional_events(session: Session, _flush_context) -> None:
    from uuid import uuid4
    from app.db import models
    from app.eventing import correlation_context
    changes = session.info.pop("domain_changes", [])
    for row in changes:
        if not getattr(row, "id", None) or not getattr(row, "tenant_id", None):
            continue
        if isinstance(row, models.PurchaseRequirement):
            event_type, requirement_id = "procurement.requirement.changed", row.id
        elif isinstance(row, models.Task):
            event_type, requirement_id = "task.changed", None
            if row.objective_id:
                objective = session.get(models.ProcurementCycleObjective, row.objective_id)
                requirement_id = objective.requirement_id if objective else None
        elif isinstance(row, models.Commitment):
            event_type, requirement_id = "commitment.changed", None
            if row.objective_id:
                objective = session.get(models.ProcurementCycleObjective, row.objective_id)
                requirement_id = objective.requirement_id if objective else None
        elif isinstance(row, models.AgentProposal):
            event_type, requirement_id = "agent.proposal.changed", None
        elif isinstance(row, models.PreparedWorkItem):
            event_type, requirement_id = "prepared_work.changed", None
            objective = session.get(models.ProcurementCycleObjective, row.objective_id)
            requirement_id = objective.requirement_id if objective else None
        else:
            event_type, requirement_id = f"procurement.{row.__tablename__}.changed", getattr(row, "requirement_id", None)
            if requirement_id is None and getattr(row, "rfq_id", None):
                rfq = session.get(models.RFQ, row.rfq_id)
                requirement_id = rfq.requirement_id if rfq else None
        correlation_id = correlation_context.get() or str(uuid4())
        session.add(models.EventOutbox(
            tenant_id=row.tenant_id, plant_id=getattr(row, "plant_id", None),
            event_type=event_type, aggregate_type=row.__tablename__, aggregate_id=row.id,
            aggregate_version=getattr(row, "version", 1), correlation_id=correlation_id,
            actor_membership_id=session.info.get("actor_membership_id"),
            payload={"entity_id": row.id, "requirement_id": requirement_id},
        ))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
