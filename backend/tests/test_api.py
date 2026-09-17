import os
import tempfile
os.environ['UPLOAD_DIR'] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from app.main import app, Base, engine, STORAGE
import pytest

def note(client, title='Planning', content='Decide the launch date'):
    response = client.post('/api/notes', json={'title':title,'content':content,'attendees':'Alex','meeting_date':'2026-09-17'})
    assert response.status_code == 201
    return response.json()

def test_crud_search_and_validation(client):
    n = note(client)
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/notes', params={'q':'LAUNCH'}).json()[0]['id'] == n['id']
    assert client.get('/api/notes', params={'q':'Alex'}).json()[0]['id'] == n['id']
    assert client.get('/api/notes', params={'q':'%'}).json() == []
    assert client.post('/api/notes',json={'title':'  ','meeting_date':'2026-09-17'}).status_code == 422
    n['title']='Updated'
    assert client.put('/api/notes/'+n['id'], json=n).json()['title'] == 'Updated'
    assert client.get('/api/notes/'+n['id']).json()['title'] == 'Updated'
    assert client.delete('/api/notes/'+n['id']).status_code == 204
    assert client.get('/api/notes/'+n['id']).status_code == 404

def test_attachment_roundtrip_and_cascade(client):
    n = note(client)
    base = '/api/notes/'+n['id']
    response = client.post(base+'/attachments',files={'file':('../../example.txt',b'Hello meeting','text/plain')})
    assert response.status_code == 201
    a = response.json()
    assert a['filename'] == 'example.txt'
    assert client.get(base+'/attachments/'+a['id']).content == b'Hello meeting'
    other = note(client, 'Other')
    assert client.get('/api/notes/'+other['id']+'/attachments/'+a['id']).status_code == 404
    assert client.delete('/api/notes/'+other['id']+'/attachments/'+a['id']).status_code == 404
    assert len(client.get(base).json()['attachments']) == 1
    assert client.delete(base).status_code == 204
    assert not (STORAGE / a['id']).exists()

def test_size_limit_and_removal(client):
    n=note(client)
    base='/api/notes/'+n['id']+'/attachments'
    assert client.post(base,files={'file':('large.bin',b'x'*(20*1024*1024+1))}).status_code == 413
    assert client.get('/api/notes/'+n['id']).json()['attachments'] == []
    a=client.post(base,files={'file':('small.txt',b'yes')}).json()
    assert client.delete(base+'/'+a['id']).status_code == 204
    assert client.get(base+'/'+a['id']).status_code == 404
