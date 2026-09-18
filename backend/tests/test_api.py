import os
import tempfile
from io import BytesIO
from datetime import datetime, timezone
os.environ['UPLOAD_DIR'] = tempfile.mkdtemp()
from fastapi.testclient import TestClient
from app.main import app, Base, engine, STORAGE
from app.notes import routes as note_routes
from app.notes.models import Attachment
from sqlalchemy import text
from sqlalchemy.orm import Session
import pytest

from conftest import signed_in


PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99\r\x1d'
    b'\x00\x00\x00\x00IEND\xaeB`\x82'
)
JPEG_BYTES = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9'
GIF_BYTES = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
WEBP_BYTES = b'RIFF\x18\x00\x00\x00WEBPVP8 \n\x00\x00\x00\x2f\x00\x00\x00\x00\x07\x10\xfd\x8f\xfe\x07\x00'
PDF_BYTES = b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n'

def note(client, title='Planning', content='Decide the launch date', attendees='Alex', meeting_date='2026-09-17'):
    response = client.post('/api/notes', json={'title':title,'content':content,'attendees':attendees,'meeting_date':meeting_date})
    assert response.status_code == 201
    return response.json()

def test_crud_search_and_validation(client):
    n = note(client)
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/notes', params={'q':'LAUNCH'}).json()['items'][0]['id'] == n['id']
    assert client.get('/api/notes', params={'q':'Alex'}).json()['items'][0]['id'] == n['id']
    assert client.get('/api/notes', params={'q':'%'}).json() == {'items': [], 'total': 0}
    assert client.post('/api/notes',json={'title':'  ','meeting_date':'2026-09-17'}).status_code == 422
    n['title']='Updated'
    assert client.put('/api/notes/'+n['id'], json=n).json()['title'] == 'Updated'
    assert client.get('/api/notes/'+n['id']).json()['title'] == 'Updated'
    assert client.delete('/api/notes/'+n['id']).status_code == 204
    assert client.get('/api/notes/'+n['id']).status_code == 404


def test_scheduled_time_requires_timezone_and_is_normalized_to_utc(client):
    payload = {
        'title': 'DST planning',
        'content': '',
        'attendees': '',
        'meeting_date': '2026-03-08',
        'scheduled_at': '2026-03-08T01:30:00-05:00',
    }

    response = client.post('/api/notes', json=payload)

    assert response.status_code == 201
    assert response.json()['scheduled_at'] == '2026-03-08T06:30:00Z'
    assert client.post('/api/notes', json={**payload, 'scheduled_at': '2026-03-08T01:30:00'}).status_code == 422
    updated = client.put(
        f"/api/notes/{response.json()['id']}",
        json={**payload, 'scheduled_at': None},
    )
    assert updated.status_code == 200
    assert updated.json()['scheduled_at'] is None


def test_soft_delete_hides_note_children_and_preserves_attachment(client, monkeypatch):
    deleted_at = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(note_routes, 'now', lambda: deleted_at)
    n = note(client)
    attachment = client.post(
        f"/api/notes/{n['id']}/attachments",
        files={'file': ('evidence.txt', b'keep me', 'text/plain')},
    ).json()
    action_item = client.post(
        f"/api/notes/{n['id']}/action-items",
        json={'text': 'Follow up'},
    ).json()
    attachment_path = STORAGE / attachment['id']

    assert client.delete(f"/api/notes/{n['id']}").status_code == 204
    assert attachment_path.read_bytes() == b'keep me'
    assert client.get('/api/notes').json() == {'items': [], 'total': 0}
    assert client.get(f"/api/notes/{n['id']}").status_code == 404
    assert client.put(f"/api/notes/{n['id']}", json=n).status_code == 404
    assert client.post(
        f"/api/notes/{n['id']}/attachments",
        files={'file': ('hidden.txt', b'hidden', 'text/plain')},
    ).status_code == 404
    assert client.get(f"/api/notes/{n['id']}/attachments/{attachment['id']}").status_code == 404
    assert client.delete(f"/api/notes/{n['id']}/attachments/{attachment['id']}").status_code == 404
    assert client.post(
        f"/api/notes/{n['id']}/action-items",
        json={'text': 'Hidden task'},
    ).status_code == 404
    assert client.patch(f"/api/action-items/{action_item['id']}", json={'done': True}).status_code == 404
    assert client.delete(f"/api/action-items/{action_item['id']}").status_code == 404
    assert client.delete(f"/api/notes/{n['id']}").status_code == 404

    monkeypatch.setattr(note_routes, 'now', lambda: deleted_at.replace(second=15))
    restored = client.post(f"/api/notes/{n['id']}/undelete")

    assert restored.status_code == 200
    assert restored.json()['id'] == n['id']
    assert client.get('/api/notes').json()['total'] == 1
    assert client.get(f"/api/notes/{n['id']}/attachments/{attachment['id']}").content == b'keep me'


