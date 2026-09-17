import os

from authlib.integrations.starlette_client import OAuth
from fastapi import BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..database import db
from .config import APP_URL
from .email import email_link
from .models import Identity, User
from .router import router
from .schemas import EmailInput
from .security import limit
from .tokens import issue

# Authlib validates state and Google's OIDC signature, issuer, audience, and nonce.
oauth = OAuth()
PROVIDERS = {
    'google': dict(server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'}),
    'facebook': dict(authorize_url='https://www.facebook.com/v23.0/dialog/oauth', access_token_url='https://graph.facebook.com/v23.0/oauth/access_token', api_base_url='https://graph.facebook.com/v23.0/', client_kwargs={'scope': 'email public_profile', 'token_endpoint_auth_method': 'client_secret_post'}),
    'amazon': dict(authorize_url='https://www.amazon.com/ap/oa', access_token_url='https://api.amazon.com/auth/o2/token', api_base_url='https://api.amazon.com/', client_kwargs={'scope': 'profile', 'token_endpoint_auth_method': 'client_secret_post'}),
}
for name, config in PROVIDERS.items():
    if os.getenv(name.upper() + '_CLIENT_ID') and os.getenv(name.upper() + '_CLIENT_SECRET'):
        oauth.register(name, client_id=os.environ[name.upper() + '_CLIENT_ID'], client_secret=os.environ[name.upper() + '_CLIENT_SECRET'], **config)


@router.get('/providers')
def providers():
    return {name: bool(oauth.create_client(name)) for name in PROVIDERS}


@router.get('/{provider}/login')
async def social_login(provider: str, request: Request, remember: bool = False):
    if provider not in PROVIDERS or not oauth.create_client(provider):
        return RedirectResponse(APP_URL + '/login?error=provider_unavailable', status_code=303)
    limit(request, 'oauth', 30)
    request.session['remember'] = remember
    return await oauth.create_client(provider).authorize_redirect(request, APP_URL + f'/api/auth/{provider}/callback')


def social_user(session, provider, subject, email, name, verified, tasks):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:email))'), {'email': email})
    identity = session.scalar(select(Identity).where(Identity.provider == provider, Identity.provider_user_id == subject))
    if identity:
        return session.get(User, identity.user_id)
    target = session.scalar(select(User).where(User.email == email, User.email_verified.is_(True)).order_by(User.id)) if verified else None
    user = target or User(email=email, display_name=name[:100], auth_provider=provider, email_verified=verified)
    if not target:
        session.add(user)
        session.flush()
    session.add(Identity(user_id=user.id, provider=provider, provider_user_id=subject))
    session.commit()
    if not verified:
        email_link(session, user, 'verify', tasks)
    return user


@router.get('/{provider}/callback')
async def social_callback(provider: str, request: Request, tasks: BackgroundTasks, session: Session = Depends(db)):
    client = oauth.create_client(provider) if provider in PROVIDERS else None
    if not client:
        return RedirectResponse(APP_URL + '/login?error=provider_unavailable', status_code=303)
    try:
        token = await client.authorize_access_token(request)
        if provider == 'google':
            info = token['userinfo']
            subject = info['sub']
            verified = info.get('email_verified') is True
        else:
            result = await client.get('me?fields=id,name,email' if provider == 'facebook' else 'user/profile', token=token)
            result.raise_for_status()
            info = result.json()
            subject = info['id'] if provider == 'facebook' else info['user_id']
            verified = False
        email = str(EmailInput(email=info['email']).email)
        user = social_user(session, provider, str(subject), email, info.get('name', ''), verified, tasks)
        response = RedirectResponse(APP_URL + '/auth/callback', status_code=303)
        issue(user, response, session, bool(request.session.pop('remember', False)))
        return response
    except Exception:
        session.rollback()
        return RedirectResponse(APP_URL + '/login?error=social_failed', status_code=303)
