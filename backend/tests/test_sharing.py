from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from threading import Event, Thread

from app.auth.models import User
from app.auth import routes as auth_routes
from app.main import app, engine
from app.notes import routes as note_routes
from app.notes import sharing as sharing_routes

from conftest import HEADERS, register, signed_in


NOTE = {
    'title': 'Shared planning',
    'content': 'Initial notes',
    'attendees': 'Team',
    'meeting_date': '2026-09-18',
    'scheduled_at': None,
}


def create_note(client, **changes):
    response = client.post('/api/notes', json={**NOTE, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def use_token(client, session):
    client.headers['Authorization'] = 'Bearer ' + session['access_token']


def test_sharing_permission_matrix_revocation_lists_search_and_every_note_route(raw):
    owner = signed_in(raw, 'owner@example.com')
    owned = create_note(raw)
    attachment = raw.post(
        f"/api/notes/{owned['id']}/attachments",
        files={'file': ('agenda.txt', b'agenda', 'text/plain')},
    ).json()
    item = raw.post(
        f"/api/notes/{owned['id']}/action-items",
        json={'text': 'Owner task'},
    ).json()

    viewer = signed_in(raw, 'viewer@example.com')
    editor = signed_in(raw, 'editor@example.com')
    stranger = signed_in(raw, 'stranger@example.com')
    use_token(raw, owner)

    view_share = raw.post(
        f"/api/notes/{owned['id']}/shares",
        json={'email': 'viewer@example.com', 'permission': 'view'},
    )
    edit_share = raw.post(
        f"/api/notes/{owned['id']}/shares",
        json={'email': 'editor@example.com', 'permission': 'edit'},
    )
    assert view_share.status_code == 201, view_share.text
    assert edit_share.status_code == 201, edit_share.text
    shares = raw.get(f"/api/notes/{owned['id']}/shares").json()
    assert [(share['email'], share['permission']) for share in shares] == [
        ('editor@example.com', 'edit'),
        ('viewer@example.com', 'view'),
    ]

    use_token(raw, viewer)
    detail = raw.get(f"/api/notes/{owned['id']}")
    assert detail.status_code == 200
    assert detail.json()['effective_permission'] == 'view'
    assert detail.json()['is_owner'] is False
    listed = raw.get('/api/notes', params={'q': 'planning', 'limit': 1}).json()
    assert listed['total'] == 1
    assert [entry['id'] for entry in listed['items']] == [owned['id']]
    assert raw.get(f"/api/notes/{owned['id']}/export", params={'format': 'md'}).status_code == 200
    assert raw.get(f"/api/notes/{owned['id']}/attachments/{attachment['id']}").content == b'agenda'
    assert raw.put(f"/api/notes/{owned['id']}", json={**NOTE, 'content': 'blocked'}).status_code == 403
    assert raw.post(f"/api/notes/{owned['id']}/action-items", json={'text': 'blocked'}).status_code == 403
    assert raw.patch(f"/api/action-items/{item['id']}", json={'done': True}).status_code == 403
    assert raw.delete(f"/api/action-items/{item['id']}").status_code == 403
    assert raw.post(
        f"/api/notes/{owned['id']}/attachments",
        files={'file': ('blocked.txt', b'blocked')},
    ).status_code == 403
    assert raw.delete(f"/api/notes/{owned['id']}/attachments/{attachment['id']}").status_code == 403
    assert raw.delete(f"/api/notes/{owned['id']}").status_code == 404
    assert raw.get(f"/api/notes/{owned['id']}/shares").status_code == 404

    use_token(raw, editor)
    detail = raw.get(f"/api/notes/{owned['id']}").json()
    assert detail['effective_permission'] == 'edit'
    assert detail['is_owner'] is False
    update = raw.put(
        f"/api/notes/{owned['id']}",
        json={**NOTE, 'content': 'Edited collaboratively'},
    )
    assert update.status_code == 200, update.text
    assert update.json()['content'] == 'Edited collaboratively'
    assert raw.put(
        f"/api/notes/{owned['id']}",
        json={**NOTE, 'scheduled_at': '2026-09-19T12:00:00Z'},
    ).status_code == 403
    editor_item = raw.post(
        f"/api/notes/{owned['id']}/action-items",
        json={'text': 'Editor task'},
    )
    assert editor_item.status_code == 201
    assert raw.patch(f"/api/action-items/{editor_item.json()['id']}", json={'done': True}).status_code == 200
    assert raw.delete(f"/api/action-items/{editor_item.json()['id']}").status_code == 204
    editor_attachment = raw.post(
        f"/api/notes/{owned['id']}/attachments",
        files={'file': ('editor.txt', b'editor')},
    )
    assert editor_attachment.status_code == 201
    assert raw.delete(
        f"/api/notes/{owned['id']}/attachments/{editor_attachment.json()['id']}"
    ).status_code == 204
    assert raw.get(f"/api/notes/{owned['id']}/export", params={'format': 'pdf'}).status_code == 200
    assert raw.delete(f"/api/notes/{owned['id']}").status_code == 404
    assert raw.post(
        f"/api/notes/{owned['id']}/shares",
        json={'email': 'stranger@example.com', 'permission': 'view'},
    ).status_code == 404

    use_token(raw, stranger)
    assert raw.get('/api/notes').json() == {'items': [], 'total': 0}
    assert raw.get('/api/notes', params={'q': 'planning'}).json() == {'items': [], 'total': 0}
    assert raw.get(f"/api/notes/{owned['id']}").status_code == 404
    assert raw.get(f"/api/notes/{owned['id']}/export", params={'format': 'md'}).status_code == 404
    assert raw.get(f"/api/notes/{owned['id']}/attachments/{attachment['id']}").status_code == 404
    assert raw.patch(f"/api/action-items/{item['id']}", json={'done': True}).status_code == 404

    use_token(raw, owner)
    assert raw.delete(f"/api/notes/{owned['id']}/shares/{viewer['user']['id']}").status_code == 204
    use_token(raw, viewer)
    assert raw.get(f"/api/notes/{owned['id']}").status_code == 404
    assert raw.get('/api/notes').json() == {'items': [], 'total': 0}

    use_token(raw, owner)
    deleted = create_note(raw, title='Delete ownership')
    assert raw.post(
        f"/api/notes/{deleted['id']}/shares",
        json={'email': 'viewer@example.com', 'permission': 'edit'},
    ).status_code == 201
    assert raw.delete(f"/api/notes/{deleted['id']}").status_code == 204
    use_token(raw, viewer)
    assert raw.post(f"/api/notes/{deleted['id']}/undelete").status_code == 404
    use_token(raw, owner)
    restored = raw.post(f"/api/notes/{deleted['id']}/undelete")
    assert restored.status_code == 200
    assert restored.json()['effective_permission'] == 'owner'
    assert restored.json()['is_owner'] is True


def test_share_target_privacy_previous_contacts_and_account_cascades(raw):
    owner = signed_in(raw, 'owner@example.com')
    note = create_note(raw)
    recipient = signed_in(raw, 'recipient@example.com')
    outsider = signed_in(raw, 'outsider@example.com')

    register(raw, 'unverified@example.com')
    use_token(raw, owner)
    unverified = raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'unverified@example.com', 'permission': 'view'},
    )
    missing = raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'missing@example.com', 'permission': 'view'},
    )
    assert unverified.status_code == missing.status_code == 404
    assert unverified.json() == missing.json()

    with Session(engine) as session:
        session.add(User(
            email='recipient@example.com',
            auth_provider='google',
            email_verified=True,
            display_name='Duplicate',
        ))
        session.commit()
    ambiguous = raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'recipient@example.com', 'permission': 'view'},
    )
    assert ambiguous.status_code == 404
    assert ambiguous.json() == missing.json()
    with Session(engine) as session:
        duplicate = session.scalar(select(User).where(
            User.email == 'recipient@example.com',
            User.auth_provider == 'google',
        ))
        session.delete(duplicate)
        session.commit()

    with Session(engine) as session:
        session.add(User(
            email='owner@example.com',
            auth_provider='google',
            email_verified=True,
            display_name='Owner duplicate',
        ))
        session.commit()
    owner_ambiguous = raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'owner@example.com', 'permission': 'view'},
    )
    assert owner_ambiguous.status_code == 404
    assert owner_ambiguous.json() == missing.json()
    with Session(engine) as session:
        duplicate = session.scalar(select(User).where(
            User.email == 'owner@example.com',
            User.auth_provider == 'google',
        ))
        session.delete(duplicate)
        session.commit()

    created = raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'recipient@example.com', 'permission': 'view'},
    )
    assert created.status_code == 201
    updated = raw.patch(
        f"/api/notes/{note['id']}/shares/{recipient['user']['id']}",
        json={'permission': 'edit'},
    )
    assert updated.status_code == 200
    assert updated.json()['permission'] == 'edit'
    assert raw.delete(f"/api/notes/{note['id']}/shares/{recipient['user']['id']}").status_code == 204

    previous_two = signed_in(raw, 'previous-two@example.com')
    use_token(raw, owner)
    assert raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'previous-two@example.com', 'permission': 'view'},
    ).status_code == 201
    assert raw.delete(f"/api/notes/{note['id']}/shares/{previous_two['user']['id']}").status_code == 204

    contacts = raw.get('/api/sharing/contacts')
    assert contacts.status_code == 200
    assert [(entry['user_id'], entry['email']) for entry in contacts.json()] == [
        (previous_two['user']['id'], 'previous-two@example.com'),
        (recipient['user']['id'], 'recipient@example.com'),
    ]
    rejected_bulk = raw.post(
        f"/api/notes/{note['id']}/shares/previous",
        json={'permission': 'view', 'user_ids': [outsider['user']['id']]},
    )
    assert rejected_bulk.status_code == 409
    bulk = raw.post(
        f"/api/notes/{note['id']}/shares/previous",
        json={'permission': 'view', 'user_ids': [recipient['user']['id']]},
    )
    assert bulk.status_code == 200
    assert [entry['user_id'] for entry in bulk.json()] == [recipient['user']['id']]
    use_token(raw, recipient)
    assert raw.get(f"/api/notes/{note['id']}").status_code == 200
    use_token(raw, outsider)
    assert raw.get(f"/api/notes/{note['id']}").status_code == 404

    use_token(raw, recipient)
    deleted = raw.request(
        'DELETE',
        '/api/auth/me',
        json={'password': 'SafePassword123', 'confirmation': ''},
    )
    assert deleted.status_code == 200
    use_token(raw, owner)
    assert raw.get(f"/api/notes/{note['id']}/shares").json() == []
    assert raw.get('/api/sharing/contacts').json() == [contacts.json()[0]]

    use_token(raw, owner)
    assert raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'outsider@example.com', 'permission': 'view'},
    ).status_code == 201
    owner_deleted = raw.request(
        'DELETE',
        '/api/auth/me',
        json={'password': 'SafePassword123', 'confirmation': ''},
    )
    assert owner_deleted.status_code == 200
    use_token(raw, outsider)
    assert raw.get('/api/notes').json() == {'items': [], 'total': 0}
    assert raw.get(f"/api/notes/{note['id']}").status_code == 404