def test_undelete_rejects_other_users_and_expired_windows(raw, monkeypatch):
    deleted_at = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(note_routes, 'now', lambda: deleted_at)
    owner = signed_in(raw)
    n = note(raw)
    assert raw.delete(f"/api/notes/{n['id']}").status_code == 204

    signed_in(raw, 'other@example.com')
    assert raw.post(f"/api/notes/{n['id']}/undelete").status_code == 404

    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    monkeypatch.setattr(
        note_routes,
        'now',
        lambda: datetime(2026, 9, 17, 12, 0, 15, 1, tzinfo=timezone.utc),
    )
    response = raw.post(f"/api/notes/{n['id']}/undelete")
    assert response.status_code == 409
    assert response.json()['detail'] == 'Undo window has expired'
    assert raw.get(f"/api/notes/{n['id']}").status_code == 404


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

    launch_results = raw.get('/api/notes', params={'q': 'LAUNCH'}).json()['items']
    assert [item['id'] for item in launch_results] == [title_match['id'], content_match['id']]
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'orbit'}).json()['items']] == sorted([first_tie['id'], second_tie['id']])
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'priorityterm'}).json()['items']] == [newer_meeting['id'], older_meeting['id']]
    assert [item['id'] for item in raw.get('/api/notes', params={'q': 'updatedterm'}).json()['items']] == [newer_update['id'], older_update['id']]
    assert raw.get('/api/notes', params={'q': 'Alex'}).json()['items'][0]['id'] == attendee_match['id']
    assert raw.get('/api/notes', params={'q': '%_\\'}).json() == {'items': [], 'total': 0}
    assert raw.get('/api/notes', params={'q': "launch'); DROP TABLE notes; --"}).json() == {'items': [], 'total': 0}
    assert raw.get('/api/notes', params={'q': '   '}).json() == raw.get('/api/notes').json()

    editable['content'] = 'Now contains the indexed phrase nebula'
    assert raw.put('/api/notes/' + editable['id'], json=editable).status_code == 200
    assert raw.get('/api/notes', params={'q': 'nebula'}).json()['items'][0]['id'] == editable['id']

    signed_in(raw, 'other@example.com')
    other_note = note(raw, title='Private quasar', content='', attendees='')
    assert raw.get('/api/notes', params={'q': 'launch'}).json() == {'items': [], 'total': 0}

    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    assert raw.get('/api/notes', params={'q': 'quasar'}).json() == {'items': [], 'total': 0}
    assert raw.get('/api/notes/' + other_note['id']).status_code == 404
    assert raw.get('/api/notes', params={'q': 'x' * 201}).status_code == 422


def test_notes_pagination_boundaries_totals_and_stable_pages(raw):
    owner = signed_in(raw)
    created = [note(raw, title=f'Planning {index}', content='shared phrase') for index in range(5)]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE notes SET updated_at = '2026-09-17T12:00:00Z' WHERE id = ANY(:ids)"),
            {'ids': [item['id'] for item in created]},
        )

    first = raw.get('/api/notes', params={'skip': 0, 'limit': 2}).json()
    second = raw.get('/api/notes', params={'skip': 2, 'limit': 2}).json()
    assert first['total'] == 5
    assert second['total'] == 5
    assert len(first['items']) == 2
    assert len(second['items']) == 2
    assert {item['id'] for item in first['items']}.isdisjoint(item['id'] for item in second['items'])
    assert [item['id'] for item in first['items'] + second['items']] == sorted(
        [item['id'] for item in created]
    )[:4]

    assert raw.get('/api/notes', params={'skip': -1}).status_code == 422
    assert raw.get('/api/notes', params={'limit': 0}).status_code == 422
    assert raw.get('/api/notes', params={'limit': 201}).status_code == 422

    signed_in(raw, 'other@example.com')
    note(raw, title='Other planning', content='shared phrase')
    assert raw.get('/api/notes', params={'q': 'shared'}).json()['total'] == 1

    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    filtered = raw.get('/api/notes', params={'q': 'Planning 1'}).json()
    assert filtered['total'] == 1
    assert filtered['items'][0]['id'] == created[1]['id']

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
    assert (STORAGE / a['id']).read_bytes() == b'Hello meeting'
    assert client.post(base + '/undelete').status_code == 200
    assert client.delete(base + '/attachments/' + a['id']).status_code == 204
    assert not (STORAGE / a['id']).exists()


