from sqlalchemy.orm import Session

from app.db import models

AGENTIC_FLAGS = {
    "agentic_procurement_cycles", "prepared_work", "opa_governance",
    "sandbox_execution", "async_specialists", "manager_cockpit", "autonomy_centre",
    "temporal_procurement_workflow", "tier2_automation", "tier3_automation",
    "proactive_companion",
    "scm_control_tower",
}


def enabled(db: Session, tenant_id: str, key: str, default: bool = False) -> bool:
    if key not in AGENTIC_FLAGS:
        raise ValueError("Unknown agentic feature flag")
    row = db.query(models.TenantFeatureFlag).filter_by(tenant_id=tenant_id, key=key).first()
    if row is not None:
        return row.enabled
    tenant = db.get(models.Tenant, tenant_id)
    return bool((tenant.feature_flags or {}).get(key, default)) if tenant else default
