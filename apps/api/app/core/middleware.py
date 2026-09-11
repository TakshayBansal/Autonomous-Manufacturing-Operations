import hashlib
import json
import logging
import secrets
import time
import re
from datetime import datetime, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.security import SESSION_COOKIE, token_hash
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.eventing import correlation_context

logger = logging.getLogger("genuinegigs.request")

IDEMPOTENCY_EXEMPT_PATHS = {"/auth/login", "/auth/logout"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_PATH = re.compile(r"(/supplier/(?:rfqs|pos)/)[^/]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_path(path: str) -> str:
    return SENSITIVE_PATH.sub(r"\1[redacted]", path)


def _actor_scope(request: Request, db) -> tuple[str, str]:
    raw_session = request.cookies.get(SESSION_COOKIE)
    if raw_session:
        session = db.query(models.AuthSession).filter(
            models.AuthSession.token_hash == token_hash(raw_session),
            models.AuthSession.revoked_at.is_(None),
        ).first()
        if session:
            return session.tenant_id, f"user:{session.user_id}"
    path_fingerprint = hashlib.sha256(request.url.path.encode("utf-8")).hexdigest()
    return "external", f"external:{path_fingerprint}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in UNSAFE_METHODS or request.url.path in IDEMPOTENCY_EXEMPT_PATHS:
            return await call_next(request)

        key = request.headers.get("idempotency-key", "").strip()
        if not key:
            return JSONResponse(status_code=428, content={"detail": "Idempotency-Key header is required"})
        if len(key) > 160:
            return JSONResponse(status_code=422, content={"detail": "Idempotency-Key is too long"})

        body = await request.body()
        request_hash = hashlib.sha256(request.method.encode() + request.url.path.encode() + body).hexdigest()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # Starlette request body replay for downstream form/json parsing.

        with SessionLocal() as db:
            tenant_id, actor_key = _actor_scope(request, db)
            existing = db.query(models.IdempotencyRecord).filter_by(actor_key=actor_key, idempotency_key=key).first()
            if existing:
                if existing.request_hash != request_hash:
                    return JSONResponse(status_code=409, content={"detail": "Idempotency key was already used with another request"})
                if existing.status == "completed" and existing.response_status is not None:
                    replay_headers = {"Idempotency-Replayed": "true"}
                    if isinstance(existing.response_body, dict) and isinstance(existing.response_body.get("version"), int):
                        replay_headers["ETag"] = f'"{existing.response_body["version"]}"'
                    return JSONResponse(
                        status_code=existing.response_status,
                        content=existing.response_body,
                        headers=replay_headers,
                    )
                return JSONResponse(status_code=409, content={"detail": "An identical request is already processing"})
            record = models.IdempotencyRecord(
                tenant_id=tenant_id,
                actor_key=actor_key,
                idempotency_key=key,
                method=request.method,
                path=request.url.path,
                request_hash=request_hash,
            )
            db.add(record)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return JSONResponse(status_code=409, content={"detail": "An identical request is already processing"})

        try:
            response = await call_next(request)
            response_body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                stored_body = json.loads(response_body.decode("utf-8")) if response_body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                stored_body = {"detail": "Non-JSON response"}

            with SessionLocal() as db:
                persisted = db.get(models.IdempotencyRecord, record.id)
                if persisted:
                    if response.status_code < 500:
                        persisted.status = "completed"
                        persisted.response_status = response.status_code
                        persisted.response_body = stored_body
                        persisted.completed_at = _utcnow()
                    else:
                        db.delete(persisted)
                    db.commit()

            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers["Idempotency-Replayed"] = "false"
            if isinstance(stored_body, dict) and isinstance(stored_body.get("version"), int):
                headers["ETag"] = f'"{stored_body["version"]}"'
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
                background=response.background,
            )
        except Exception:
            with SessionLocal() as db:
                persisted = db.get(models.IdempotencyRecord, record.id)
                if persisted:
                    db.delete(persisted)
                    db.commit()
            raise


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("x-correlation-id") or f"REQ-{secrets.token_hex(8).upper()}"
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        token = correlation_context.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_context.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        duration = time.perf_counter() - started
        safe_path = _safe_path(request.url.path)
        HTTP_REQUESTS.labels(request.method, safe_path, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, safe_path).observe(duration)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": safe_path,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                }
            )
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser hardening uniformly, including error responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        response.headers.setdefault("Cache-Control", "no-store")
        if get_settings().secure_cookies:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