def test_attachment_inline_preview_requires_matching_safe_signature_and_owner(raw):
    owner = signed_in(raw)
    n = note(raw)
    base = f"/api/notes/{n['id']}/attachments"
    fixtures = [
        ('pixel.png', PNG_BYTES, 'image/png'),
        ('photo.jpg', JPEG_BYTES, 'image/jpeg'),
        ('animation.gif', GIF_BYTES, 'image/gif'),
        ('sample.webp', WEBP_BYTES, 'image/webp'),
        ('document.pdf', PDF_BYTES, 'application/pdf'),
    ]

    uploaded = []
    for filename, content, content_type in fixtures:
        response = raw.post(base, files={'file': (filename, content, content_type)})
        assert response.status_code == 201
        item = response.json()
        assert item['content_type'] == content_type
        uploaded.append((item, content, content_type))

    first, first_content, _ = uploaded[0]
    download = raw.get(f"{base}/{first['id']}")
    assert download.content == first_content
    assert download.headers['content-type'] == 'application/octet-stream'
    assert download.headers['content-disposition'].startswith('attachment;')
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert download.headers['cache-control'] == 'no-store'

    for item, content, content_type in uploaded:
        preview = raw.get(f"{base}/{item['id']}", params={'inline': 'true'})
        assert preview.content == content
        assert preview.headers['content-type'] == content_type
        assert preview.headers['content-disposition'].startswith('inline;')
        assert preview.headers['x-content-type-options'] == 'nosniff'
        assert preview.headers['cache-control'] == 'no-store'

    extension_fallback = raw.post(
        base,
        files={'file': ('fallback.png', PNG_BYTES, 'application/octet-stream')},
    ).json()
    assert extension_fallback['content_type'] == 'image/png'
    assert raw.get(f"{base}/{extension_fallback['id']}", params={'inline': 'true'}).headers['content-type'] == 'image/png'

    unsafe = [
        ('spoofed.png', b'<!doctype html><script>alert(1)</script>', 'image/png'),
        ('vector.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', 'image/svg+xml'),
        ('wrong-mime.jpg', PNG_BYTES, 'image/jpeg'),
        ('broken.pdf', b'not a pdf', 'application/pdf'),
    ]
    for filename, content, content_type in unsafe:
        item = raw.post(base, files={'file': (filename, content, content_type)}).json()
        preview = raw.get(f"{base}/{item['id']}", params={'inline': 'true'})
        assert preview.content == content
        assert preview.headers['content-type'] == 'application/octet-stream'
        assert preview.headers['content-disposition'].startswith('attachment;')

    other = note(raw, title='Other note')
    assert raw.get(
        f"/api/notes/{other['id']}/attachments/{first['id']}",
        params={'inline': 'true'},
    ).status_code == 404

    raw.headers.pop('Authorization')
    assert raw.get(f"{base}/{first['id']}", params={'inline': 'true'}).status_code == 401
    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    signed_in(raw, 'other@example.com')
    assert raw.get(f"{base}/{first['id']}", params={'inline': 'true'}).status_code == 404

    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    assert raw.delete(f"/api/notes/{n['id']}").status_code == 204
    assert raw.get(f"{base}/{first['id']}", params={'inline': 'true'}).status_code == 404

def test_size_limit_and_removal(client):
    n=note(client)
    base='/api/notes/'+n['id']+'/attachments'
    assert client.post(base,files={'file':('large.bin',b'x'*(20*1024*1024+1))}).status_code == 413
    assert client.get('/api/notes/'+n['id']).json()['attachments'] == []
    a=client.post(base,files={'file':('small.txt',b'yes')}).json()
    assert client.delete(base+'/'+a['id']).status_code == 204
    assert client.get(base+'/'+a['id']).status_code == 404


