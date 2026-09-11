"""Local-only developer observability API for the Northstar simulation."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import SessionLocal, get_db
from app import eventing
from app.operations.state import get_latest_operational_state, serialize_snapshot
from app.operations.recovery import service as recovery_service

router = APIRouter(prefix="/internal/devtools", tags=["developer-tools"])
TENANT_ID = "tenant-northstar-mobility"


def developer_guard(x_developer_token: str | None = Header(default=None)) -> None:
    flag=os.getenv("DEVELOPER_LAB_ENABLED")
    environment=os.getenv("APP_ENV","production").lower()
    enabled=(flag or "").lower()=="true" or (flag is None and environment in {"development","test"})
    if not enabled:
        raise HTTPException(404, "Developer tools are disabled")
    expected = os.getenv("DEVELOPER_LAB_TOKEN", "northstar-developer-local")
    if x_developer_token != expected:
        raise HTTPException(401, "Invalid developer token")


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _redact(value):
    """Keep developer traces useful without turning the portal into a secret viewer."""
    if isinstance(value, dict):
        return {
            key: "[redacted]" if any(part in key.lower() for part in
                ("password", "secret", "token", "cookie", "authorization")) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


@router.get("/health", dependencies=[Depends(developer_guard)])
def health(db: Session = Depends(get_db)):
    connections = db.query(models.IntegrationConnection).filter_by(tenant_id=TENANT_ID).all()
    jobs = (db.query(models.IntegrationSyncJob).filter_by(tenant_id=TENANT_ID)
            .order_by(models.IntegrationSyncJob.created_at.desc()).limit(50).all())
    pending = db.query(models.EventOutbox).filter(
        models.EventOutbox.tenant_id == TENANT_ID,
        models.EventOutbox.status.in_(("pending", "retry", "dead_letter"))).all()
    return {"generated_at": datetime.now(timezone.utc), "connections": [{
        "id": row.id, "name": row.name, "provider": row.provider, "status": row.status,
        "last_checked_at": _iso(row.last_checked_at),
    } for row in connections], "jobs": [{
        "id": row.id, "type": row.job_type, "status": row.status,
        "started_at": _iso(row.started_at), "finished_at": _iso(row.finished_at),
        "counts": (row.summary or {}).get("counts", {}), "error": row.error,
    } for row in jobs], "event_queue": {
        "pending": sum(row.status == "pending" for row in pending),
        "retry": sum(row.status == "retry" for row in pending),
        "dead_letter": sum(row.status == "dead_letter" for row in pending),
    }}


@router.get("/topology", dependencies=[Depends(developer_guard)])
def topology(db: Session = Depends(get_db)):
    latest = (db.query(models.IntegrationSyncJob).filter_by(tenant_id=TENANT_ID)
              .order_by(models.IntegrationSyncJob.created_at.desc()).limit(8).all())
    nodes = [
        {"id": "sources", "label": "Factory source systems", "kind": "source"},
        {"id": "connector", "label": "Connector + cursors", "kind": "integration"},
        {"id": "canonical", "label": "Canonical plant state", "kind": "state"},
        {"id": "detectors", "label": "Detectors + forecasts", "kind": "reasoning"},
        {"id": "work", "label": "Actions + agents", "kind": "orchestration"},
        {"id": "outbox", "label": "Outbox + SSE", "kind": "delivery"},
    ]
    edges = [{"from": nodes[i]["id"], "to": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)]
    return {"nodes": nodes, "edges": edges, "latest_jobs": [{
        "type": row.job_type, "status": row.status, "counts": (row.summary or {}).get("counts", {})
    } for row in latest]}


@router.get("/traces", dependencies=[Depends(developer_guard)])
def traces(limit: int = 100, db: Session = Depends(get_db)):
    events = (db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID)
              .order_by(models.EventOutbox.created_at.desc()).limit(min(limit, 200)).all())
    return [{"trace_id": row.correlation_id, "event_id": row.event_id, "event_type": row.event_type,
             "aggregate_type": row.aggregate_type, "aggregate_id": row.aggregate_id,
             "status": row.status, "attempts": row.attempts, "created_at": row.created_at,
             "processed_at": row.processed_at, "last_error": row.last_error} for row in events]


@router.get("/traces/{trace_id}", dependencies=[Depends(developer_guard)])
def trace(trace_id: str, db: Session = Depends(get_db)):
    events = db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID, correlation_id=trace_id).all()
    event_ids = [row.event_id for row in events]
    receipts = db.query(models.EventConsumerReceipt).filter(
        models.EventConsumerReceipt.event_id.in_(event_ids)).all() if event_ids else []
    runs = db.query(models.AgentRun).filter_by(tenant_id=TENANT_ID, correlation_id=trace_id).all()
    calls = db.query(models.AgentToolCall).filter_by(tenant_id=TENANT_ID, correlation_id=trace_id).all()
    audits = db.query(models.AuditEvent).filter_by(tenant_id=TENANT_ID, correlation_id=trace_id).all()
    return {"trace_id": trace_id, "events": [{"event_id": r.event_id, "type": r.event_type,
        "aggregate": f"{r.aggregate_type}:{r.aggregate_id}", "status": r.status,
        "payload": _redact(r.payload), "at": r.created_at} for r in events],
        "consumer_receipts": [{"event_id": r.event_id, "consumer": r.consumer_name,
            "status": r.status, "attempts": r.attempt_count, "error": r.error} for r in receipts],
        "agent_runs": [{"id": r.id, "state": r.state, "intent": r.intent,
            "termination_reason": r.termination_reason, "latency_ms": r.latency_ms} for r in runs],
        "tool_calls": [{"tool": r.tool_name, "authorization": r.authorization_decision,
            "latency_ms": r.latency_ms, "target": f"{r.target_entity_type}:{r.target_entity_id}"} for r in calls],
        "audit": [{"action": r.action, "entity": f"{r.entity_type}:{r.entity_id}",
            "result": r.result, "at": r.created_at} for r in audits]}


@router.get("/source-events/{source_event_id}/trace", dependencies=[Depends(developer_guard)])
def source_event_trace(source_event_id: str, db: Session=Depends(get_db)):
    receipts=db.query(models.IntegrationIngestionRecord).filter_by(
        tenant_id=TENANT_ID,source_record_key=source_event_id).all()
    stages=[{"id":"source","label":"Factory source","status":"emitted","output":{"event_id":source_event_id}}]
    for receipt in receipts:
        stages.extend([
            {"id":f"receive:{receipt.id}","label":"Connector receive","status":"accepted","output":{"capability":receipt.capability,"cursor":receipt.source_cursor}},
            {"id":f"normalize:{receipt.id}","label":"Canonical normalization","status":receipt.status,"output":{"entity_type":receipt.target_entity_type,"entity_id":receipt.target_entity_id}},
        ])
        related=db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID,aggregate_id=receipt.target_entity_id).all()
        for event in related:
            stages.append({"id":f"event:{event.event_id}","label":event.event_type,"status":event.status,
                           "output":{"trace_id":event.correlation_id,"aggregate":event.aggregate_type}})
    return {"source_event_id":source_event_id,"found":bool(receipts),"stages":stages,
            "message":None if receipts else "The source event has not reached a canonical ingestion receipt yet."}


@router.get("/agent-runs/{run_id}/graph", dependencies=[Depends(developer_guard)])
def agent_graph(run_id: str, db: Session = Depends(get_db)):
    run = db.query(models.AgentRun).filter_by(id=run_id, tenant_id=TENANT_ID).first()
    if not run: raise HTTPException(404, "Agent run not found")
    checkpoints = db.query(models.AgentCheckpoint).filter_by(run_id=run.id).order_by(models.AgentCheckpoint.sequence).all()
    return {"run": {"id": run.id, "state": run.state, "intent": run.intent,
        "trace_id": run.trace_id, "termination_reason": run.termination_reason,
        "budgets": {"steps": run.step_count, "reads": run.read_tool_count, "mutations": run.mutation_count}},
        "runtime": "langgraph" if checkpoints else "deterministic_orchestration",
        "checkpoints": [{"sequence": row.sequence, "step": row.step_name,
            "status": row.status, "state_hash": row.state_hash} for row in checkpoints]}


@router.get("/entities/{entity_type}/{entity_id}/history", dependencies=[Depends(developer_guard)])
def entity_history(entity_type: str, entity_id: str, db: Session = Depends(get_db)):
    events = (db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID,
        aggregate_type=entity_type, aggregate_id=entity_id).order_by(models.EventOutbox.created_at).all())
    audits = (db.query(models.AuditEvent).filter_by(tenant_id=TENANT_ID,
        entity_type=entity_type, entity_id=entity_id).order_by(models.AuditEvent.created_at).all())
    return {"entity_type":entity_type,"entity_id":entity_id,
        "events":[{"type":r.event_type,"at":r.created_at,"status":r.status,"payload":_redact(r.payload)} for r in events],
        "audit":[{"action":r.action,"at":r.created_at,"result":r.result} for r in audits]}


@router.get("/live", dependencies=[Depends(developer_guard)])
def live():
    def stream():
        cursor = datetime.now(timezone.utc)
        yield f"event: devtools.ready\ndata: {json.dumps({'tenant_id': TENANT_ID})}\n\n"
        while True:
            db = SessionLocal()
            try:
                rows = (db.query(models.EventOutbox)
                        .filter(models.EventOutbox.tenant_id == TENANT_ID,
                                models.EventOutbox.created_at > cursor)
                        .order_by(models.EventOutbox.created_at.asc()).limit(100).all())
                for row in rows:
                    cursor = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
                    data = {"trace_id": row.correlation_id, "event_id": row.event_id,
                            "event_type": row.event_type, "aggregate_type": row.aggregate_type,
                            "aggregate_id": row.aggregate_id, "status": row.status,
                            "created_at": _iso(row.created_at)}
                    yield f"id: {row.event_id}\nevent: runtime.event\ndata: {json.dumps(data)}\n\n"
                if not rows:
                    yield f"event: heartbeat\ndata: {json.dumps({'at':datetime.now(timezone.utc).isoformat()})}\n\n"
            finally:
                db.close()
            time.sleep(2)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/browser-ack", dependencies=[Depends(developer_guard)])
def browser_ack(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    event_id = str(payload.get("event_id") or "")
    event = db.query(models.EventOutbox).filter_by(event_id=event_id, tenant_id=TENANT_ID).first()
    if not event:
        raise HTTPException(404, "Simulation event not found")
    received_at = datetime.now(timezone.utc)
    canonical = json.dumps(_redact(payload), sort_keys=True, default=str)
    db.add(models.AuditEvent(
        id=str(uuid4()), tenant_id=TENANT_ID, plant_id=event.plant_id,
        actor_user_id=None, actor="developer-lab", action="developer.browser_ack",
        entity_type="event_outbox", entity_id=event.event_id, result="accepted",
        correlation_id=event.correlation_id,
        payload_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        meta={"received_at": received_at.isoformat()},
    ))
    db.commit()
    return {"accepted": True, "event_id": event_id, "received_at": received_at}


@router.post("/events/{event_id}/replay", dependencies=[Depends(developer_guard)])
def replay_event(event_id: str, db: Session = Depends(get_db)):
    row = db.query(models.EventOutbox).filter_by(event_id=event_id, tenant_id=TENANT_ID).first()
    if not row: raise HTTPException(404, "Simulation event not found")
    eventing.replay(db, event_id)
    from app.workers import dispatch_domain_event
    dispatch_domain_event.apply_async(args=[event_id], queue="events")
    return {"event_id": event_id, "status": "queued", "completed_consumers_will_not_repeat": True}


@router.get("/services", dependencies=[Depends(developer_guard)])
def services(db: Session = Depends(get_db)):
    latest_job=(db.query(models.IntegrationSyncJob).filter_by(tenant_id=TENANT_ID)
                .order_by(models.IntegrationSyncJob.created_at.desc()).first())
    pending=db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID,status="pending").count()
    return {"services":[
        {"id":"web","name":"Web","kind":"frontend","status":"healthy","protocols":["HTTP","SSE"]},
        {"id":"api","name":"API","kind":"application","status":"healthy","protocols":["HTTP","SQL","Redis"]},
        {"id":"postgres","name":"PostgreSQL","kind":"state","status":"healthy","protocols":["SQL"]},
        {"id":"redis","name":"Redis / Celery","kind":"queue","status":"healthy","protocols":["Redis"]},
        {"id":"worker","name":"Celery Worker","kind":"worker","status":"healthy" if latest_job else "unknown","last_activity":_iso(latest_job.created_at) if latest_job else None},
        {"id":"beat","name":"Celery Beat","kind":"scheduler","status":"healthy","schedule_count":7},
        {"id":"outbox","name":"Transactional Outbox","kind":"delivery","status":"degraded" if pending>100 else "healthy","queue_depth":pending},
        {"id":"factory-lab","name":"Factory Lab","kind":"source","status":"healthy","protocols":["HTTP","MQTT","OPC UA","SMTP"]},
        {"id":"minio","name":"MinIO","kind":"documents","status":"configured","protocols":["S3"]},
        {"id":"mailpit","name":"Mailpit","kind":"mail","status":"configured","protocols":["SMTP"]},
    ]}


@router.get("/connectors", dependencies=[Depends(developer_guard)])
def connectors(db: Session = Depends(get_db)):
    rows=db.query(models.IntegrationConnection).filter_by(tenant_id=TENANT_ID).all()
    result=[]
    for row in rows:
        jobs=(db.query(models.IntegrationSyncJob).filter_by(connection_id=row.id)
              .order_by(models.IntegrationSyncJob.created_at.desc()).limit(100).all())
        counts={"received":0,"accepted":0,"rejected":0,"deduplicated":0}
        for job in jobs:
            summary=job.summary or {}; current=summary.get("counts",{})
            for key in counts: counts[key]+=int(current.get(key,0) or 0)
        result.append({"id":row.id,"name":row.name,"provider":row.provider,"mode":row.mode,"status":row.status,
            "last_checked_at":row.last_checked_at,"capabilities":row.enabled_capabilities,"counts":counts,
            "last_job":{"id":jobs[0].id,"status":jobs[0].status,"type":jobs[0].job_type,
                        "error":jobs[0].error,"summary":_redact(jobs[0].summary)} if jobs else None})
    return {"connectors":result}


@router.get("/events", dependencies=[Depends(developer_guard)])
def events(status: str | None=None, limit: int=200, db: Session=Depends(get_db)):
    query=db.query(models.EventOutbox).filter_by(tenant_id=TENANT_ID)
    if status: query=query.filter_by(status=status)
    rows=query.order_by(models.EventOutbox.created_at.desc()).limit(min(limit,500)).all()
    return {"events":[{"id":r.event_id,"type":r.event_type,"aggregate_type":r.aggregate_type,
        "aggregate_id":r.aggregate_id,"trace_id":r.correlation_id,"causation_id":r.causation_id,"status":r.status,
        "attempts":r.attempts,"created_at":r.created_at,"processed_at":r.processed_at,"error":r.last_error,
        "payload":_redact(r.payload)} for r in rows]}


CANONICAL_TYPES={"lines":models.ProductionLine,"assets":models.PlantAsset,"work_orders":models.ProductionWorkOrder,
    "production":models.ProductionActualPoint,"downtime":models.ProductionDowntimeEvent,"quality":models.ProductionQualityEvent,
    "inventory":models.MaterialInventoryPosition,"commitments":models.ProductionSupplierCommitment,"maintenance":models.MaintenanceWorkRecord}


@router.get("/canonical/{entity_type}", dependencies=[Depends(developer_guard)])
def canonical(entity_type: str, limit: int=100, db: Session=Depends(get_db)):
    model=CANONICAL_TYPES.get(entity_type)
    if not model: raise HTTPException(404,"Unknown canonical entity type")
    rows=db.query(model).filter_by(tenant_id=TENANT_ID).order_by(model.created_at.desc()).limit(min(limit,250)).all()
    return {"entity_type":entity_type,"records":[_redact({column.name:_iso(getattr(row,column.name)) for column in model.__table__.columns}) for row in rows]}


@router.get("/state/{entity_type}/{entity_id}", dependencies=[Depends(developer_guard)])
def state(entity_type: str, entity_id: str, db: Session=Depends(get_db)):
    if entity_type not in {"line","asset","work_order"}: raise HTTPException(422,"Unsupported state scope")
    current=get_latest_operational_state(db,TENANT_ID,entity_type,entity_id)
    history=(db.query(models.OperationalStateSnapshot).filter_by(tenant_id=TENANT_ID,scope_type=entity_type,scope_id=entity_id)
             .order_by(models.OperationalStateSnapshot.observed_at.desc()).limit(20).all())
    serialized=[serialize_snapshot(row) for row in history]
    diff={}
    if len(serialized)>1:
        for key,value in serialized[0].items():
            if serialized[1].get(key)!=value: diff[key]={"before":serialized[1].get(key),"after":value}
    return {"current":serialize_snapshot(current),"history":serialized,"diff":diff}


@router.get("/graph", dependencies=[Depends(developer_guard)])
def graph(root: str | None=None, depth: int=2, db: Session=Depends(get_db)):
    depth=min(max(depth,1),4); nodes=[]; edges=[]; known=set()
    def node(identifier,label,kind,meta=None):
        if identifier not in known: known.add(identifier); nodes.append({"id":identifier,"label":label,"type":kind,"meta":meta or {}})
    plant=db.get(models.Plant,"plant-northstar-chakan")
    if plant: node(plant.id,plant.name,"plant")
    lines=db.query(models.ProductionLine).filter_by(tenant_id=TENANT_ID,plant_id="plant-northstar-chakan").all()
    for line in lines:
        node(line.id,f"{line.code} · {line.name}","line"); edges.append({"id":f"{plant.id}:{line.id}","source":plant.id,"target":line.id,"type":"contains"})
    assets=db.query(models.PlantAsset).filter_by(tenant_id=TENANT_ID).all()
    for asset in assets:
        node(asset.id,asset.name,"asset",{"criticality":asset.criticality});
        if asset.line_id: edges.append({"id":f"{asset.line_id}:{asset.id}","source":asset.line_id,"target":asset.id,"type":"runs_on"})
    orders=db.query(models.ProductionWorkOrder).filter_by(tenant_id=TENANT_ID,status="in_progress").all()
    for order in orders:
        node(order.id,order.product_code,"work_order",{"target":order.target_quantity}); edges.append({"id":f"{order.id}:{order.line_id}","source":order.id,"target":order.line_id,"type":"scheduled_on"})
    deviations=db.query(models.OperationalDeviation).filter_by(tenant_id=TENANT_ID).order_by(models.OperationalDeviation.detected_at.desc()).limit(30).all()
    for deviation in deviations:
        node(deviation.id,deviation.title,"deviation",{"severity":deviation.severity,"status":deviation.status})
        target=deviation.asset_id or deviation.line_id or deviation.work_order_id
        if target: edges.append({"id":f"{target}:{deviation.id}","source":target,"target":deviation.id,"type":"detected_as"})
        case=db.query(models.RecoveryCase).filter_by(deviation_id=deviation.id).first()
        if case:
            node(case.id,f"Recovery · {case.status}","recovery_case"); edges.append({"id":f"{deviation.id}:{case.id}","source":deviation.id,"target":case.id,"type":"recovered_by"})
            strategies=db.query(models.RecoveryStrategy).filter_by(recovery_case_id=case.id).all()
            for strategy in strategies:
                node(strategy.id,strategy.title,"strategy",{"score":strategy.recovery_score,"status":strategy.status}); edges.append({"id":f"{case.id}:{strategy.id}","source":case.id,"target":strategy.id,"type":"considered"})
    if root and root in known:
        included={root}
        for _ in range(depth):
            included|={e["target"] for e in edges if e["source"] in included}|{e["source"] for e in edges if e["target"] in included}
        nodes=[n for n in nodes if n["id"] in included]; edges=[e for e in edges if e["source"] in included and e["target"] in included]
    return {"nodes":nodes,"edges":edges,"projection":"relational_causal_action_v1"}


@router.get("/deviations/{deviation_id}/explain", dependencies=[Depends(developer_guard)])
def explain_deviation(deviation_id: str, db: Session=Depends(get_db)):
    row=db.query(models.OperationalDeviation).filter_by(id=deviation_id,tenant_id=TENANT_ID).first()
    if not row: raise HTTPException(404,"Deviation not found")
    rule=db.query(models.OperationalDetectorRule).filter_by(tenant_id=TENANT_ID,detector_key=row.detector_key).first()
    actions=db.query(models.OperationalAction).filter_by(deviation_id=row.id).all()
    return {"deviation":{"id":row.id,"title":row.title,"category":row.category,"severity":row.severity,"status":row.status},
        "trigger":{"detected_at":row.detected_at,"source_event_ids":row.source_event_ids},
        "detector":{"key":row.detector_key,"rule_id":rule.id if rule else None,"version":rule.version if rule else None},
        "inputs":_redact(row.current_state),"expected":_redact(row.expected_state),"rules":_redact(rule.parameters if rule else {}),
        "derived_values":{"lost_units":row.estimated_lost_units,"financial_impact":row.estimated_financial_impact,"confidence":row.confidence},
        "decision":{"created":True,"severity":row.severity},"actions":[{"id":a.id,"title":a.title,"owner_role":a.owner_role,"status":a.status} for a in actions]}


@router.get("/recovery/{case_id}/explain", dependencies=[Depends(developer_guard)])
def explain_recovery(case_id: str, db: Session=Depends(get_db)):
    case=db.query(models.RecoveryCase).filter_by(id=case_id,tenant_id=TENANT_ID).first()
    if not case: raise HTTPException(404,"Recovery Case not found")
    payload=recovery_service.serialize_case(db,case)
    return {"case":payload,"playbooks_considered":list(dict.fromkeys(row["strategy_type"] for row in payload["strategies"])),
        "recommendation":{"strategy_id":case.recommended_strategy_id},"selection":{"strategy_id":case.selected_strategy_id,
        "actor":case.decision_actor_id,"reason":case.decision_reason,"override_reason":case.override_reason},
        "ranking_boundary":"deterministic; Gigi explains but does not calculate"}


@router.get("/agents", dependencies=[Depends(developer_guard)])
def agents(limit: int=100, db: Session=Depends(get_db)):
    runs=db.query(models.AgentRun).filter_by(tenant_id=TENANT_ID).order_by(models.AgentRun.created_at.desc()).limit(min(limit,200)).all()
    return {"runs":[{"id":r.id,"intent":r.intent,"state":r.state,"trigger":r.correlation_id,"runtime":r.model,
        "latency_ms":r.latency_ms,"steps":r.step_count,"reads":r.read_tool_count,"mutations":r.mutation_count,
        "termination":r.termination_reason,"created_at":r.created_at} for r in runs]}


@router.get("/value/{entity_type}/{entity_id}", dependencies=[Depends(developer_guard)])
def value(entity_type: str, entity_id: str, db: Session=Depends(get_db)):
    query=db.query(models.OperationalValueEntry).filter_by(tenant_id=TENANT_ID)
    query=query.filter_by(deviation_id=entity_id) if entity_type=="deviation" else query.filter_by(action_id=entity_id)
    rows=query.order_by(models.OperationalValueEntry.captured_at).all()
    return {"entries":[{"id":r.id,"type":r.value_type,"amount":r.amount,"currency":r.currency,
        "confidence":r.confidence_state,"method":r.calculation_method,"inputs":r.calculation_inputs,"captured_at":r.captured_at} for r in rows]}


@router.post("/assertions/evaluate", dependencies=[Depends(developer_guard)])
def evaluate_assertions(payload: dict=Body(default={}), db: Session=Depends(get_db)):
    """Evaluate lab-only expectations; product runtime never consumes these."""
    started_at=payload.get("started_at")
    since=datetime.fromisoformat(str(started_at).replace("Z","+00:00")) if started_at else None
    def rows_since(model,field="created_at"):
        query=db.query(model).filter_by(tenant_id=TENANT_ID)
        return query.filter(getattr(model,field)>=since).all() if since else query.all()
    deviations=rows_since(models.OperationalDeviation,"detected_at")
    cases=rows_since(models.RecoveryCase,"opened_at")
    outcomes=rows_since(models.RecoveryOutcome)
    actions=rows_since(models.OperationalAction)
    jobs=rows_since(models.IntegrationSyncJob)
    snapshots=rows_since(models.OperationalStateSnapshot,"observed_at")
    values=rows_since(models.OperationalValueEntry,"captured_at")
    updates=[]
    for assertion in payload.get("assertions",[]):
        text_value=str(assertion.get("description","")).lower(); status="waiting"; observed={}
        if assertion.get("category")=="ingestion": status="passed" if any(j.status in {"completed","completed_with_errors"} for j in jobs) else "waiting"; observed={"sync_jobs":len(jobs)}
        elif assertion.get("category")=="state": status="passed" if snapshots else "waiting"; observed={"snapshots":len(snapshots)}
        elif assertion.get("category")=="detection":
            if "no new" in text_value: status="failed" if any(d.severity in {"high","critical"} and d.status!="verified" for d in deviations) else "passed"
            else: status="passed" if deviations else "waiting"
            observed={"deviations":len(deviations)}
        elif assertion.get("category")=="recovery": status="passed" if cases else "waiting"; observed={"recovery_cases":len(cases)}
        elif assertion.get("category")=="execution": status="passed" if actions else "waiting"; observed={"actions":len(actions)}
        elif assertion.get("category")=="verification": status="passed" if outcomes else "waiting"; observed={"outcomes":len(outcomes)}
        elif assertion.get("category")=="learning": status="passed" if outcomes and any(o.context_fingerprint for o in outcomes) else "waiting"; observed={"memory_records":len(outcomes)}
        elif assertion.get("category")=="impact": status="passed" if values else "waiting"; observed={"value_entries":len(values)}
        updates.append({"id":assertion.get("id"),"status":status,"observed":observed,"evaluated_at":datetime.now(timezone.utc).isoformat(),"details":{"lab_only":True}})
    return {"updates":updates}


@router.get("/workers", dependencies=[Depends(developer_guard)])
def workers(db: Session=Depends(get_db)):
    jobs=(db.query(models.IntegrationSyncJob).filter_by(tenant_id=TENANT_ID)
          .order_by(models.IntegrationSyncJob.created_at.desc()).limit(200).all())
    return {"jobs":[{"id":r.id,"name":r.job_type,"status":r.status,"attempts":int((r.summary or {}).get("attempts",0)),
        "queued_at":r.created_at,"started_at":r.started_at,"finished_at":r.finished_at,"error":r.error,
        "correlation_id":(r.summary or {}).get("correlation_id")} for r in jobs],
        "scheduled":["sync_factory_simulators","reconcile_operational_snapshots","log_forecast_evaluations",
                     "evaluate_all_v2_action_slas","reconcile_all_v2_lines","dispatch_pending_domain_events"]}


@router.get("/apis", dependencies=[Depends(developer_guard)])
def apis():
    contracts=[("GET","/api/v2/home","home projection"),("GET","/api/v2/command-center","operational_v2"),
        ("GET","/api/v2/operations","operational_v2"),("GET","/api/v2/deviations/{id}","operational_v2"),
        ("GET","/api/v2/recovery-cases/{id}","recovery"),("POST","/api/v2/recovery-cases/{id}/select-strategy","recovery"),
        ("POST","/api/v2/edge/events","edge ingestion"),("GET","/api/v2/events/stream","SSE delivery"),
        ("GET","/internal/devtools/graph","developer observatory")]
    return {"endpoints":[{"method":method,"route":route,"owner":owner,"authorization":"role/scope" if not route.startswith("/internal") else "developer token",
        "telemetry":"OpenTelemetry + request metrics"} for method,route,owner in contracts]}


@router.get("/forecast", dependencies=[Depends(developer_guard)])
def forecast(db: Session=Depends(get_db)):
    rows=(db.query(models.ForecastEvaluation).filter_by(tenant_id=TENANT_ID)
          .order_by(models.ForecastEvaluation.forecast_at.desc()).limit(100).all())
    return {"evaluations":[{"work_order_id":r.work_order_id,"forecast_at":r.forecast_at,"horizon_seconds":r.horizon_seconds,
        "forecast_quantity":r.forecast_quantity,"actual":r.actual_eventual_quantity,"absolute_error":r.absolute_error,
        "percentage_error":r.percentage_error,"context":r.context} for r in rows]}


@router.get("/material-readiness", dependencies=[Depends(developer_guard)])
def material_readiness(db: Session=Depends(get_db)):
    rows=(db.query(models.MaterialReadinessSnapshot).filter_by(tenant_id=TENANT_ID)
          .order_by(models.MaterialReadinessSnapshot.calculated_at.desc()).limit(100).all())
    return {"snapshots":[{column.name:_iso(getattr(row,column.name)) for column in models.MaterialReadinessSnapshot.__table__.columns} for row in rows]}


@router.get("/policy", dependencies=[Depends(developer_guard)])
def policy(db: Session=Depends(get_db)):
    rows=db.query(models.OperationalScope).filter_by(tenant_id=TENANT_ID).all()
    return {"scopes":[{"membership_id":r.membership_id,"plants":r.plant_ids,"areas":r.area_ids,"lines":r.line_ids,
        "assets":r.asset_ids,"financial_visibility":r.financial_visibility,"authorities":r.authorities} for r in rows]}


@router.get("/errors", dependencies=[Depends(developer_guard)])
def errors(db: Session=Depends(get_db)):
    jobs=(db.query(models.IntegrationSyncJob).filter_by(tenant_id=TENANT_ID,status="failed")
          .order_by(models.IntegrationSyncJob.created_at.desc()).limit(100).all())
    events=(db.query(models.EventOutbox).filter(models.EventOutbox.tenant_id==TENANT_ID,
        models.EventOutbox.status.in_(("retry","dead_letter"))).order_by(models.EventOutbox.created_at.desc()).limit(100).all())
    return {"groups":[{"kind":"connector","id":r.id,"message":r.error,"at":r.created_at} for r in jobs]+[
        {"kind":"outbox","id":r.event_id,"message":r.last_error,"at":r.created_at,"trace_id":r.correlation_id} for r in events]}
