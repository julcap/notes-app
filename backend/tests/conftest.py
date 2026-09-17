import os
import tempfile
os.environ['UPLOAD_DIR']=tempfile.mkdtemp()
import pytest
from fastapi.testclient import TestClient
from app.main import app, Base, engine
from app import auth
HEADERS={'origin':'http://localhost:8080','x-requested-with':'Minutes'}
@pytest.fixture
def raw(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    messages=[]
    monkeypatch.setattr(auth.email,'send_email',lambda recipient,subject,body:messages.append((recipient,subject,body)))
    with TestClient(app,headers=HEADERS) as c:
        c.messages=messages
        yield c
    Base.metadata.drop_all(engine)

def register(c,email='test@example.com',remember=False):
    r=c.post('/api/auth/register',json={'email':email,'password':'SafePassword123','password_confirmation':'SafePassword123','remember':remember})
    assert r.status_code==201,r.text
    return r.json()

def token(c):
    return c.messages[-1][2].split('#token=')[1].split()[0]

def signed_in(c,email='test@example.com'):
    register(c,email)
    r=c.post('/api/auth/verify-email',json={'token':token(c)})
    assert r.status_code==200,r.text
    c.headers['Authorization']='Bearer '+r.json()['access_token']
    return r.json()

@pytest.fixture
def client(raw):
    signed_in(raw)
    return raw
