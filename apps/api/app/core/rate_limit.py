import hashlib
import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.metrics import LOGIN_THROTTLES

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - installation/runtime guard
    Redis = None
    RedisError = Exception


def _key(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _redis():
    if Redis is None:
        return None
    return Redis.from_url(get_settings().redis_url, decode_responses=True, socket_timeout=0.25)


def login_actor(request: Request, email: str) -> tuple[str, str]:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    return _key(email), _key(ip)


def enforce_login_rate_limit(request: Request, email: str) -> None:
    client = _redis()
    if client is None:
        return
    account, ip = login_actor(request, email)
    try:
        account_count = int(client.get(f"login:account:{account}") or 0)
        ip_count = int(client.get(f"login:ip:{ip}") or 0)
        if account_count >= 5 or ip_count >= 25:
            LOGIN_THROTTLES.labels("account" if account_count >= 5 else "ip").inc()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts; try again later",
                headers={"Retry-After": "900"},
            )
        if account_count:
            time.sleep(min(2.0, 0.25 * (2 ** (account_count - 1))))
    except RedisError:
        return


def enforce_recovery_rate_limit(request: Request, subject: str) -> None:
    client = _redis()
    if client is None:
        return
    account, ip = login_actor(request, subject)
    account_key = f"recovery:subject:{account}"
    ip_key = f"recovery:ip:{ip}"
    try:
        account_count = int(client.get(account_key) or 0)
        ip_count = int(client.get(ip_key) or 0)
        if account_count >= 5 or ip_count >= 20:
            LOGIN_THROTTLES.labels("recovery").inc()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many recovery attempts; try again later",
                headers={"Retry-After": "900"},
            )
        for key in (account_key, ip_key):
            value = client.incr(key)
            if value == 1:
                client.expire(key, 900)
    except RedisError:
        return


def record_login_result(request: Request, email: str, success: bool) -> None:
    client = _redis()
    if client is None:
        return
    account, ip = login_actor(request, email)
    try:
        if success:
            client.delete(f"login:account:{account}")
            return
        for key, ttl in ((f"login:account:{account}", 900), (f"login:ip:{ip}", 300)):
            value = client.incr(key)
            if value == 1:
                client.expire(key, ttl)
    except RedisError:
        return
