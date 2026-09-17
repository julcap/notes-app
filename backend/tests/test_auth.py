from datetime import timedelta
from fastapi import BackgroundTasks
from sqlalchemy import select
from app import auth
from app.database import SessionLocal, now
from conftest import register, signed_in, token

NOTE={'title':'Private','content':'Secret roadmap','meeting_date':'2026-09-17'}
def csrf(c):return {'x-csrf-token':c.cookies.get('minutes_csrf')}

def test_registration_verification_and_single_use(raw):
    s=register(raw)
    raw.headers['Authorization']='Bearer '+s['access_token']
    assert raw.post('/api/notes',json=NOTE).status_code==403
    verification=token(raw)
    with SessionLocal() as db:
        u=db.scalar(select(auth.User))
        assert u.password_hash.startswith('$2b$')
        assert u.password_hash!='SafePassword123'
        assert db.scalar(select(auth.EmailToken)).token_hash!=verification
    assert raw.post('/api/auth/verify-email',json={'token':verification}).status_code==200
    assert raw.post('/api/auth/verify-email',json={'token':verification}).status_code==400
    assert raw.post('/api/notes',json=NOTE).status_code==201
    assert raw.get('/api/auth/me').json()['email_verified'] is True

def test_password_policy_and_duplicate_email(raw):
    for pw in ['short1','abcdefghijk','12345678900','é'*40+'a1']:
        assert raw.post('/api/auth/register',json={'email':'a@example.com','password':pw,'password_confirmation':pw}).status_code==422
    register(raw)
    r=raw.post('/api/auth/register',json={'email':'TEST@example.com','password':'SafePassword123','password_confirmation':'SafePassword123'})
    assert r.status_code==409

def test_private_notes_and_attachments(client):
    n=client.post('/api/notes',json=NOTE).json()
    base='/api/notes/'+n['id']
    a=client.post(base+'/attachments',files={'file':('x.txt',b'private')}).json()
    signed_in(client,'other@example.com')
    assert client.get('/api/notes').json()==[]
    assert client.get('/api/notes?q=roadmap').json()==[]
    for method,path,kw in [('get',base,{}),('put',base,{'json':NOTE}),('delete',base,{}),('get',base+'/attachments/'+a['id'],{}),('delete',base+'/attachments/'+a['id'],{}),('post',base+'/attachments',{'files':{'file':('x',b'x')}})]:
        assert getattr(client,method)(path,**kw).status_code==404
    client.headers.pop('Authorization')
    assert client.get('/api/notes').status_code==401
    assert client.get(base+'/attachments/'+a['id']).status_code==401

def test_refresh_rotation_csrf_and_logout(client):
    old=client.cookies.get('minutes_refresh')
    oldcsrf=client.cookies.get('minutes_csrf')
    assert client.post('/api/auth/refresh').status_code==403
    assert client.post('/api/auth/refresh',headers={**csrf(client),'origin':'https://evil.example'}).status_code==403
    r=client.post('/api/auth/refresh',headers=csrf(client))
    assert r.status_code==200
    client.headers['Authorization']='Bearer '+r.json()['access_token']
    assert old != client.cookies.get('minutes_refresh')
    assert client.post('/api/auth/refresh',headers={'cookie':f'minutes_refresh={old}; minutes_csrf={oldcsrf}','x-csrf-token':oldcsrf}).status_code==401
    assert client.post('/api/auth/logout',headers=csrf(client)).status_code==200
    assert client.get('/api/auth/me').status_code==401

def test_reset_generic_single_use_and_session_revocation(client):
    a=client.post('/api/auth/forgot-password',json={'email':'test@example.com'})
    reset=token(client)
    b=client.post('/api/auth/forgot-password',json={'email':'missing@example.com'})
    assert a.json()==b.json()
    payload={'token':reset,'password':'NewPassword123','password_confirmation':'NewPassword123'}
    assert client.post('/api/auth/reset-password',json=payload).status_code==200
    assert client.post('/api/auth/reset-password',json=payload).status_code==400
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/refresh',headers=csrf(client)).status_code==401
    assert client.post('/api/auth/login',json={'email':'test@example.com','password':'SafePassword123'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'test@example.com','password':'NewPassword123'}).status_code==200