def test_attachment_delete_reconciles_files_after_database_commit_errors(client, monkeypatch):
    n = note(client)
    base = '/api/notes/' + n['id'] + '/attachments'
    first = client.post(base, files={'file': ('first.txt', b'first')}).json()
    first_path = STORAGE / first['id']
    first_trash = STORAGE / '.trash' / first['id']
    original_commit = Session.commit

    def fail_before_commit(session):
        raise RuntimeError('temporary database failure')

    monkeypatch.setattr(Session, 'commit', fail_before_commit)
    with pytest.raises(RuntimeError, match='temporary database failure'):
        client.delete(base + '/' + first['id'])
    assert client.get(base + '/' + first['id']).content == b'first'
    assert first_path.read_bytes() == b'first'
    assert not first_trash.exists()

    monkeypatch.setattr(Session, 'commit', original_commit)
    second = client.post(base, files={'file': ('second.txt', b'second')}).json()
    second_path = STORAGE / second['id']
    second_trash = STORAGE / '.trash' / second['id']

    def commit_then_fail(session):
        original_commit(session)
        raise RuntimeError('commit result was lost')

    monkeypatch.setattr(Session, 'commit', commit_then_fail)
    with pytest.raises(RuntimeError, match='commit result was lost'):
        client.delete(base + '/' + second['id'])
    assert client.get(base + '/' + second['id']).status_code == 404
    assert not second_path.exists()
    assert not second_trash.exists()

    with pytest.raises(RuntimeError, match='commit result was lost'):
        client.post(base, files={'file': ('committed.txt', b'committed')})
    committed = next(
        item for item in client.get('/api/notes/' + n['id']).json()['attachments']
        if item['filename'] == 'committed.txt'
    )
    committed_path = STORAGE / committed['id']
    assert client.get(base + '/' + committed['id']).content == b'committed'
    assert committed_path.read_bytes() == b'committed'
    assert not (STORAGE / '.trash' / committed['id']).exists()

    monkeypatch.setattr(Session, 'commit', original_commit)
    original_refresh = Session.refresh

    def fail_refresh(session, instance, *args, **kwargs):
        raise RuntimeError('refresh failed after commit')

    monkeypatch.setattr(Session, 'refresh', fail_refresh)
    with pytest.raises(RuntimeError, match='refresh failed after commit'):
        client.post(base, files={'file': ('refresh.txt', b'refresh')})
    refreshed = next(
        item for item in client.get('/api/notes/' + n['id']).json()['attachments']
        if item['filename'] == 'refresh.txt'
    )
    refreshed_path = STORAGE / refreshed['id']
    assert client.get(base + '/' + refreshed['id']).content == b'refresh'
    assert refreshed_path.read_bytes() == b'refresh'
    assert not (STORAGE / '.trash' / refreshed['id']).exists()
    monkeypatch.setattr(Session, 'refresh', original_refresh)


def test_attachment_upload_persists_object_key_and_streams_headers(client):
    n = note(client)
    response = client.post(
        f"/api/notes/{n['id']}/attachments",
        files={'file': ('stream.txt', b'streamed bytes', 'text/plain')},
    )
    assert response.status_code == 201
    attachment = response.json()
    with Session(engine) as session:
        row = session.get(Attachment, attachment['id'])
        assert row.object_key == attachment['id']

    downloaded = client.get(f"/api/notes/{n['id']}/attachments/{attachment['id']}")
    assert downloaded.status_code == 200
    assert downloaded.content == b'streamed bytes'
    assert downloaded.headers['content-length'] == str(len(b'streamed bytes'))
    assert downloaded.headers['content-disposition'] == 'attachment; filename="stream.txt"'
    assert downloaded.headers['cache-control'] == 'no-store'
    assert downloaded.headers['x-content-type-options'] == 'nosniff'


def test_attachment_content_disposition_encodes_unicode_and_controls(client):
    n = note(client)
    attachment = client.post(
        f"/api/notes/{n['id']}/attachments",
        files={'file': ('safe.txt', b'content', 'text/plain')},
    ).json()
    with Session(engine) as session:
        row = session.get(Attachment, attachment['id'])
        row.filename = 'résumé\r\nX-Evil: yes.txt'
        session.commit()

    downloaded = client.get(f"/api/notes/{n['id']}/attachments/{attachment['id']}")
    disposition = downloaded.headers['content-disposition']
    assert disposition == (
        "attachment; filename*=utf-8''r%C3%A9sum%C3%A9%0D%0AX-Evil%3A%20yes.txt"
    )
    assert '\r' not in disposition and '\n' not in disposition


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


