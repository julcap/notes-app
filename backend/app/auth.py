import hashlib
import hmac
import os
import re
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlencode
import bcrypt
import boto3
import jwt
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import String, DateTime, ForeignKey, Index, UniqueConstraint, select, update, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from .database import Base, db, now, SessionLocal

APP_URL = os.environ.get('APP_URL', 'http://localhost:8080').rstrip('/')
SECRET = os.environ['AUTH_SECRET']
if len(SECRET) < 32:
    raise RuntimeError('AUTH_SECRET must contain at least 32 random characters')
SECURE = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
if not SECURE and not APP_URL.startswith(('http://localhost:', 'http://127.0.0.1:')):
    raise RuntimeError('Insecure cookies are only allowed on localhost')
if SECURE and not APP_URL.startswith('https://'):
    raise RuntimeError('Production APP_URL must use HTTPS')
router = APIRouter(prefix='/api/auth')
bearer = HTTPBearer(auto_error=False)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(100))
    email_verified: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(String(100), default='')
    auth_provider: Mapped[str] = mapped_column(String(20), default='local')
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (Index('unique_local_email', 'email', unique=True, postgresql_where=text("auth_provider = 'local'")),)

class Identity(Base):
    __tablename__ = 'social_identities'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint('provider', 'provider_user_id'),)

class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    remember: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

class EmailToken(Base):
    __tablename__ = 'email_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))