def test_expired_tokens(raw):
    register(raw)
    t=token(raw)
    with SessionLocal() as db:
        row=db.scalar(select(auth.EmailToken));row.expires_at=now()-timedelta(seconds=1);db.commit()
    assert raw.post('/api/auth/verify-email',json={'token':t}).status_code==400
    with SessionLocal() as db:
        row=db.scalar(select(auth.RefreshToken));row.expires_at=now()-timedelta(seconds=1);db.commit()
    assert raw.post('/api/auth/refresh',headers=csrf(raw)).status_code==401

def test_rate_limits(raw):
    for _ in range(5):
        assert raw.post('/api/auth/forgot-password',json={'email':'unknown@example.com'}).status_code==200
    assert raw.post('/api/auth/forgot-password',json={'email':'unknown@example.com'}).status_code==429

def test_remember_me_cookie_lifetime(raw):
    r=raw.post('/api/auth/register',json={'email':'remember@example.com','password':'SafePassword123','password_confirmation':'SafePassword123','remember':True})
    assert 'Max-Age=' in r.headers.get('set-cookie')
    assert 'HttpOnly' in r.headers.get('set-cookie')
    assert 'SameSite=lax' in r.headers.get('set-cookie')
    r=raw.post('/api/auth/login',json={'email':'remember@example.com','password':'SafePassword123','remember':False})
    assert 'Max-Age=' not in r.headers.get('set-cookie')

def test_social_merge_and_unverified_separation(raw):
    local=signed_in(raw)
    with SessionLocal() as db:
        google=auth.social_user(db,'google','g123','test@example.com','Test',True,BackgroundTasks())
        assert google.id==local['user']['id']
        assert google.password_hash
        again=auth.social_user(db,'google','g123','changed@example.com','Test',True,BackgroundTasks())
        assert again.id==google.id
    unverified=register(raw,'unverified@example.com')
    with SessionLocal() as db:
        new=auth.social_user(db,'google','g456','unverified@example.com','Other',True,BackgroundTasks())
        assert new.id!=unverified['user']['id']
        fb=auth.social_user(db,'facebook','f123','test@example.com','Test',False,BackgroundTasks())
        assert fb.id!=local['user']['id']
        assert not fb.email_verified

def test_social_mailbox_proof_before_linking(raw):
    local=signed_in(raw)
    tasks=BackgroundTasks()
    with SessionLocal() as db:
        social=auth.social_user(db,'amazon','a123','test@example.com','Test',False,tasks)
        task=tasks.tasks[0]
        raw_token=task.args[2].split('#token=')[1].split()[0]
    response=raw.post('/api/auth/verify-email',json={'token':raw_token})
    assert response.json()['user']['id']==local['user']['id']
    with SessionLocal() as db:
        assert db.scalar(select(auth.Identity).where(auth.Identity.provider=='amazon')).user_id==local['user']['id']

def test_oauth_unconfigured_and_state_rejected(raw,monkeypatch):
    assert raw.get('/api/auth/providers').json()=={'google':False,'facebook':False,'amazon':False}
    assert raw.get('/api/auth/google/login',follow_redirects=False).status_code==303
    auth.oauth.register('google',overwrite=True,client_id='fake',client_secret='fake',authorize_url='https://example.com/authorize',access_token_url='https://example.com/token',client_kwargs={'scope':'email'})
    try:
        r=raw.get('/api/auth/google/callback?code=bad&state=forged',follow_redirects=False)
        assert r.status_code==303
        assert 'social_failed' in r.headers['location']
    finally:
        auth.oauth._clients.pop('google',None)
        auth.oauth._registry.pop('google',None)

def test_reset_invalidates_unused_verification_links(raw):
    register(raw)
    verification=token(raw)
    raw.post('/api/auth/forgot-password',json={'email':'test@example.com'})
    reset_token=token(raw)
    assert raw.post('/api/auth/reset-password',json={'token':reset_token,'password':'AnotherPassword123','password_confirmation':'AnotherPassword123'}).status_code==200
    assert raw.post('/api/auth/verify-email',json={'token':verification}).status_code==400

def test_resend_verification(raw):
    s=register(raw)
    raw.headers['Authorization']='Bearer '+s['access_token']
    assert raw.post('/api/auth/resend-verification').status_code==200
    assert len(raw.messages)==2
