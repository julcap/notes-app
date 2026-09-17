import secrets

import bcrypt
from fastapi import BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ..database import db, now
from .config import APP_URL, SECURE
from .email import deliver_email, email_link
from .models import EmailToken, Identity, RefreshToken, User
from .router import router
from .schemas import EmailInput, Login, Registration, Reset, TokenInput
from .security import DUMMY_HASH, digest, limit, password_hash, same_origin
from .tokens import access, consume, cookie, current_user, issue, profile, refresh_row


@router.post('/register', dependencies=[Depends(same_origin)], status_code=201)
def register(data: Registration, request: Request, response: Response, tasks: BackgroundTasks, session: Session = Depends(db)):
    limit(request, 'register', 5)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'), {'email': data.email})
    if session.scalar(select(User).where(User.email == data.email, User.auth_provider == 'local')):
        raise HTTPException(409, 'This email is already registered. Sign in or reset your password.')
    user = User(email=data.email, password_hash=password_hash(data.password), display_name=data.display_name.strip(), auth_provider='local')
    session.add(user)
    session.flush()
    email_link(session, user, 'verify', tasks)
    return issue(user, response, session, data.remember)


@router.post('/login', dependencies=[Depends(same_origin)])
def login(data: Login, request: Request, response: Response, session: Session = Depends(db)):
    limit(request, 'login', 15)
    user = session.scalar(select(User).where(User.email == data.email, User.auth_provider == 'local'))
    valid = bcrypt.checkpw(data.password.encode()[:72], user.password_hash.encode() if user and user.password_hash else DUMMY_HASH)
    if not user:
        social = session.scalar(select(User).where(User.email == data.email))
        if social:
            raise HTTPException(400, f'Use {social.auth_provider.title()} to sign in to this account.')
    if not user or not valid or len(data.password.encode()) > 72:
        raise HTTPException(401, 'Email or password is incorrect.')
    return issue(user, response, session, data.remember)


@router.post('/refresh', dependencies=[Depends(same_origin)])
def refresh(request: Request, response: Response, session: Session = Depends(db)):
    row = refresh_row(request, session)
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    row.token_hash = digest(raw)
    row.csrf_hash = digest(csrf)
    user = session.get(User, row.user_id)
    session.commit()
    cookie(response, raw, csrf, row)
    return {'access_token': access(user, row.id), 'token_type': 'bearer', 'user': profile(user)}


@router.post('/logout', dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response, session: Session = Depends(db)):
    row = refresh_row(request, session)
    row.revoked_at = now()
    session.commit()
    response.delete_cookie('minutes_refresh', path='/api/auth', secure=SECURE, httponly=True, samesite='lax')
    response.delete_cookie('minutes_csrf', path='/', secure=SECURE, samesite='lax')
    return {'message': 'Signed out'}


@router.get('/me')
def me(user: User = Depends(current_user)):
    return profile(user)


@router.post('/forgot-password', dependencies=[Depends(same_origin)])
def forgot(data: EmailInput, request: Request, tasks: BackgroundTasks, session: Session = Depends(db)):
    limit(request, 'forgot-password', 5)
    users = session.scalars(select(User).where(User.email == data.email)).all()
    local = next((u for u in users if u.auth_provider == 'local'), None)
    if local:
        email_link(session, local, 'reset', tasks)
    elif users:
        providers = ', '.join(sorted({u.auth_provider.title() for u in users}))
        tasks.add_task(deliver_email, data.email, 'Sign in to Minutes', f'Your account uses {providers}. Use that provider at {APP_URL}/login to sign in.')
    return {'message': "If that email exists, we've sent a link or sign-in instructions."}


@router.post('/reset-password', dependencies=[Depends(same_origin)])
def reset(data: Reset, request: Request, session: Session = Depends(db)):
    limit(request, 'reset', 15)
    user = consume(session, data.token, 'reset')
    user.password_hash = password_hash(data.password)
    user.token_version += 1
    session.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked_at=now()))
    session.execute(update(EmailToken).where(EmailToken.user_id == user.id, EmailToken.used_at.is_(None)).values(used_at=now()))
    session.commit()
    return {'message': 'Password updated. Sign in with your new password.'}


@router.post('/resend-verification', dependencies=[Depends(same_origin)])
def resend(request: Request, tasks: BackgroundTasks, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'resend', 5)
    if not user.email_verified:
        email_link(session, user, 'verify', tasks)
    return {'message': 'If verification is needed, a new link has been sent.'}


@router.post('/verify-email', dependencies=[Depends(same_origin)])
def verify(data: TokenInput, request: Request, response: Response, session: Session = Depends(db)):
    limit(request, 'verify', 15)
    user = consume(session, data.token, 'verify')
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'), {'email': user.email})
    # A provider without verified-email claims must prove mailbox control before an automatic merge.
    target = session.scalar(select(User).where(User.email == user.email, User.email_verified.is_(True), User.id != user.id).order_by(User.id)) if user.auth_provider != 'local' else None
    if target:
        session.execute(update(Identity).where(Identity.user_id == user.id).values(user_id=target.id))
        user.token_version += 1
        session.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked_at=now()))
        user = target
    user.email_verified = True
    session.commit()
    return issue(user, response, session)
