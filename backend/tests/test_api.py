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

def test_action_items_crud_and_ownership(client):
    n = note(client)
    base = '/api/notes/'+n['id']+'/action-items'
    assert client.get('/api/notes/'+n['id']).json()['action_items'] == []
    response = client.post(base, json={'text':'Send recap email','owner_name':'Alex','due_date':'2026-09-20'})
    assert response.status_code == 201
    item = response.json()
    assert item['text'] == 'Send recap email' and item['owner_name'] == 'Alex' and item['due_date'] == '2026-09-20' and item['done'] is False
    assert client.post(base, json={'text':'   '}).status_code == 422
    minimal = client.post(base, json={'text':'Follow up'}).json()
    assert minimal['owner_name'] == '' and minimal['due_date'] is None
    assert [i['id'] for i in client.get('/api/notes/'+n['id']).json()['action_items']] == [item['id'], minimal['id']]

    patched = client.patch('/api/action-items/'+item['id'], json={'done':True})
    assert patched.status_code == 200 and patched.json()['done'] is True and patched.json()['text'] == 'Send recap email'
    patched = client.patch('/api/action-items/'+item['id'], json={'text':'Send the recap email','due_date':None})
    assert patched.json()['text'] == 'Send the recap email' and patched.json()['due_date'] is None and patched.json()['done'] is True
    assert client.patch('/api/action-items/'+item['id'], json={'text':'  '}).status_code == 422

    other = note(client, 'Other')
    other_item = client.post('/api/notes/'+other['id']+'/action-items', json={'text':'Other task'}).json()
    assert client.post('/api/notes/does-not-exist/action-items', json={'text':'x'}).status_code == 404

    assert client.delete('/api/action-items/'+minimal['id']).status_code == 204
    assert client.patch('/api/action-items/'+minimal['id'], json={'done':True}).status_code == 404

    assert client.delete('/api/notes/'+n['id']).status_code == 204
    assert client.patch('/api/action-items/'+item['id'], json={'done':False}).status_code == 404
    assert client.delete('/api/action-items/'+other_item['id']).status_code == 204