def test_revocation_waits_for_in_flight_editor_mutation(raw, monkeypatch):
    owner = signed_in(raw, 'owner@example.com')
    note = create_note(raw)
    editor = signed_in(raw, 'editor@example.com')
    use_token(raw, owner)
    assert raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'editor@example.com', 'permission': 'edit'},
    ).status_code == 201

    mutation_locked = Event()
    release_mutation = Event()
    revoke_started = Event()
    revoke_done = Event()
    responses = {}
    original_now = note_routes.now

    def pause_after_authorization():
        mutation_locked.set()
        assert release_mutation.wait(5)
        return original_now()

    monkeypatch.setattr(note_routes, 'now', pause_after_authorization)

    def edit_note():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + editor['access_token']}) as client:
            responses['edit'] = client.put(
                f"/api/notes/{note['id']}",
                json={**NOTE, 'content': 'Committed before revocation'},
            )

    def revoke_editor():
        revoke_started.set()
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']}) as client:
            responses['revoke'] = client.delete(
                f"/api/notes/{note['id']}/shares/{editor['user']['id']}"
            )
        revoke_done.set()

    edit_thread = Thread(target=edit_note)
    edit_thread.start()
    assert mutation_locked.wait(5)
    revoke_thread = Thread(target=revoke_editor)
    revoke_thread.start()
    assert revoke_started.wait(5)
    assert not revoke_done.wait(0.2)
    release_mutation.set()
    edit_thread.join(5)
    revoke_thread.join(5)

    assert responses['edit'].status_code == 200
    assert responses['revoke'].status_code == 204
    use_token(raw, owner)
    assert raw.get(f"/api/notes/{note['id']}").json()['content'] == 'Committed before revocation'
    use_token(raw, editor)
    assert raw.put(f"/api/notes/{note['id']}", json=NOTE).status_code == 404


