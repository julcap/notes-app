import secrets

import bcrypt
from fastapi import BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.orm import Session

from ..database import db, now
from ..jobs import try_reconcile_quarantine
from ..notes.models import MeetingShare, Note
from ..notes.permissions import lock_account
from ..storage import FILE_CLEANUP_LOCK_ID, discard_quarantined, quarantine_files
from . import totp
from .config import APP_URL, SECURE
from .email import deliver_email, email_link
from .models import BackupCode, EmailToken, Identity, RefreshToken, User
from .router import router
from .schemas import ChangePassword, DeleteAccount, EmailInput, Login, Login2FA, NotificationPreferences, ProfileUpdate, Registration, Reset, TokenInput, TotpCode, TotpDisable
from .security import DUMMY_HASH, check_password, digest, limit, password_hash, same_origin
from .tokens import access, consume, consume_mfa, cookie, current_user, issue, mfa_challenge, profile, refresh_row


def verify_totp_or_backup_code(session, user, code):
    secret = user.totp_secret and totp.decrypt_secret(user.totp_secret)
    if secret and totp.verify_code(secret, code):
        return True
    for row in session.scalars(select(BackupCode).where(BackupCode.user_id == user.id, BackupCode.used_at.is_(None))):
        if check_password(code, row.code_hash):
            row.used_at = now()
            session.commit()
            return True
    return False


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
    if user.totp_enabled:
        return {'mfa_required': True, 'mfa_token': mfa_challenge(user, data.remember)}
    return issue(user, response, session, data.remember)


@router.post('/login/2fa', dependencies=[Depends(same_origin)])
def login_2fa(data: Login2FA, request: Request, response: Response, session: Session = Depends(db)):
    limit(request, 'login-2fa', 15)
    user, remember = consume_mfa(data.mfa_token, session)
    if not verify_totp_or_backup_code(session, user, data.code):
        raise HTTPException(401, 'Invalid code.')
    return issue(user, response, session, remember)


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


def notification_preferences_for(user):
    return {
        'reminders_enabled': user.reminders_enabled,
        'digest_enabled': user.digest_enabled,
        'reminder_lead_minutes': user.reminder_lead_minutes,
    }


@router.get('/notification-preferences', response_model=NotificationPreferences)
def get_notification_preferences(user: User = Depends(current_user)):
    return notification_preferences_for(user)


@router.put('/notification-preferences', response_model=NotificationPreferences, dependencies=[Depends(same_origin)])
def update_notification_preferences(
    data: NotificationPreferences,
    user: User = Depends(current_user),
    session: Session = Depends(db),
):
    for key, value in data.model_dump().items():
        setattr(user, key, value)
    session.commit()
    return notification_preferences_for(user)


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
    user, _ = consume(session, data.token, ('reset',))
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
    user, purpose = consume(session, data.token, ('verify', 'change_email'))
    if purpose == 'change_email':
        new_email = user.pending_email
        if not new_email:
            raise HTTPException(400, 'This link is invalid or expired. Request a new one.')
        session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'), {'email': new_email})
        if user.auth_provider == 'local' and session.scalar(select(User).where(User.email == new_email, User.auth_provider == 'local', User.id != user.id)):
            raise HTTPException(409, 'That email is already in use.')
        user.email = new_email
        user.pending_email = None
        session.commit()
        return issue(user, response, session)
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


@router.put('/me', dependencies=[Depends(same_origin)])
def update_profile(data: ProfileUpdate, request: Request, tasks: BackgroundTasks, user: User = Depends(current_user), session: Session = Depends(db)):
    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    message = None
    if data.email is not None and data.email != user.email:
        limit(request, 'change-email', 5)
        if user.auth_provider == 'local' and session.scalar(select(User).where(User.email == data.email, User.auth_provider == 'local', User.id != user.id)):
            raise HTTPException(409, 'That email is already in use.')
        user.pending_email = data.email
        session.execute(update(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == 'change_email', EmailToken.used_at.is_(None)).values(used_at=now()))
        email_link(session, user, 'change_email', tasks, recipient=data.email)
        message = 'Check the new address to confirm the change.'
    session.commit()
    return {'user': profile(user), 'message': message}


