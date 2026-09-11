import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import agent_service
from app.agent_schemas import (
    InvitationAcceptRequest,
    InvitationCreateRequest,
    MfaVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
)
from app.core.config import get_settings
from app.core.permissions import ADMIN, require_workspace_capability, workspace_capabilities
from app.core.rate_limit import enforce_recovery_rate_limit
from app.core.security import (
    current_session,
    current_user,
    hash_password,
    require_csrf,
    seal_secret,
    token_hash,
    unseal_secret,
    verify_mfa_code,
)
from app.db import models
from app.db.session import get_db
from app.domains import workflows


router = APIRouter()


def authenticated_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    return current_user(db, request)


def csrf_guard(request: Request, db: Session = Depends(get_db)) -> None:
    require_csrf(db, request)


def account_for_session(db: Session, request: Request) -> models.Account:
    session = current_session(db, request)
    account = db.get(models.Account, session.account_id) if session.account_id else None
    if account is None:
        raise HTTPException(status_code=409, detail="Account migration is incomplete")
    return account


@router.get("/auth/sessions")
def list_sessions(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    session = current_session(db, request)
    records = db.query(models.AuthSession).filter_by(
        account_id=session.account_id
    ).order_by(models.AuthSession.created_at.desc()).all()
    return [{
        "id": item.id,
        "membership_id": item.membership_id,
        "tenant_id": item.tenant_id,
        "plant_id": item.plant_id,
        "created_at": item.created_at,
        "expires_at": item.expires_at,
        "revoked_at": item.revoked_at,
        "current": item.id == session.id,
    } for item in records]


@router.delete("/auth/sessions/{session_id}", dependencies=[Depends(csrf_guard)])
def revoke_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    current = current_session(db, request)
    target = db.query(models.AuthSession).filter_by(
        id=session_id, account_id=current.account_id
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Session not found")
    target.revoked_at = datetime.now(timezone.utc)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "auth.session.revoked",
        "auth_session", target.id, actor_user_id=user.id,
    )
    db.commit()
    return {"status": "revoked"}


@router.post("/auth/mfa/enroll", dependencies=[Depends(csrf_guard)])
def enroll_mfa(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    import pyotp

    account = account_for_session(db, request)
    secret = pyotp.random_base32()
    account.mfa_secret_encrypted = seal_secret(secret)
    account.mfa_enabled = False
    uri = pyotp.TOTP(secret).provisioning_uri(name=account.email, issuer_name="GenuineGigs")
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "auth.mfa.enrollment_started",
        "account", account.id, actor_user_id=user.id,
    )
    db.commit()
    return {"secret": secret, "provisioning_uri": uri}


@router.post("/auth/mfa/confirm", dependencies=[Depends(csrf_guard)])
def confirm_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    import pyotp

    account = account_for_session(db, request)
    if not account.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="Start MFA enrollment first")
    secret = unseal_secret(account.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=422, detail="Invalid MFA code")
    backup_codes = [secrets.token_hex(5) for _ in range(8)]
    account.backup_code_hashes = [token_hash(code) for code in backup_codes]
    account.mfa_enabled = True
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "auth.mfa.enabled",
        "account", account.id, actor_user_id=user.id,
    )
    db.commit()
    return {"status": "enabled", "backup_codes": backup_codes}


@router.post("/auth/mfa/disable", dependencies=[Depends(csrf_guard)])
def disable_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    account = account_for_session(db, request)
    if not verify_mfa_code(account, payload.code):
        raise HTTPException(status_code=422, detail="Invalid MFA code")
    account.mfa_enabled = False
    account.mfa_secret_encrypted = None
    account.backup_code_hashes = []
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "auth.mfa.disabled",
        "account", account.id, actor_user_id=user.id,
    )
    db.commit()
    return {"status": "disabled"}