class RateBucket(Base):
    __tablename__ = 'auth_rate_limits'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    hits: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))

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
"""), {'key':key, 'now':now(), 'expires':now()+timedelta(minutes=15)}).scalar_one()
        session.commit()
    if row > maximum:
        raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.', headers={'Retry-After':'900'})

def same_origin(request: Request):
    if request.headers.get('origin') != APP_URL or request.headers.get('x-requested-with') != 'Minutes':
        raise HTTPException(403, 'Invalid request origin')

def password_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

DUMMY_HASH = bcrypt.hashpw(b'nonexistent-account-password', bcrypt.gensalt(rounds=12))

def validate_password(password):
    if len(password) < 10 or len(password.encode()) > 72 or not re.search('[a-zA-Z]',password) or not re.search('[0-9]',password):
        raise ValueError('Password needs at least 10 characters, a letter and a number (maximum 72 UTF-8 bytes).')
    return password

class EmailInput(BaseModel):
    email: EmailStr
    @model_validator(mode='after')
    def normalize(self):
        self.email = str(self.email).lower()
        return self

class PasswordInput(BaseModel):
    password: str = Field(max_length=72)
    password_confirmation: str = Field(max_length=72)
    @model_validator(mode='after')
    def policy(self):
        validate_password(self.password)
        if self.password != self.password_confirmation:
            raise ValueError('Passwords do not match')
        return self

class Registration(EmailInput, PasswordInput):
    display_name: str = Field(default='', max_length=100)
    remember: bool = False

class Login(EmailInput):
    password: str = Field(max_length=1000)
    remember: bool = False

class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)

class Reset(PasswordInput, TokenInput):
    pass

def profile(user):
    return {'id':user.id, 'email':user.email, 'display_name':user.display_name, 'email_verified':user.email_verified, 'auth_provider':user.auth_provider}

def access(user, session_id):
    return jwt.encode({'sub':str(user.id), 'sid':session_id, 'ver':user.token_version, 'type':'access', 'iat':now(), 'exp':now()+timedelta(minutes=15), 'iss':'minutes', 'aud':'minutes'}, SECRET, algorithm='HS256')

def cookie(response, raw, csrf, row):
    age = max(0, int((row.expires_at-now()).total_seconds())) if row.remember else None
    response.set_cookie('minutes_refresh', raw, max_age=age, httponly=True, secure=SECURE, samesite='lax', path='/api/auth')
    response.set_cookie('minutes_csrf', csrf, max_age=age, httponly=False, secure=SECURE, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'

def issue(user, response, session, remember=False):
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    row = RefreshToken(user_id=user.id, token_hash=digest(raw), csrf_hash=digest(csrf), remember=remember, expires_at=now()+timedelta(days=30) if remember else now()+timedelta(hours=24))
    session.add(row)
    session.commit()
    cookie(response, raw, csrf, row)
    return {'access_token':access(user,row.id), 'token_type':'bearer', 'user':profile(user)}

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), session: Session = Depends(db)):
    try:
        if not credentials:
            raise ValueError()
        claims=jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'], issuer='minutes', audience='minutes', options={'require':['exp','sub','sid','ver','type']})
        user=session.get(User,int(claims['sub']))
        row=session.get(RefreshToken,claims['sid'])
        if claims['type'] != 'access' or not user or user.token_version != claims['ver'] or not row or row.user_id != user.id or row.revoked_at or row.expires_at <= now():
            raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, 'Please sign in again', headers={'WWW-Authenticate':'Bearer'})

def verified_user(user: User = Depends(current_user)):
    if not user.email_verified:
        raise HTTPException(403, 'Verify your email before creating meeting notes.')
    return user

def send_email(recipient, subject, body):
    mode=os.getenv('MAIL_MODE','ses')
    if mode == 'smtp' and not SECURE:
        message=EmailMessage()
        message['From']=os.getenv('SES_FROM_EMAIL','minutes@localhost.test')
        message['To']=recipient
        message['Subject']=subject
        message.set_content(body)
        with smtplib.SMTP(os.getenv('SMTP_HOST','mailpit'),int(os.getenv('SMTP_PORT','1025')),timeout=10) as smtp:
            smtp.send_message(message)
    else:
        boto3.client('ses',region_name=os.getenv('AWS_REGION','eu-west-1')).send_email(Source=os.environ['SES_FROM_EMAIL'],Destination={'ToAddresses':[recipient]},Message={'Subject':{'Data':subject},'Body':{'Text':{'Data':body}}})

def deliver_email(recipient, subject, body):
    # Do not leak tokens, email addresses, or provider errors into application logs.
    try:
        send_email(recipient,subject,body)
    except Exception:
        import logging
        logging.getLogger(__name__).error('Transactional email delivery failed; check SES/SMTP configuration. Use resend or request recovery again.')

def email_link(session, user, purpose, tasks):
    raw=secrets.token_urlsafe(48)
    session.add(EmailToken(user_id=user.id,purpose=purpose,token_hash=digest(raw),expires_at=now()+timedelta(hours=1)))
    session.commit()
    path='reset-password' if purpose == 'reset' else 'verify-email'
    # URL fragment keeps the bearer token out of proxy/access logs and Referer headers.
    link=f'{APP_URL}/{path}#token={raw}'
    tasks.add_task(deliver_email,user.email,'Reset your Minutes password' if purpose == 'reset' else 'Verify your Minutes email',f'Open this link within one hour:\n\n{link}\n\nIf you did not request this, you can ignore this email.')

@router.post('/register', dependencies=[Depends(same_origin)], status_code=201)
def register(data: Registration, request: Request, response: Response, tasks: BackgroundTasks, session: Session=Depends(db)):
    limit(request,'register',5)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'),{'email':data.email})
    if session.scalar(select(User).where(User.email==data.email,User.auth_provider=='local')):
        raise HTTPException(409,'This email is already registered. Sign in or reset your password.')
    user=User(email=data.email,password_hash=password_hash(data.password),display_name=data.display_name.strip(),auth_provider='local')
    session.add(user)
    session.flush()
    email_link(session,user,'verify',tasks)
    return issue(user,response,session,data.remember)

@router.post('/login', dependencies=[Depends(same_origin)])
def login(data: Login, request: Request, response: Response, session: Session=Depends(db)):
    limit(request,'login',15)
    user=session.scalar(select(User).where(User.email==data.email,User.auth_provider=='local'))
    valid=bcrypt.checkpw(data.password.encode()[:72],user.password_hash.encode() if user and user.password_hash else DUMMY_HASH)
    if not user:
        social=session.scalar(select(User).where(User.email==data.email))
        if social:
            raise HTTPException(400, f'Use {social.auth_provider.title()} to sign in to this account.')
    if not user or not valid or len(data.password.encode()) > 72:
        raise HTTPException(401,'Email or password is incorrect.')
    return issue(user,response,session,data.remember)

def refresh_row(request, session):
    raw=request.cookies.get('minutes_refresh','')
    csrf=request.headers.get('x-csrf-token','')
    if not csrf or not hmac.compare_digest(csrf,request.cookies.get('minutes_csrf','')):
        raise HTTPException(403,'Missing or invalid CSRF token')
    row=session.scalar(select(RefreshToken).where(RefreshToken.token_hash==digest(raw)).with_for_update())
    if not row or row.revoked_at or row.expires_at<=now():
        raise HTTPException(401,'Session expired. Please sign in again.')
    if not hmac.compare_digest(row.csrf_hash,digest(csrf)):
        raise HTTPException(403,'Invalid CSRF token')
    return row

@router.post('/refresh', dependencies=[Depends(same_origin)])
def refresh(request: Request, response: Response, session: Session=Depends(db)):
    row=refresh_row(request,session)
    raw,csrf=secrets.token_urlsafe(48),secrets.token_urlsafe(32)
    row.token_hash=digest(raw)
    row.csrf_hash=digest(csrf)
    user=session.get(User,row.user_id)
    session.commit()
    cookie(response,raw,csrf,row)
    return {'access_token':access(user,row.id),'token_type':'bearer','user':profile(user)}

@router.post('/logout', dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response, session: Session=Depends(db)):
    row=refresh_row(request,session)
    row.revoked_at=now()
    session.commit()
    response.delete_cookie('minutes_refresh',path='/api/auth',secure=SECURE,httponly=True,samesite='lax')
    response.delete_cookie('minutes_csrf',path='/',secure=SECURE,samesite='lax')
    return {'message':'Signed out'}

@router.get('/me')
def me(user: User=Depends(current_user)):
    return profile(user)

@router.post('/forgot-password', dependencies=[Depends(same_origin)])
def forgot(data: EmailInput, request: Request, tasks: BackgroundTasks, session: Session=Depends(db)):
    limit(request,'forgot-password',5)
    users=session.scalars(select(User).where(User.email==data.email)).all()
    local=next((u for u in users if u.auth_provider=='local'),None)
    if local:
        email_link(session,local,'reset',tasks)
    elif users:
        providers=', '.join(sorted({u.auth_provider.title() for u in users}))
        tasks.add_task(deliver_email,data.email,'Sign in to Minutes',f'Your account uses {providers}. Use that provider at {APP_URL}/login to sign in.')
    return {'message':"If that email exists, we've sent a link or sign-in instructions."}

def consume(session, raw, purpose):
    row=session.scalar(select(EmailToken).where(EmailToken.token_hash==digest(raw),EmailToken.purpose==purpose).with_for_update())
    if not row or row.used_at or row.expires_at<=now():
        raise HTTPException(400,'This link is invalid or expired. Request a new one.')
    row.used_at=now()
    return session.get(User,row.user_id)

@router.post('/reset-password', dependencies=[Depends(same_origin)])
def reset(data: Reset, request: Request, session: Session=Depends(db)):
    limit(request,'reset',15)
    user=consume(session,data.token,'reset')
    user.password_hash=password_hash(data.password)
    user.token_version+=1
    session.execute(update(RefreshToken).where(RefreshToken.user_id==user.id).values(revoked_at=now()))
    session.execute(update(EmailToken).where(EmailToken.user_id==user.id,EmailToken.used_at.is_(None)).values(used_at=now()))
    session.commit()
    return {'message':'Password updated. Sign in with your new password.'}

@router.post('/resend-verification', dependencies=[Depends(same_origin)])
def resend(request: Request, tasks: BackgroundTasks, user: User=Depends(current_user), session: Session=Depends(db)):
    limit(request,'resend',5)
    if not user.email_verified:
        email_link(session,user,'verify',tasks)
    return {'message':'If verification is needed, a new link has been sent.'}

@router.post('/verify-email', dependencies=[Depends(same_origin)])
def verify(data: TokenInput, request: Request, response: Response, session: Session=Depends(db)):
    limit(request,'verify',15)
    user=consume(session,data.token,'verify')
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'),{'email':user.email})
    # A provider without verified-email claims must prove mailbox control before an automatic merge.
    target=session.scalar(select(User).where(User.email==user.email,User.email_verified.is_(True),User.id!=user.id).order_by(User.id)) if user.auth_provider!='local' else None
    if target:
        session.execute(update(Identity).where(Identity.user_id==user.id).values(user_id=target.id))
        user.token_version+=1
        session.execute(update(RefreshToken).where(RefreshToken.user_id==user.id).values(revoked_at=now()))
        user=target
    user.email_verified=True
    session.commit()
    return issue(user,response,session)

# Authlib validates state and Google's OIDC signature, issuer, audience, and nonce.
oauth=OAuth()
PROVIDERS={
 'google':dict(server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile','code_challenge_method':'S256'}),
 'facebook':dict(authorize_url='https://www.facebook.com/v23.0/dialog/oauth',access_token_url='https://graph.facebook.com/v23.0/oauth/access_token',api_base_url='https://graph.facebook.com/v23.0/',client_kwargs={'scope':'email public_profile','token_endpoint_auth_method':'client_secret_post'}),
 'amazon':dict(authorize_url='https://www.amazon.com/ap/oa',access_token_url='https://api.amazon.com/auth/o2/token',api_base_url='https://api.amazon.com/',client_kwargs={'scope':'profile','token_endpoint_auth_method':'client_secret_post'})
}
for name, config in PROVIDERS.items():
    if os.getenv(name.upper()+'_CLIENT_ID') and os.getenv(name.upper()+'_CLIENT_SECRET'):
        oauth.register(name, client_id=os.environ[name.upper()+'_CLIENT_ID'],client_secret=os.environ[name.upper()+'_CLIENT_SECRET'],**config)

@router.get('/providers')
def providers():
    return {name:bool(oauth.create_client(name)) for name in PROVIDERS}

@router.get('/{provider}/login')
async def social_login(provider: str, request: Request, remember: bool=False):
    if provider not in PROVIDERS or not oauth.create_client(provider):
        return RedirectResponse(APP_URL+'/login?error=provider_unavailable',status_code=303)
    limit(request,'oauth',30)
    request.session['remember']=remember
    return await oauth.create_client(provider).authorize_redirect(request,APP_URL+f'/api/auth/{provider}/callback')

def social_user(session,provider,subject,email,name,verified,tasks):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'),{'email':email})
    identity=session.scalar(select(Identity).where(Identity.provider==provider,Identity.provider_user_id==subject))
    if identity:
        return session.get(User,identity.user_id)
    target=session.scalar(select(User).where(User.email==email,User.email_verified.is_(True)).order_by(User.id)) if verified else None
    user=target or User(email=email,display_name=name[:100],auth_provider=provider,email_verified=verified)
    if not target:
        session.add(user)
        session.flush()
    session.add(Identity(user_id=user.id,provider=provider,provider_user_id=subject))
    session.commit()
    if not verified:
        email_link(session,user,'verify',tasks)
    return user

@router.get('/{provider}/callback')
async def social_callback(provider: str, request: Request, tasks: BackgroundTasks, session: Session=Depends(db)):
    client=oauth.create_client(provider) if provider in PROVIDERS else None
    if not client:
        return RedirectResponse(APP_URL+'/login?error=provider_unavailable',status_code=303)
    try:
        token=await client.authorize_access_token(request)
        if provider=='google':
            info=token['userinfo']
            subject=info['sub']
            verified=info.get('email_verified') is True
        else:
            result=await client.get('me?fields=id,name,email' if provider=='facebook' else 'user/profile',token=token)
            result.raise_for_status()
            info=result.json()
            subject=info['id'] if provider=='facebook' else info['user_id']
            verified=False
        email=str(EmailInput(email=info['email']).email)
        user=social_user(session,provider,str(subject),email,info.get('name',''),verified,tasks)
        response=RedirectResponse(APP_URL+'/auth/callback',status_code=303)
        issue(user,response,session,bool(request.session.pop('remember',False)))
        return response
    except Exception:
        session.rollback()
        return RedirectResponse(APP_URL+'/login?error=social_failed',status_code=303)
