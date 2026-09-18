import hashlib
import ipaddress
import os
import re
from datetime import datetime

import jwt
from fastapi import Request
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .auth.config import SECRET
from .auth.models import RefreshToken, User
from .database import SessionLocal, now


AUTHENTICATED_LIMIT = 120
UNAUTHENTICATED_LIMIT = 60
UPLOAD_LIMIT = 10
EXPORT_LIMIT = 20
GENERAL_WINDOW_SECONDS = 60
UPLOAD_PATH = re.compile(r'^/api/notes/[^/]+/attachments$')
EXPORT_PATH = re.compile(r'^/api/notes/[^/]+/export$')


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__(retry_after)
        self.retry_after = retry_after


def parse_trusted_proxy_networks(value: str):
    networks = tuple(
        ipaddress.ip_network(item.strip(), strict=False)
        for item in value.split(',')
        if item.strip()
    )
    if any(network.prefixlen == 0 for network in networks):
        raise ValueError('TRUSTED_PROXY_IPS cannot contain a universal network')
    return networks


TRUSTED_PROXY_NETWORKS = parse_trusted_proxy_networks(os.getenv('TRUSTED_PROXY_IPS', ''))


def bucket_key(scope: str, identity: str) -> str:
    return hashlib.sha256(f'{scope}:{identity}'.encode()).hexdigest()


def rate_limit_clock() -> datetime | None:
    return None


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else 'unknown'
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_address in network for network in TRUSTED_PROXY_NETWORKS):
        return peer

    forwarded = [value.strip() for value in request.headers.get('x-forwarded-for', '').split(',') if value.strip()]
    if not forwarded:
        return peer
    try:
        addresses = [ipaddress.ip_address(value) for value in forwarded]
    except ValueError:
        return peer
    for address in reversed(addresses):
        if not any(address in network for network in TRUSTED_PROXY_NETWORKS):
            return str(address)
    return peer


def authenticated_user_id(request: Request) -> int | None:
    authorization = request.headers.get('authorization', '')
    scheme, separator, raw = authorization.partition(' ')
    if not separator or scheme.lower() != 'bearer' or not raw:
        return None
    try:
        claims = jwt.decode(
            raw,
            SECRET,
            algorithms=['HS256'],
            issuer='minutes',
            audience='minutes',
            options={'require': ['exp', 'sub', 'sid', 'ver', 'type']},
        )
        with SessionLocal() as session:
            user = session.get(User, int(claims['sub']))
            token = session.get(RefreshToken, claims['sid'])
            if (
                claims['type'] != 'access'
                or not user
                or user.token_version != claims['ver']
                or not token
                or token.user_id != user.id
                or token.revoked_at
                or token.expires_at <= now()
            ):
                return None
            return user.id
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def consume(
    *,
    scope: str,
    identity: str,
    maximum: int,
    window_seconds: int,
    current_time: datetime | None = None,
) -> None:
    timestamp = current_time if current_time is not None else rate_limit_clock()
    with SessionLocal.begin() as session:
        session.execute(
            text("""
INSERT INTO auth_rate_limits (key, hits, expires_at)
VALUES (:key, 0, '-infinity'::TIMESTAMPTZ)
ON CONFLICT (key) DO NOTHING
"""),
            {'key': bucket_key(scope, identity)},
        )
        hits, retry_after = session.execute(
            text("""
WITH locked AS MATERIALIZED (
    SELECT key
    FROM auth_rate_limits
    WHERE key = :key
    FOR UPDATE
),
current AS MATERIALIZED (
    SELECT COALESCE(CAST(:current_time AS TIMESTAMPTZ), clock_timestamp()) AS value
    FROM locked
)
UPDATE auth_rate_limits AS bucket
SET hits = CASE
    WHEN bucket.expires_at <= current.value
        THEN 1
    ELSE bucket.hits + 1
END,
expires_at = CASE
    WHEN bucket.expires_at <= current.value
        THEN current.value + (:window_seconds * INTERVAL '1 second')
    ELSE bucket.expires_at
END
FROM current
WHERE bucket.key = :key
RETURNING bucket.hits, GREATEST(
    0,
    CEIL(EXTRACT(EPOCH FROM bucket.expires_at - current.value))
)::INTEGER
"""),
            {
                'key': bucket_key(scope, identity),
                'current_time': timestamp,
                'window_seconds': window_seconds,
            },
        ).one()
    if hits > maximum:
        raise RateLimitExceeded(retry_after)


def enforce_api_rate_limit(request: Request) -> None:
    user_id = authenticated_user_id(request)
    identity = f'user:{user_id}' if user_id is not None else f'ip:{client_ip(request)}'
    consume(
        scope='api',
        identity=identity,
        maximum=AUTHENTICATED_LIMIT if user_id is not None else UNAUTHENTICATED_LIMIT,
        window_seconds=GENERAL_WINDOW_SECONDS,
    )
    if user_id is not None and request.method == 'POST' and UPLOAD_PATH.fullmatch(request.url.path):
        consume(
            scope='upload',
            identity=identity,
            maximum=UPLOAD_LIMIT,
            window_seconds=GENERAL_WINDOW_SECONDS,
        )
    if user_id is not None and request.method == 'GET' and EXPORT_PATH.fullmatch(request.url.path):
        consume(
            scope='export',
            identity=identity,
            maximum=EXPORT_LIMIT,
            window_seconds=GENERAL_WINDOW_SECONDS,
        )


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith('/api/') and request.url.path != '/api/health':
            try:
                await run_in_threadpool(enforce_api_rate_limit, request)
            except RateLimitExceeded as exc:
                return JSONResponse(
                    {'detail': 'Too many requests. Try again later.'},
                    status_code=429,
                    headers={'Retry-After': str(exc.retry_after)},
                )
        return await call_next(request)