def test_markdown_export_includes_exact_note_fields_and_action_items(raw):
    owner = signed_in(raw)
    n = note(
        raw,
        title='Quarterly planning',
        content='First line\n\n**Decision:** ship it.',
        attendees='Alex, 李',
    )
    raw.post(
        f"/api/notes/{n['id']}/action-items",
        json={'text': 'Send recap', 'owner_name': 'Zoë', 'due_date': '2026-09-20'},
    )
    completed = raw.post(
        f"/api/notes/{n['id']}/action-items",
        json={'text': 'Close loop'},
    ).json()
    raw.patch(f"/api/action-items/{completed['id']}", json={'done': True})

    response = raw.get(f"/api/notes/{n['id']}/export", params={'format': 'md'})

    assert response.status_code == 200
    assert response.headers['content-type'] == 'text/markdown; charset=utf-8'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-disposition'] == 'attachment; filename="Quarterly-planning.md"'
    assert response.text == (
        '# Quarterly planning\n\n'
        '**Date:** 2026-09-17\n\n'
        '**Attendees:** Alex, 李\n\n'
        '## Notes\n\n'
        'First line\n\n**Decision:** ship it.\n\n'
        '## Action items\n\n'
        '- [ ] Send recap — Owner: Zoë — Due: 2026-09-20\n'
        '- [x] Close loop — Owner: Unassigned — Due: No due date\n'
    )

    unsafe = note(raw, title='../../季度\r\nplan\\file')
    unsafe_response = raw.get(f"/api/notes/{unsafe['id']}/export", params={'format': 'md'})
    disposition = unsafe_response.headers['content-disposition']
    assert disposition == 'attachment; filename="plan-file.md"'
    assert '\r' not in disposition and '\n' not in disposition and '/' not in disposition and '\\' not in disposition

    assert raw.get(f"/api/notes/{n['id']}/export").status_code == 422
    assert raw.get(f"/api/notes/{n['id']}/export", params={'format': 'html'}).status_code == 422

    signed_in(raw, 'other@example.com')
    assert raw.get(f"/api/notes/{n['id']}/export", params={'format': 'md'}).status_code == 404
    raw.headers['Authorization'] = 'Bearer ' + owner['access_token']
    assert raw.delete(f"/api/notes/{n['id']}").status_code == 204
    assert raw.get(f"/api/notes/{n['id']}/export", params={'format': 'md'}).status_code == 404


def test_pdf_export_is_paginated_unicode_text_without_markup_interpretation(client):
    from pypdf import PdfReader

    prefix = '<img src="file:///etc/passwd"> https://example.com/track '
    content = (prefix + ('Long Unicode café Δοκιμή 漢字 😀. ' * 6000))[:100000]
    n = note(client, title='Résumé Δοκιμή 漢字 😀', content=content, attendees='Zoë, Δανάη, 李 😀')
    item = client.post(
        f"/api/notes/{n['id']}/action-items",
        json={'text': 'Verify café Δοκιμή 漢字 😀', 'owner_name': 'Renée', 'due_date': '2026-09-21'},
    ).json()
    client.patch(f"/api/action-items/{item['id']}", json={'done': True})

    response = client.get(f"/api/notes/{n['id']}/export", params={'format': 'pdf'})

    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-disposition'] == 'attachment; filename="Resume.pdf"'
    reader = PdfReader(BytesIO(response.content))
    extracted = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert len(reader.pages) > 1
    assert 'Résumé Δοκιμή 漢字 😀' in extracted
    assert 'Zoë, Δανάη, 李 😀' in extracted
    assert 'Long Unicode café Δοκιμή 漢字 😀.' in extracted
    assert 'Verify café Δοκιμή 漢字 😀' in extracted
    assert 'Completed' in extracted
    assert 'Renée' in extracted
    assert '2026-09-21' in extracted
    assert '<img src="file:///etc/passwd">' in extracted
    assert 'https://example.com/track' in extracted
    assert 'root:x:' not in extracted