@router.post('/change-password', dependencies=[Depends(same_origin)])
def change_password(data: ChangePassword, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'change-password', 15)
    if user.auth_provider != 'local' or not user.password_hash:
        raise HTTPException(400, 'This account has no password to change.')
    if not check_password(data.current_password, user.password_hash):
        raise HTTPException(401, 'Current password is incorrect.')
    user.password_hash = password_hash(data.password)
    session.commit()
    return {'message': 'Password updated.'}


@router.delete('/me', dependencies=[Depends(same_origin)])
def delete_account(data: DeleteAccount, request: Request, response: Response, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'delete-account', 5)
    if user.password_hash:
        if not check_password(data.password, user.password_hash):
            raise HTTPException(401, 'Incorrect password.')
    elif data.confirmation.strip().lower() != 'delete account':
        raise HTTPException(400, 'Type "delete account" to confirm.')
    session.execute(
        text('SELECT pg_advisory_xact_lock(:lock_id)'),
        {'lock_id': FILE_CLEANUP_LOCK_ID},
    )
    lock_account(session, user.id)
    locked_notes = session.scalars(
        select(Note)
        .where(or_(
            Note.owner_id == user.id,
            Note.id.in_(select(MeetingShare.note_id).where(MeetingShare.user_id == user.id)),
        ))
        .order_by(Note.id)
        .with_for_update()
    ).all()
    notes = [note for note in locked_notes if note.owner_id == user.id]
    attachment_ids = [a.id for n in notes for a in n.attachments]
    quarantined = quarantine_files(attachment_ids)
    try:
        for note in notes:
            session.delete(note)
        session.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
        session.execute(delete(EmailToken).where(EmailToken.user_id == user.id))
        session.execute(delete(Identity).where(Identity.user_id == user.id))
        session.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
        session.delete(user)
        session.commit()
    except Exception:
        session.rollback()
        try_reconcile_quarantine()
        raise
    discard_quarantined(quarantined)
    response.delete_cookie('minutes_refresh', path='/api/auth', secure=SECURE, httponly=True, samesite='lax')
    response.delete_cookie('minutes_csrf', path='/', secure=SECURE, samesite='lax')
    return {'message': 'Your account and everything it owns have been deleted.'}


@router.post('/2fa/enable', dependencies=[Depends(same_origin)])
def enable_2fa(request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'totp-enable', 10)
    if user.totp_enabled:
        raise HTTPException(400, 'Two-factor authentication is already enabled.')
    secret = totp.generate_secret()
    user.totp_secret = totp.encrypt_secret(secret)
    session.commit()
    uri = totp.otpauth_uri(secret, user.email)
    return {'secret': secret, 'otpauth_url': uri, 'qr_svg': totp.qr_svg(uri)}


@router.post('/2fa/confirm', dependencies=[Depends(same_origin)])
def confirm_2fa(data: TotpCode, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'totp-confirm', 15)
    if user.totp_enabled:
        raise HTTPException(400, 'Two-factor authentication is already enabled.')
    secret = user.totp_secret and totp.decrypt_secret(user.totp_secret)
    if not secret:
        raise HTTPException(400, 'Start enrollment before confirming a code.')
    if not totp.verify_code(secret, data.code):
        raise HTTPException(401, 'Invalid code.')
    user.totp_enabled = True
    session.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    codes = totp.generate_backup_codes()
    for code in codes:
        session.add(BackupCode(user_id=user.id, code_hash=password_hash(code)))
    session.commit()
    return {'message': 'Two-factor authentication is enabled.', 'backup_codes': codes}


@router.post('/2fa/disable', dependencies=[Depends(same_origin)])
def disable_2fa(data: TotpDisable, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    limit(request, 'totp-disable', 15)
    if not user.totp_enabled:
        raise HTTPException(400, 'Two-factor authentication is not enabled.')
    confirmed = (user.password_hash and check_password(data.password, user.password_hash)) or verify_totp_or_backup_code(session, user, data.code)
    if not confirmed:
        raise HTTPException(401, 'Enter your current password or a valid code to disable two-factor authentication.')
    user.totp_enabled = False
    user.totp_secret = None
    session.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    session.commit()
    return {'message': 'Two-factor authentication is disabled.'}
