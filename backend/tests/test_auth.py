from datetime import timedelta
from pathlib import Path

import pytest
import pyotp
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import auth
from app.database import SessionLocal, now
from app.jobs import purge_deleted
from app.notes.models import Note
from app.storage import STORAGE
from conftest import register, signed_in, token

NOTE={'title':'Private','content':'Secret roadmap','meeting_date':'2026-09-17'}
def csrf(c):return {'x-csrf-token':c.cookies.get('minutes_csrf')}

def enable_totp(c):
    r=c.post('/api/auth/2fa/enable',headers=csrf(c))
    assert r.status_code==200,r.text
    secret=r.json()['secret']
    r=c.post('/api/auth/2fa/confirm',json={'code':pyotp.TOTP(secret).now()},headers=csrf(c))
    assert r.status_code==200,r.text
    return secret,r.json()['backup_codes']

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
    assert client.get('/api/notes').json()=={'items': [], 'total': 0}
    assert client.get('/api/notes?q=roadmap').json()=={'items': [], 'total': 0}
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

def test_totp_login_and_backup_codes(client):
    secret,codes=enable_totp(client)
    assert len(codes)==10
    assert client.get('/api/auth/me').json()['totp_enabled'] is True
    client.headers.pop('Authorization')
    r=client.post('/api/auth/login',json={'email':'test@example.com','password':'SafePassword123'})
    assert r.status_code==200 and r.json()['mfa_required'] is True
    mfa_token=r.json()['mfa_token']
    assert client.post('/api/auth/login/2fa',json={'mfa_token':mfa_token,'code':'000000'}).status_code==401
    r=client.post('/api/auth/login/2fa',json={'mfa_token':mfa_token,'code':pyotp.TOTP(secret).now()})
    assert r.status_code==200
    client.headers['Authorization']='Bearer '+r.json()['access_token']
    r=client.post('/api/auth/login',json={'email':'test@example.com','password':'SafePassword123'})
    mfa_token=r.json()['mfa_token']
    assert client.post('/api/auth/login/2fa',json={'mfa_token':mfa_token,'code':codes[0]}).status_code==200
    r=client.post('/api/auth/login',json={'email':'test@example.com','password':'SafePassword123'})
    mfa_token=r.json()['mfa_token']
    assert client.post('/api/auth/login/2fa',json={'mfa_token':mfa_token,'code':codes[0]}).status_code==401

def test_totp_disable_requires_password_or_code(client):
    enable_totp(client)
    assert client.post('/api/auth/2fa/disable',json={'password':'wrong'},headers=csrf(client)).status_code==401
    assert client.post('/api/auth/2fa/disable',json={'password':'SafePassword123'},headers=csrf(client)).status_code==200
    assert client.get('/api/auth/me').json()['totp_enabled'] is False

def test_change_email_flow(client):
    other=register(client,'taken@example.com')
    r=client.put('/api/auth/me',json={'email':'taken@example.com'},headers=csrf(client))
    assert r.status_code==409
    r=client.put('/api/auth/me',json={'email':'new@example.com'},headers=csrf(client))
    assert r.status_code==200,r.text
    assert client.get('/api/auth/me').json()['pending_email']=='new@example.com'
    assert client.get('/api/auth/me').json()['email']=='test@example.com'
    change_token=token(client)
    assert client.post('/api/auth/verify-email',json={'token':change_token}).status_code==200
    profile=client.get('/api/auth/me').json()
    assert profile['email']=='new@example.com' and profile['pending_email'] is None

def test_change_password(client):
    bad={'current_password':'wrong','password':'NewPassword123','password_confirmation':'NewPassword123'}
    assert client.post('/api/auth/change-password',json=bad,headers=csrf(client)).status_code==401
    good={'current_password':'SafePassword123','password':'NewPassword123','password_confirmation':'NewPassword123'}
    assert client.post('/api/auth/change-password',json=good,headers=csrf(client)).status_code==200
    assert client.post('/api/auth/login',json={'email':'test@example.com','password':'NewPassword123'}).status_code==200


