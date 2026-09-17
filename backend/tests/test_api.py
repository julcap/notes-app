import os
import tempfile
os.environ['UPLOAD_DIR'] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from app.main import app, Base, engine, STORAGE
from sqlalchemy import text
import pytest

from conftest import signed_in

def note(client, title='Planning', content='Decide the launch date', attendees='Alex', meeting_date='2026-09-17'):
    response = client.post('/api/notes', json={'title':title,'content':content,'attendees':attendees,'meeting_date':meeting_date})
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


def test_postgresql_full_text_search_ranking_updates_safety_and_ownership(raw):
    owner = signed_in(raw)
    title_match = note(raw, title='Launch brief', content='agenda', attendees='')
    content_match = note(raw, title='Weekly brief', content='launch launch launch', attendees='')
    attendee_match = note(raw, title='Introductions', content='', attendees='Alex')
    first_tie = note(raw, title='Orbit', content='', attendees='')
    second_tie = note(raw, title='Orbit', content='', attendees='')
    older_meeting = note(raw, title='Roadmap priorityterm', content='', attendees='', meeting_date='2026-09-16')
    newer_meeting = note(raw, title='Roadmap priorityterm', content='', attendees='', meeting_date='2026-09-18')
    older_update = note(raw, title='Status updatedterm', content='', attendees='')
    newer_update = note(raw, title='Status updatedterm', content='', attendees='')
    editable = note(raw, title='Editable', content='old content', attendees='')

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE notes SET updated_at = '2026-09-17T12:00:00Z' WHERE id IN (:first, :second)"),
            {'first': first_tie['id'], 'second': second_tie['id']},
        )
        connection.execute(
            text("UPDATE notes SET updated_at = CASE id WHEN :older THEN '2026-09-17T11:00:00Z'::timestamptz ELSE '2026-09-17T13:00:00Z'::timestamptz END WHERE id IN (:older, :newer)"),
            {'older': older_update['id'], 'newer': newer_update['id']},
        )

    launch_results = raw.get('/api/notes', params={'q': 'LAUNCH'}).json()
    assert [item['id'] for item in launch_results] == [title_match['id'], content_match['id']]
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'orbit'}).json()] == sorted([first_tie['id'], second_tie['id']])
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'priorityterm'}).json()] == [newer_meeting['id'], older_meeting['id']]
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'updatedterm'}).json()] == [newer_update['id'], older_update['id']]
    assert raw.get('/api/notes', params={'q': 'Alex'}).json()[0]['id'] == attendee_match['id']
    assert raw.get('/api/notes', params={'q': '%_\\'}).json() == []
    assert raw.get('/api/notes', params={'q': "launch'); DROP TABLE notes; --"}).json() == []
    assert raw.get('/api/notes', params={'q': '   '}).json() == raw.get('/api/notes').json()

    editable['content'] = 'Now contains the indexed phrase nebula'
    assert raw.put('/api/notes/' + editable['id'], json=editable).status_code == 200
    assert raw.get('/api/notes', params={'q': 'nebula'}).json()[0]['id'] == editable['id']

    signed_in(raw, 'other@example.com')
    other_note = note(raw, title='Private quasar', content='', attendees='')
    assert raw.get('/api/notes', params={'q': 'launch'}).json() == []

    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    assert raw.get('/api/notes', params={'q': 'quasar'}).json() == []
    assert raw.get('/api/notes/' + other_note['id']).status_code == 404
    assert raw.get('/api/notes', params={'q': 'x' * 201}).status_code == 422

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
