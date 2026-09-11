from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "genuinegigs", broker=settings.redis_url, backend=settings.redis_url,
    include=["app.workers"],
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.process_document": {"queue": "documents"},
        "app.workers.dispatch_integration": {"queue": "integrations"},
        "app.workers.send_email": {"queue": "email"},
        "app.workers.run_sync_job": {"queue": "sync"},
        "app.workers.sync_factory_simulators": {"queue": "sync"},
        "app.workers.apply_simulated_recovery_strategy": {"queue": "sync"},
        "app.workers.import_master_data": {"queue": "sync"},
        "app.workers.enforce_retention": {"queue": "sync"},
        "app.workers.dispatch_domain_event": {"queue": "events"},
        "app.workers.evaluate_active_cycles": {"queue": "events"},
        "app.workers.run_specialist": {"queue": "specialists"},
        "app.workers.reconcile_line_performance": {"queue": "events"},
        "app.workers.recompute_material_readiness": {"queue": "events"},
        "app.workers.recompute_v2_material_readiness": {"queue": "events"},
        "app.workers.evaluate_open_deviations": {"queue": "events"},
        "app.workers.evaluate_action_slas": {"queue": "events"},
        "app.workers.reconcile_operational_snapshots": {"queue": "events"},
        "app.workers.log_forecast_evaluations": {"queue": "events"},
        "app.workers.generate_shift_briefing": {"queue": "events"},
        "app.workers.generate_shift_handover": {"queue": "events"},
        "app.workers.index_knowledge_document": {"queue": "documents"},
        "app.workers.run_agent": {"queue": "specialists"},
        "app.workers.run_v2_agent": {"queue": "specialists"},
        "app.workers.run_scm_planning": {"queue": "scm"},
        "app.workers.dispatch_queued_scm_runs": {"queue": "scm"},
        "app.workers.evaluate_gigi_insights": {"queue": "events"},
        "app.workers.evaluate_operational_commitments": {"queue": "events"},
        "app.workers.monitor_case_recovery": {"queue": "events"},
    },
    beat_schedule={
        'internal-task-followups': {'task': 'app.workers.run_internal_followups', 'schedule': 300.0},
        "recover-queued-jobs": {"task": "app.workers.recover_queued_jobs", "schedule": 60.0},
        "enforce-retention": {"task": "app.workers.enforce_retention", "schedule": 86400.0},
        # Procurement handoffs are user-facing live events. Keep the durable
        # outbox, but drain it frequently enough that the next owner sees the
        # companion CTA without refreshing the page.
        "dispatch-domain-events": {"task": "app.workers.dispatch_pending_domain_events", "schedule": 2.0},
        "evaluate-active-cycles": {"task": "app.workers.evaluate_active_cycles", "schedule": 900.0},
        "cleanup-sandboxes": {"task": "app.workers.cleanup_sandboxes", "schedule": 300.0},
        "v2-action-slas": {"task": "app.workers.evaluate_all_v2_action_slas", "schedule": 60.0},
        "v2-line-reconciliation": {"task": "app.workers.reconcile_all_v2_lines", "schedule": 300.0},
        "v2-material-readiness": {"task": "app.workers.recompute_all_v2_material_readiness", "schedule": 900.0},
        "northstar-factory-streams": {"task": "app.workers.sync_factory_simulators", "schedule": 2.0,
                                      "options": {"expires": 2.0}},
        "v2-operational-state-and-recovery": {"task": "app.workers.reconcile_operational_snapshots", "schedule": 60.0},
        "v2-forecast-evaluation-log": {"task": "app.workers.log_forecast_evaluations", "schedule": 300.0},
        "scm-queued-planning-runs": {"task": "app.workers.dispatch_queued_scm_runs", "schedule": 5.0},
        "gigi-proactive-case-evaluation": {"task": "app.workers.evaluate_gigi_insights", "schedule": 60.0},
        "gigi-durable-commitments": {"task": "app.workers.evaluate_operational_commitments", "schedule": 60.0},
        "case-stability-verification": {"task": "app.workers.monitor_case_recovery", "schedule": 300.0},
    },
)
from app.telemetry import configure_celery
configure_celery()