def test_revocation_that_locks_first_blocks_later_editor_mutation(raw, monkeypatch):
    owner = signed_in(raw, 'owner@example.com')
    note = create_note(raw)
    editor = signed_in(raw, 'editor@example.com')
    use_token(raw, owner)
    assert raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'editor@example.com', 'permission': 'edit'},
    ).status_code == 201

    revocation_locked = Event()
    release_revocation = Event()
    edit_done = Event()
    responses = {}
    original_get_note = sharing_routes.get_note

    def pause_after_lock(*args, **kwargs):
        result = original_get_note(*args, **kwargs)
        revocation_locked.set()
        assert release_revocation.wait(5)
        return result

    monkeypatch.setattr(sharing_routes, 'get_note', pause_after_lock)

    def revoke_editor():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']}) as client:
            responses['revoke'] = client.delete(
                f"/api/notes/{note['id']}/shares/{editor['user']['id']}"
            )

    def edit_note():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + editor['access_token']}) as client:
            responses['edit'] = client.put(
                f"/api/notes/{note['id']}",
                json={**NOTE, 'content': 'Must not commit'},
            )
        edit_done.set()

    revoke_thread = Thread(target=revoke_editor)
    revoke_thread.start()
    assert revocation_locked.wait(5)
    edit_thread = Thread(target=edit_note)
    edit_thread.start()
    assert not edit_done.wait(0.2)
    release_revocation.set()
    revoke_thread.join(5)
    edit_thread.join(5)

    assert responses['revoke'].status_code == 204
    assert responses['edit'].status_code == 404
    use_token(raw, owner)
    assert raw.get(f"/api/notes/{note['id']}").json()['content'] == 'Initial notes'