@router.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    enforce_recovery_rate_limit(request, email)
    account = db.query(models.Account).filter_by(email=email).first()
    raw_token = None
    if account:
        db.query(models.IdentityToken).filter_by(
            account_id=account.id, purpose="password_reset", used_at=None
        ).update({models.IdentityToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)
        raw_token = secrets.token_urlsafe(40)
        db.add(models.IdentityToken(
            account_id=account.id, email=email, purpose="password_reset",
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
    db.commit()
    response = {"status": "accepted"}
    if raw_token and get_settings().app_env in {"development", "test"}:
        response["development_token"] = raw_token
    return response


@router.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest, request: Request, db: Session = Depends(get_db)):
    enforce_recovery_rate_limit(request, payload.token)
    record = db.query(models.IdentityToken).filter_by(
        token_hash=token_hash(payload.token), purpose="password_reset", used_at=None
    ).first()
    now = datetime.now(timezone.utc)
    if record is None or record.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=422, detail="Recovery token is invalid or expired")
    account = db.get(models.Account, record.account_id)
    if account is None:
        raise HTTPException(status_code=422, detail="Recovery token is invalid or expired")
    new_hash = hash_password(payload.password)
    account.password_hash = new_hash
    db.query(models.User).filter_by(account_id=account.id).update(
        {models.User.password_hash: new_hash}, synchronize_session=False
    )
    db.query(models.AuthSession).filter_by(account_id=account.id, revoked_at=None).update(
        {models.AuthSession.revoked_at: now}, synchronize_session=False
    )
    record.used_at = now
    db.commit()
    return {"status": "password_updated"}


ROLE_DEPARTMENT = {
    'plant_manager': 'Plant Leadership',
    'purchase_manager': 'Procurement',
    'purchase_executive': 'Procurement',
    'gate_operator': 'Gate and Security',
    'store_manager': 'Stores',
    'quality_inspector': 'Quality',
    'admin': 'Plant Leadership',
}


def queue_invitation_email(
    db: Session, user: models.User, invitation: models.WorkspaceInvitation, raw_token: str
) -> None:
    correlation = f'INV-{secrets.token_hex(6)}'
    accept_url = f"{get_settings().web_base_url.rstrip('/')}/accept-invitation?token={raw_token}"
    body = (
        f'You have been invited to GenuineGigs as {invitation.role.replace("_", " ").title()}. '
        f'Accept this one-time invitation within seven days: {accept_url}'
    )
    db.add(models.OutboxMessage(
        tenant_id=user.tenant_id, plant_id=user.plant_id, channel='email',
        recipient=invitation.email, subject='Your GenuineGigs workspace invitation',
        body=body, status='approved_pending_send',
        payload_hash=hashlib.sha256(body.encode()).hexdigest(),
        correlation_id=correlation,
        idempotency_key=f'workspace-invite-{invitation.id}-{invitation.expires_at.isoformat()}',
        approved_by_user_id=user.id, approved_at=datetime.now(timezone.utc),
        meta={'invitation_id': invitation.id, 'expires_at': invitation.expires_at.isoformat()},
    ))


@router.get('/workspace/invitations')
def list_invitations(
    db: Session = Depends(get_db), user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_members')
    records = db.query(models.WorkspaceInvitation).filter_by(
        tenant_id=user.tenant_id
    ).order_by(models.WorkspaceInvitation.created_at.desc()).all()
    return [{
        'id': row.id, 'email': row.email, 'role': row.role, 'status': row.status,
        'department_id': row.department_id, 'plant_ids': row.plant_ids,
        'manager_membership_id': row.manager_membership_id,
        'expires_at': row.expires_at, 'accepted_at': row.accepted_at,
    } for row in records]


@router.get('/workspace/setup')
def workspace_setup(
    db: Session = Depends(get_db), user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.view_setup')
    tenant = db.get(models.Tenant, user.tenant_id)
    memberships = db.query(models.WorkspaceMembership).filter_by(
        tenant_id=user.tenant_id, status='active'
    ).all()
    roles = {row.role for row in memberships}
    required_roles = {
        'plant_manager', 'purchase_manager', 'purchase_executive',
        'gate_operator', 'store_manager', 'quality_inspector',
    }
    item_count = workflows.user_scope_query(db, models.Item, user).count()
    supplier_count = workflows.user_scope_query(db, models.Supplier, user).count()
    if required_roles.issubset(roles) and item_count and supplier_count:
        onboarding_status = 'complete'
    elif not required_roles.issubset(roles):
        onboarding_status = 'needs_team'
    else:
        onboarding_status = 'needs_master_data'
    departments = db.query(models.Department).filter_by(tenant_id=user.tenant_id, plant_id=user.plant_id).all()
    return {
        'onboarding_status': onboarding_status, 'capabilities': workspace_capabilities(db, user),
        'required_roles': sorted(required_roles), 'active_roles': sorted(roles),
        'item_count': item_count, 'supplier_count': supplier_count,
        'agent_enabled': bool(tenant and tenant.agent_enabled),
        'departments': [{'id': row.id, 'name': row.name} for row in departments],
        'members': [{
            'membership_id': row.id, 'role': row.role,
            'name': db.get(models.User, row.user_id).name,
            'manager_membership_id': row.manager_membership_id,
        } for row in memberships],
    }


@router.post("/workspace/invitations", dependencies=[Depends(csrf_guard)])
def create_invitation(
    payload: InvitationCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_members')
    plant_ids = payload.plant_ids or [user.plant_id]
    department = db.get(models.Department, payload.department_id) if payload.department_id else db.query(models.Department).filter_by(
        tenant_id=user.tenant_id, plant_id=user.plant_id,
        name=ROLE_DEPARTMENT.get(payload.role, 'Plant Leadership'),
    ).first()
    if department is None or department.tenant_id != user.tenant_id:
        raise HTTPException(status_code=422, detail='Department not found')
    authorized_plants = {
        row.plant_id for row in db.query(models.UserPlantAccess).filter_by(
            tenant_id=user.tenant_id, user_id=user.id
        ).all()
    }
    if not set(plant_ids).issubset(authorized_plants):
        raise HTTPException(status_code=403, detail="Plant administration access denied")
    if payload.manager_membership_id:
        manager = db.get(models.WorkspaceMembership, payload.manager_membership_id)
        if manager is None or manager.tenant_id != user.tenant_id:
            raise HTTPException(status_code=422, detail="Manager membership not found")
    allowed_roles = set(ROLE_DEPARTMENT)
    if payload.role not in allowed_roles:
        raise HTTPException(status_code=422, detail='Choose a supported workspace role')
    existing = db.query(models.WorkspaceInvitation).filter_by(
        tenant_id=user.tenant_id, email=payload.email.lower().strip(), status='pending'
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail='A pending invitation already exists for this email')
    raw_token = secrets.token_urlsafe(40)
    invitation = models.WorkspaceInvitation(
        tenant_id=user.tenant_id,
        email=payload.email.lower().strip(),
        role=payload.role,
        department_id=department.id,
        plant_ids=plant_ids,
        manager_membership_id=payload.manager_membership_id,
        token_hash=token_hash(raw_token),
        status="pending",
        invited_by_membership_id=db.query(models.WorkspaceMembership).filter_by(
            tenant_id=user.tenant_id, user_id=user.id
        ).first().id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.flush()
    queue_invitation_email(db, user, invitation, raw_token)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, "workspace.invitation.created",
        "workspace_invitation", invitation.id, actor_user_id=user.id,
        meta={"email_hash": hashlib.sha256(invitation.email.encode()).hexdigest(),
              "role": invitation.role, "plant_ids": invitation.plant_ids},
    )
    db.commit()
    response = {"id": invitation.id, "status": invitation.status, "expires_at": invitation.expires_at}
    if get_settings().app_env in {"development", "test"}:
        response["development_token"] = raw_token
    return response


@router.post('/workspace/invitations/{invitation_id}/resend', dependencies=[Depends(csrf_guard)])
def resend_invitation(
    invitation_id: str, db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_members')
    invitation = db.query(models.WorkspaceInvitation).filter_by(
        id=invitation_id, tenant_id=user.tenant_id, status='pending'
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail='Pending invitation not found')
    raw_token = secrets.token_urlsafe(40)
    invitation.token_hash = token_hash(raw_token)
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    queue_invitation_email(db, user, invitation, raw_token)
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'workspace.invitation.resent',
        'workspace_invitation', invitation.id, actor_user_id=user.id,
    )
    db.commit()
    response = {'id': invitation.id, 'status': invitation.status, 'expires_at': invitation.expires_at}
    if get_settings().app_env in {'development', 'test'}:
        response['development_token'] = raw_token
    return response


@router.delete('/workspace/invitations/{invitation_id}', dependencies=[Depends(csrf_guard)])
def revoke_invitation(
    invitation_id: str, db: Session = Depends(get_db),
    user: models.User = Depends(authenticated_user),
):
    require_workspace_capability(db, user, 'workspace.manage_members')
    invitation = db.query(models.WorkspaceInvitation).filter_by(
        id=invitation_id, tenant_id=user.tenant_id, status='pending'
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail='Pending invitation not found')
    invitation.status = 'revoked'
    workflows.create_audit(
        db, user.tenant_id, user.plant_id, user.name, 'workspace.invitation.revoked',
        'workspace_invitation', invitation.id, actor_user_id=user.id,
    )
    db.commit()
    return {'id': invitation.id, 'status': invitation.status}


@router.post("/workspace/invitations/accept")
def accept_invitation(payload: InvitationAcceptRequest, request: Request, db: Session = Depends(get_db)):
    enforce_recovery_rate_limit(request, payload.token)
    invitation = db.query(models.WorkspaceInvitation).filter_by(
        token_hash=token_hash(payload.token), status="pending"
    ).first()
    now = datetime.now(timezone.utc)
    if invitation is None or invitation.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=422, detail="Invitation is invalid or expired")
    account = db.query(models.Account).filter_by(email=invitation.email).first()
    if account is None:
        account = models.Account(
            id=workflows.next_id(db, models.Account, "ACCT"),
            email=invitation.email, name=payload.name,
            password_hash=hash_password(payload.password), email_verified_at=now,
        )
        db.add(account)
        db.flush()
    if db.query(models.WorkspaceMembership).filter_by(
        account_id=account.id, tenant_id=invitation.tenant_id
    ).first():
        raise HTTPException(status_code=409, detail="Account already belongs to this workspace")
    plant_id = invitation.plant_ids[0]
    suffix = secrets.token_hex(5)
    user = models.User(
        id=f"usr-{suffix}", account_id=account.id, tenant_id=invitation.tenant_id,
        plant_id=plant_id, department_id=invitation.department_id, name=payload.name,
        email=f"{suffix}+{account.email}", role=invitation.role,
        password_hash=account.password_hash,
    )
    membership = models.WorkspaceMembership(
        id=f"mem-{suffix}", account_id=account.id, tenant_id=invitation.tenant_id,
        user_id=user.id, default_plant_id=plant_id, plant_ids=invitation.plant_ids,
        department_id=invitation.department_id, role=invitation.role,
        manager_membership_id=invitation.manager_membership_id,
        permissions=[], status="active",
    )
    db.add_all([user, membership])
    for index, allowed_plant in enumerate(invitation.plant_ids):
        db.add(models.UserPlantAccess(
            id=f"upa-{suffix}-{index}", tenant_id=invitation.tenant_id,
            user_id=user.id, plant_id=allowed_plant, is_default=index == 0,
        ))
    tenant = db.get(models.Tenant, invitation.tenant_id)
    db.add(models.AgentProfile(
        id=f"agt-{suffix}", tenant_id=invitation.tenant_id, plant_id=plant_id,
        user_id=user.id, membership_id=membership.id, role=invitation.role,
        display_name=f"{payload.name.split(' ')[0]}'s {invitation.role.replace('_', ' ').title()} Agent",
        allowed_actions=agent_service.ROLE_DRAFT_TOOLS.get(invitation.role, ["explain_task"]),
        blocked_actions=agent_service.RESTRICTED_ACTIONS,
        prompt_version=f"{invitation.role}-playbook@1", policy_version="agent-policy@1",
        provider="groq", model_profile=get_settings().agent_primary_model,
        enabled=bool(tenant and tenant.agent_enabled and get_settings().agent_enabled),
        escalation_policy={"manager_membership_id": invitation.manager_membership_id},
    ))
    invitation.status = "accepted"
    invitation.accepted_at = now
    workflows.create_audit(
        db, invitation.tenant_id, plant_id, payload.name, "workspace.invitation.accepted",
        "workspace_membership", membership.id, actor_user_id=user.id,
        meta={"invitation_id": invitation.id, "account_id": account.id},
    )
    db.commit()
    return {'status': 'accepted', 'membership_id': membership.id, 'email': account.email}
