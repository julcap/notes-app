import hashlib
import re

import bcrypt
from fastapi import HTTPException, Request

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
    from ..rate_limits import RateLimitExceeded, client_ip, consume

    try:
        consume(
            scope=scope,
            identity=client_ip(request),
            maximum=maximum,
            window_seconds=900,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            429,
            'Too many attempts. Try again in 15 minutes.',
            headers={'Retry-After': str(exc.retry_after)},
        ) from None
