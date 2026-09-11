from fastapi import HTTPException, status

from app.db import models

WORKSPACE_OWNER = 'workspace.owner'
WORKSPACE_CAPABILITIES = {
    'workspace.manage_members',
    'workspace.manage_master_data',
    'workspace.manage_agents',
    'workspace.view_setup',
}

PLANT_MANAGER = "plant_manager"
PURCHASE_MANAGER = "purchase_manager"
PURCHASE_EXECUTIVE = "purchase_executive"
GATE_OPERATOR = "gate_operator"
STORE_MANAGER = "store_manager"
QUALITY_INSPECTOR = "quality_inspector"
SCM_PLANNER = "scm_planner"
ADMIN = "admin"


def require_role(user: models.User, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {user.role} is not allowed for this action",
        )


def assert_same_scope(user: models.User, tenant_id: str, plant_id: str | None = None) -> None:
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    if plant_id and user.plant_id != plant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Plant access denied")


def workspace_membership(db, user: models.User) -> models.WorkspaceMembership | None:
    return db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, user_id=user.id, status='active'
    ).first()


def workspace_capabilities(db, user: models.User) -> list[str]:
    membership = workspace_membership(db, user)
    permissions = set(membership.permissions or []) if membership else set()
    if user.role == ADMIN or WORKSPACE_OWNER in permissions:
        permissions.update(WORKSPACE_CAPABILITIES)
    return sorted(permissions)


def require_workspace_capability(db, user: models.User, capability: str) -> None:
    if capability not in workspace_capabilities(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'Workspace capability {capability} is required',
        )


READ_ROLES = {
    "procurement": {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, ADMIN},
    "po": {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, GATE_OPERATOR, STORE_MANAGER, QUALITY_INSPECTOR, ADMIN},
    "inbound": {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, GATE_OPERATOR, STORE_MANAGER, QUALITY_INSPECTOR, ADMIN},
    "documents": {PLANT_MANAGER, PURCHASE_MANAGER, PURCHASE_EXECUTIVE, QUALITY_INSPECTOR, ADMIN},
    "audit": {PLANT_MANAGER, ADMIN},
    "integrations": {PURCHASE_MANAGER, ADMIN},
    "admin": {ADMIN},
}


def require_read_role(user: models.User, resource: str) -> None:
    allowed = READ_ROLES.get(resource)
    if allowed is not None and user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Role {user.role} cannot read {resource}")