def test_notification_preferences_default_opt_out_and_validate_lead(client):
    assert client.get('/api/auth/notification-preferences').json() == {
        'reminders_enabled': False,
        'digest_enabled': False,
        'reminder_lead_minutes': 10,
    }

    response = client.put(
        '/api/auth/notification-preferences',
        json={
            'reminders_enabled': True,
            'digest_enabled': True,
            'reminder_lead_minutes': 45,
        },
    )

    assert response.status_code == 200
    assert response.json()['reminder_lead_minutes'] == 45
    assert client.get('/api/auth/notification-preferences').json() == response.json()
    for invalid in (0, 1441):
        assert client.put(
            '/api/auth/notification-preferences',
            json={
                'reminders_enabled': True,
                'digest_enabled': False,
                'reminder_lead_minutes': invalid,
            },
        ).status_code == 422

def test_delete_account_cascades_notes_and_attachments(client):
    n=client.post('/api/notes',json=NOTE).json()
    attachment=client.post('/api/notes/'+n['id']+'/attachments',files={'file':('x.txt',b'bye')}).json()
    assert client.delete('/api/notes/'+n['id']).status_code==204
    assert (STORAGE / attachment['id']).exists()
    assert client.request('DELETE','/api/auth/me',json={'password':'wrong'},headers=csrf(client)).status_code==401
    r=client.request('DELETE','/api/auth/me',json={'password':'SafePassword123'},headers=csrf(client))
    assert r.status_code==200,r.text
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'email':'test@example.com','password':'SafePassword123'}).status_code==401
    with SessionLocal() as db:
        assert db.scalar(select(auth.User))is None
        assert db.scalar(select(Note))is None
    assert not (STORAGE / attachment['id']).exists()


def test_delete_account_restores_files_when_database_commit_fails(client, monkeypatch):
    n=client.post('/api/notes',json=NOTE).json()
    attachment=client.post('/api/notes/'+n['id']+'/attachments',files={'file':('x.txt',b'bye')}).json()
    attachment_path=STORAGE / attachment['id']
    trash_path=STORAGE / '.trash' / attachment['id']
    original_commit=Session.commit

    def fail_commit(session):
        raise RuntimeError('temporary database failure')

    monkeypatch.setattr(Session,'commit',fail_commit)
    with pytest.raises(RuntimeError,match='temporary database failure'):
        client.request('DELETE','/api/auth/me',json={'password':'SafePassword123'},headers=csrf(client))
    with SessionLocal() as db:
        assert db.scalar(select(auth.User))is not None
        assert db.scalar(select(Note))is not None
    assert attachment_path.read_bytes()==b'bye'
    assert not trash_path.exists()

    monkeypatch.setattr(Session,'commit',original_commit)
    assert client.request('DELETE','/api/auth/me',json={'password':'SafePassword123'},headers=csrf(client)).status_code==200
    assert not attachment_path.exists()


def test_delete_account_queues_failed_final_file_removal(client, monkeypatch):
    n=client.post('/api/notes',json=NOTE).json()
    attachment=client.post('/api/notes/'+n['id']+'/attachments',files={'file':('x.txt',b'bye')}).json()
    attachment_path=STORAGE / attachment['id']
    trash_path=STORAGE / '.trash' / attachment['id']
    original_unlink=Path.unlink

    def fail_trash_cleanup(path, *, missing_ok=False):
        if path == trash_path:
            raise PermissionError('temporary cleanup failure')
        return original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path,'unlink',fail_trash_cleanup)
    assert client.request('DELETE','/api/auth/me',json={'password':'SafePassword123'},headers=csrf(client)).status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(auth.User))is None
        assert db.scalar(select(Note))is None
    assert not attachment_path.exists()
    assert trash_path.read_bytes()==b'bye'

    monkeypatch.setattr(Path,'unlink',original_unlink)
    assert purge_deleted()==0
    assert not trash_path.exists()