def test_recipient_deletion_that_locks_first_blocks_later_editor_mutation(raw, monkeypatch):
    owner = signed_in(raw, 'owner@example.com')
    note = create_note(raw)
    editor = signed_in(raw, 'editor@example.com')
    use_token(raw, owner)
    assert raw.post(
        f"/api/notes/{note['id']}/shares",
        json={'email': 'editor@example.com', 'permission': 'edit'},
    ).status_code == 201

    deletion_locked = Event()
    release_deletion = Event()
    edit_done = Event()
    responses = {}
    original_quarantine = auth_routes.quarantine_files

    def pause_after_note_locks(attachment_ids):
        deletion_locked.set()
        assert release_deletion.wait(5)
        return original_quarantine(attachment_ids)

    monkeypatch.setattr(auth_routes, 'quarantine_files', pause_after_note_locks)

    def delete_editor():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + editor['access_token']}) as client:
            responses['delete'] = client.request(
                'DELETE',
                '/api/auth/me',
                json={'password': 'SafePassword123', 'confirmation': ''},
            )

    def edit_note():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + editor['access_token']}) as client:
            responses['edit'] = client.put(
                f"/api/notes/{note['id']}",
                json={**NOTE, 'content': 'Must not commit'},
            )
        edit_done.set()

    delete_thread = Thread(target=delete_editor)
    delete_thread.start()
    assert deletion_locked.wait(5)
    edit_thread = Thread(target=edit_note)
    edit_thread.start()
    assert not edit_done.wait(0.2)
    release_deletion.set()
    delete_thread.join(5)
    edit_thread.join(5)

    assert responses['delete'].status_code == 200
    assert responses['edit'].status_code == 404
    use_token(raw, owner)
    assert raw.get(f"/api/notes/{note['id']}").json()['content'] == 'Initial notes'


