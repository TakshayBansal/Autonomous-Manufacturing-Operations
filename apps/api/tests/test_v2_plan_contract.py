from app.main import app
from app.celery_app import celery_app
from app.workers import REQUIRED_TASKS


REQUIRED_API = {
    ("GET", "/api/v2/me/context"),
    ("GET", "/api/v2/plants"),
    ("GET", "/api/v2/plants/{plant_id}/areas"),
    ("GET", "/api/v2/plants/{plant_id}/lines"),
    ("GET", "/api/v2/plants/{plant_id}/command-center"),
    ("GET", "/api/v2/plants/{plant_id}/operations/overview"),
    ("GET", "/api/v2/lines/{line_id}/workspace"),
    ("GET", "/api/v2/lines/{line_id}/timeline"),
    ("GET", "/api/v2/lines/{line_id}/loss-tree"),
    ("GET", "/api/v2/deviations"),
    ("GET", "/api/v2/deviations/{deviation_id}"),
    ("GET", "/api/v2/deviations/{deviation_id}/timeline"),
    ("GET", "/api/v2/deviations/{deviation_id}/evidence"),
    ("POST", "/api/v2/deviations/{deviation_id}/assign"),
    ("POST", "/api/v2/deviations/{deviation_id}/acknowledge"),
    ("POST", "/api/v2/deviations/{deviation_id}/resolve"),
    ("POST", "/api/v2/deviations/{deviation_id}/verify"),
    ("GET", "/api/v2/my-work"),
    ("GET", "/api/v2/actions/{action_id}"),
    ("POST", "/api/v2/actions/{action_id}/accept"),
    ("POST", "/api/v2/actions/{action_id}/start"),
    ("POST", "/api/v2/actions/{action_id}/wait"),
    ("POST", "/api/v2/actions/{action_id}/complete"),
    ("POST", "/api/v2/actions/{action_id}/evidence"),
    ("GET", "/api/v2/materials/readiness"),
    ("GET", "/api/v2/work-orders/{work_order_id}/material-readiness"),
    ("GET", "/api/v2/materials/{material_code}/risk"),
    ("GET", "/api/v2/value/summary"),
    ("GET", "/api/v2/deviations/{deviation_id}/value"),
    ("POST", "/api/v2/value/{entry_id}/verify"),
    ("GET", "/api/v2/gigi/briefing"),
    ("POST", "/api/v2/gigi/query"),
    ("POST", "/api/v2/gigi/prepare-action"),
    ("POST", "/api/v2/gigi/actions/{prepared_action_id}/execute"),
    ("GET", "/api/v2/gigi/activity"),
    ("GET", "/api/v2/integrations"),
    ("POST", "/api/v2/integrations"),
    ("POST", "/api/v2/integrations/{connection_id}/test"),
    ("POST", "/api/v2/integrations/{connection_id}/sync"),
    ("GET", "/api/v2/integrations/{connection_id}/health"),
    ("GET", "/api/v2/integrations/{connection_id}/mappings"),
    ("PUT", "/api/v2/integrations/{connection_id}/mappings"),
    ("GET", "/api/v2/stream"),
}


def test_hard_v2_api_contract_is_registered_without_generic_state_patch():
    # Router inclusion is deferred by the stable httpx2/Starlette bridge, so the
    # generated OpenAPI document is the authoritative public route registry.
    paths = app.openapi()["paths"]
    actual = {(method.upper(), path) for path, operations in paths.items()
              for method in operations if method.lower() in {
                  "get", "post", "put", "patch", "delete"}}
    assert REQUIRED_API <= actual
    forbidden = {
        (method, path) for method, path in actual
        if method == "PATCH" and (
            path.startswith("/api/v2/actions/") or
            path.startswith("/api/v2/deviations/"))
    }
    assert forbidden == set()


def test_hard_v2_worker_contract_uses_canonical_task_names():
    expected = {
        "app.workers.sync_connector",
        "app.workers.publish_outbox_event",
        "app.workers.reconcile_line_performance",
        "app.workers.recompute_material_readiness",
        "app.workers.evaluate_open_deviations",
        "app.workers.evaluate_action_slas",
        "app.workers.calculate_value_entries",
        "app.workers.generate_shift_briefing",
        "app.workers.generate_shift_handover",
        "app.workers.index_knowledge_document",
        "app.workers.run_agent",
    }
    assert expected <= REQUIRED_TASKS
    assert expected <= set(celery_app.tasks)
