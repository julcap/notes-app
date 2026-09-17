import hashlib
import re
from datetime import timedelta

import bcrypt
from fastapi import HTTPException, Request
from sqlalchemy import text

from ..database import SessionLocal, now
from .config import APP_URL


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


DUMMY_HASH = bcrypt.hashpw(b'nonexistent-account-password', bcrypt.gensalt(rounds=12))


def check_password(password, hash_):
    return bool(hash_) and len(password.encode()) <= 72 and bcrypt.checkpw(password.encode(), hash_.encode())


def validate_password(password):
    if len(password) < 10 or len(password.encode()) > 72 or not re.search('[a-zA-Z]', password) or not re.search('[0-9]', password):
        raise ValueError('Password needs at least 10 characters, a letter and a number (maximum 72 UTF-8 bytes).')
    return password


def same_origin(request: Request):
    if request.headers.get('origin') != APP_URL or request.headers.get('x-requested-with') != 'Minutes':
        raise HTTPException(403, 'Invalid request origin')


def limit(request, scope, maximum=10):
    # Shared PostgreSQL counters work across workers. Never trust arbitrary X-Forwarded-For.
    key = digest(scope + ':' + (request.client.host if request.client else 'unknown'))
    with SessionLocal() as session:
        row = session.execute(text("""
INSERT INTO auth_rate_limits (key, hits, expires_at) VALUES (:key, 1, :expires)
ON CONFLICT (key) DO UPDATE SET
hits = CASE WHEN auth_rate_limits.expires_at < :now THEN 1 ELSE auth_rate_limits.hits + 1 END,
expires_at = CASE WHEN auth_rate_limits.expires_at < :now THEN :expires ELSE auth_rate_limits.expires_at END
RETURNING hits
"""), {'key': key, 'now': now(), 'expires': now() + timedelta(minutes=15)}).scalar_one()
        session.commit()
    if row > maximum:
        raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.', headers={'Retry-After': '900'})
