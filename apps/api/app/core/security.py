import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db import models
from app.core.config import get_settings

password_hasher = PasswordHasher()
SESSION_COOKIE = "gg_session"
CSRF_HEADER = "x-csrf-token"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def seal_secret(value: str) -> str:
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().session_secret.encode()).digest())
    return Fernet(key).encrypt(value.encode()).decode()


def unseal_secret(value: str) -> str:
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().session_secret.encode()).digest())
    return Fernet(key).decrypt(value.encode()).decode()


def verify_mfa_code(account: models.Account, code: str | None) -> bool:
    if not account.mfa_enabled:
        return True
    if not code:
        return False
    normalized = code.replace(" ", "").replace("-", "")
    if account.mfa_secret_encrypted:
        import pyotp

        if pyotp.TOTP(unseal_secret(account.mfa_secret_encrypted)).verify(normalized, valid_window=1):
            return True
    candidate_hash = token_hash(normalized)
    if candidate_hash in account.backup_code_hashes:
        account.backup_code_hashes = [item for item in account.backup_code_hashes if item != candidate_hash]
        return True
    return False


def membership_for_user(db: Session, user: models.User) -> models.WorkspaceMembership | None:
    return (
        db.query(models.WorkspaceMembership)
        .filter(
            models.WorkspaceMembership.user_id == user.id,
            models.WorkspaceMembership.tenant_id == user.tenant_id,
            models.WorkspaceMembership.status == "active",
        )
        .first()
    )


def create_session(db: Session, response: Response, user: models.User) -> dict:
    settings = get_settings()
    now = now_utc()
    db.query(models.AuthSession).filter(
        models.AuthSession.user_id == user.id,
        models.AuthSession.revoked_at.is_(None),
    ).update({models.AuthSession.revoked_at: now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(40)
    csrf_token = secrets.token_urlsafe(32)
    membership = membership_for_user(db, user)
    session = models.AuthSession(
        id=f"sess-{secrets.token_hex(12)}",
        tenant_id=user.tenant_id,
        plant_id=user.plant_id,
        user_id=user.id,
        account_id=membership.account_id if membership else user.account_id,
        membership_id=membership.id if membership else None,
        token_hash=token_hash(raw_token),
        csrf_token=csrf_token,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session)
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
    )
    return {"csrf_token": csrf_token, "session_id": session.id, "membership_id": session.membership_id}


def clear_session(db: Session, request: Request, response: Response) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        session = (
            db.query(models.AuthSession)
            .filter(models.AuthSession.token_hash == token_hash(raw_token), models.AuthSession.revoked_at.is_(None))
            .first()
        )
        if session:
            session.revoked_at = now_utc()
    settings = get_settings()
    response.delete_cookie(SESSION_COOKIE, secure=settings.secure_cookies, samesite=settings.cookie_samesite)


def current_session(db: Session, request: Request) -> models.AuthSession:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    session = (
        db.query(models.AuthSession)
        .filter(models.AuthSession.token_hash == token_hash(raw_token), models.AuthSession.revoked_at.is_(None))
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if session.expires_at.replace(tzinfo=timezone.utc) < now_utc():
        session.revoked_at = now_utc()
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return session


def current_user(db: Session, request: Request) -> models.User:
    session = current_session(db, request)
    user = db.get(models.User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
    db.info["actor_membership_id"] = session.membership_id
    return user


def current_membership(db: Session, request: Request) -> models.WorkspaceMembership:
    session = current_session(db, request)
    membership = db.get(models.WorkspaceMembership, session.membership_id) if session.membership_id else None
    if membership is None:
        user = db.get(models.User, session.user_id)
        membership = membership_for_user(db, user) if user else None
        if membership:
            session.membership_id = membership.id
            session.account_id = membership.account_id
    if membership is None or membership.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace membership unavailable")
    return membership


def select_membership(db: Session, request: Request, membership_id: str) -> models.User:
    session = current_session(db, request)
    membership = db.get(models.WorkspaceMembership, membership_id)
    if membership is None or membership.status != "active" or membership.account_id != session.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace membership access denied")
    user = db.get(models.User, membership.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace user unavailable")
    session.membership_id = membership.id
    session.user_id = user.id
    session.tenant_id = membership.tenant_id
    session.plant_id = membership.default_plant_id
    session.csrf_token = secrets.token_urlsafe(32)
    return user


def require_csrf(db: Session, request: Request) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    session = current_session(db, request)
    supplied = request.headers.get(CSRF_HEADER)
    if not supplied or supplied != session.csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def record_login_attempt(db: Session, email: str, success: bool) -> None:
    email_key = email.lower().strip()
    attempt = db.get(models.LoginAttempt, email_key)
    if attempt is None:
        attempt = models.LoginAttempt(email=email_key, failed_count=0)
        db.add(attempt)
    if success:
        attempt.failed_count = 0
        attempt.locked_until = None
    else:
        attempt.failed_count += 1
        if attempt.failed_count >= 5:
            attempt.locked_until = now_utc() + timedelta(minutes=15)
    attempt.last_attempt_at = now_utc()


def ensure_not_locked(db: Session, email: str) -> None:
    attempt = db.get(models.LoginAttempt, email.lower().strip())
    if attempt and attempt.locked_until and attempt.locked_until.replace(tzinfo=timezone.utc) > now_utc():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account temporarily locked")