def test_account_deletion_that_locks_first_blocks_later_note_creation(raw, monkeypatch):
    owner = signed_in(raw, 'owner@example.com')
    deletion_locked = Event()
    release_deletion = Event()
    create_done = Event()
    responses = {}
    original_quarantine = auth_routes.quarantine_files

    def pause_after_account_lock(attachment_ids):
        deletion_locked.set()
        assert release_deletion.wait(5)
        return original_quarantine(attachment_ids)

    monkeypatch.setattr(auth_routes, 'quarantine_files', pause_after_account_lock)

    def delete_owner():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']}) as client:
            responses['delete'] = client.request(
                'DELETE',
                '/api/auth/me',
                json={'password': 'SafePassword123', 'confirmation': ''},
            )

    def create_owned_note():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']}) as client:
            responses['create'] = client.post('/api/notes', json=NOTE)
        create_done.set()

    delete_thread = Thread(target=delete_owner)
    delete_thread.start()
    assert deletion_locked.wait(5)
    create_thread = Thread(target=create_owned_note)
    create_thread.start()
    assert not create_done.wait(0.2)
    release_deletion.set()
    delete_thread.join(5)
    create_thread.join(5)

    assert responses['delete'].status_code == 200
    assert responses['create'].status_code == 401


def test_action_item_delete_that_locks_first_makes_later_patch_not_found(raw, monkeypatch):
    owner = signed_in(raw, 'owner@example.com')
    note = create_note(raw)
    item = raw.post(
        f"/api/notes/{note['id']}/action-items",
        json={'text': 'Concurrent item'},
    ).json()
    deletion_locked = Event()
    release_deletion = Event()
    patch_done = Event()
    responses = {}
    original_get_action_item = note_routes.get_action_item

    def pause_first_request(*args, **kwargs):
        result = original_get_action_item(*args, **kwargs)
        if not deletion_locked.is_set():
            deletion_locked.set()
            assert release_deletion.wait(5)
        return result

    monkeypatch.setattr(note_routes, 'get_action_item', pause_first_request)

    def delete_item():
        with TestClient(app, headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']}) as client:
            responses['delete'] = client.delete(f"/api/action-items/{item['id']}")

    def patch_item():
        with TestClient(
            app,
            headers={**HEADERS, 'Authorization': 'Bearer ' + owner['access_token']},
            raise_server_exceptions=False,
        ) as client:
            responses['patch'] = client.patch(f"/api/action-items/{item['id']}", json={'done': True})
        patch_done.set()

    delete_thread = Thread(target=delete_item)
    delete_thread.start()
    assert deletion_locked.wait(5)
    patch_thread = Thread(target=patch_item)
    patch_thread.start()
    assert not patch_done.wait(0.2)
    release_deletion.set()
    delete_thread.join(5)
    patch_thread.join(5)

    assert responses['delete'].status_code == 204
    assert responses['patch'].status_code == 404
