import hmac
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import db, now
from .config import SECRET, SECURE
from .models import EmailToken, RefreshToken, User
from .security import digest

bearer = HTTPBearer(auto_error=False)


def profile(user):
    return {'id': user.id, 'email': user.email, 'display_name': user.display_name, 'email_verified': user.email_verified, 'auth_provider': user.auth_provider}


def access(user, session_id):
    return jwt.encode({'sub': str(user.id), 'sid': session_id, 'ver': user.token_version, 'type': 'access', 'iat': now(), 'exp': now() + timedelta(minutes=15), 'iss': 'minutes', 'aud': 'minutes'}, SECRET, algorithm='HS256')


def cookie(response, raw, csrf, row):
    age = max(0, int((row.expires_at - now()).total_seconds())) if row.remember else None
    response.set_cookie('minutes_refresh', raw, max_age=age, httponly=True, secure=SECURE, samesite='lax', path='/api/auth')
    response.set_cookie('minutes_csrf', csrf, max_age=age, httponly=False, secure=SECURE, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'


def issue(user, response, session, remember=False):
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    row = RefreshToken(user_id=user.id, token_hash=digest(raw), csrf_hash=digest(csrf), remember=remember, expires_at=now() + timedelta(days=30) if remember else now() + timedelta(hours=24))
    session.add(row)
    session.commit()
    cookie(response, raw, csrf, row)
    return {'access_token': access(user, row.id), 'token_type': 'bearer', 'user': profile(user)}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session: Session = Depends(db)):
    try:
        if not credentials:
            raise ValueError()
        claims = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'], issuer='minutes', audience='minutes', options={'require': ['exp', 'sub', 'sid', 'ver', 'type']})
        user = session.get(User, int(claims['sub']))
        row = session.get(RefreshToken, claims['sid'])
        if claims['type'] != 'access' or not user or user.token_version != claims['ver'] or not row or row.user_id != user.id or row.revoked_at or row.expires_at <= now():
            raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, 'Please sign in again', headers={'WWW-Authenticate': 'Bearer'})


def verified_user(user: User = Depends(current_user)):
    if not user.email_verified:
        raise HTTPException(403, 'Verify your email before creating meeting notes.')
    return user


def refresh_row(request, session):
    raw = request.cookies.get('minutes_refresh', '')
    csrf = request.headers.get('x-csrf-token', '')
    if not csrf or not hmac.compare_digest(csrf, request.cookies.get('minutes_csrf', '')):
        raise HTTPException(403, 'Missing or invalid CSRF token')
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest(raw)).with_for_update())
    if not row or row.revoked_at or row.expires_at <= now():
        raise HTTPException(401, 'Session expired. Please sign in again.')
    if not hmac.compare_digest(row.csrf_hash, digest(csrf)):
        raise HTTPException(403, 'Invalid CSRF token')
    return row


def consume(session, raw, purpose):
    row = session.scalar(select(EmailToken).where(EmailToken.token_hash == digest(raw), EmailToken.purpose == purpose).with_for_update())
    if not row or row.used_at or row.expires_at <= now():
        raise HTTPException(400, 'This link is invalid or expired. Request a new one.')
    row.used_at = now()
    return session.get(User, row.user_id)
