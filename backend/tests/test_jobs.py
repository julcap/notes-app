from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.jobs import purge_deleted
from app.notes.models import Note
from app.storage import STORAGE

from test_api import note


def attach(client, note_id, name):
    response = client.post(
        f'/api/notes/{note_id}/attachments',
        files={'file': (name, name.encode(), 'text/plain')},
    )
    assert response.status_code == 201
    return response.json()


def test_purge_deleted_removes_only_notes_older_than_retention(client):
    current_time = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    old = note(client, title='Old deleted note')
    recent = note(client, title='Recent deleted note')
    active = note(client, title='Active note')
    old_attachment = attach(client, old['id'], 'old.txt')
    recent_attachment = attach(client, recent['id'], 'recent.txt')
    assert client.delete(f"/api/notes/{old['id']}").status_code == 204
    assert client.delete(f"/api/notes/{recent['id']}").status_code == 204

    with SessionLocal.begin() as session:
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=31), 'id': old['id']},
        )
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=30), 'id': recent['id']},
        )

    assert purge_deleted(current_time=current_time) == 1

    with SessionLocal() as session:
        assert session.get(Note, old['id']) is None
        assert session.get(Note, recent['id']) is not None
        assert session.get(Note, active['id']) is not None
    assert not (STORAGE / old_attachment['id']).exists()
    assert (STORAGE / recent_attachment['id']).read_bytes() == b'recent.txt'


def test_purge_deleted_queues_failed_final_file_removal(client, monkeypatch):
    current_time = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    deleted = note(client, title='Retry cleanup')
    attachment = attach(client, deleted['id'], 'retry.txt')
    assert client.delete(f"/api/notes/{deleted['id']}").status_code == 204
    with SessionLocal.begin() as session:
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=31), 'id': deleted['id']},
        )

    attachment_path = STORAGE / attachment['id']
    trash_path = STORAGE / '.trash' / attachment['id']
    original_unlink = Path.unlink

    def fail_trash_cleanup(path, *, missing_ok=False):
        if path == trash_path:
            raise PermissionError('temporary cleanup failure')
        return original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, 'unlink', fail_trash_cleanup)
    assert purge_deleted(current_time=current_time) == 1
    with SessionLocal() as session:
        assert session.get(Note, deleted['id']) is None
    assert not attachment_path.exists()
    assert trash_path.read_bytes() == b'retry.txt'

    monkeypatch.setattr(Path, 'unlink', original_unlink)
    assert purge_deleted(current_time=current_time) == 0
    assert not trash_path.exists()


def test_purge_deleted_restores_files_when_database_commit_fails(client, monkeypatch):
    current_time = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    deleted = note(client, title='Retry transaction')
    attachment = attach(client, deleted['id'], 'transaction.txt')
    assert client.delete(f"/api/notes/{deleted['id']}").status_code == 204
    with SessionLocal.begin() as session:
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=31), 'id': deleted['id']},
        )

    attachment_path = STORAGE / attachment['id']
    trash_path = STORAGE / '.trash' / attachment['id']
    original_commit = Session.commit

    def fail_commit(session):
        raise RuntimeError('temporary database failure')

    monkeypatch.setattr(Session, 'commit', fail_commit)
    with pytest.raises(RuntimeError, match='temporary database failure'):
        purge_deleted(current_time=current_time)
    with SessionLocal() as session:
        assert session.get(Note, deleted['id']) is not None
    assert attachment_path.read_bytes() == b'transaction.txt'
    assert not trash_path.exists()

    monkeypatch.setattr(Session, 'commit', original_commit)
    assert purge_deleted(current_time=current_time) == 1
    assert not attachment_path.exists()


def test_purge_deleted_discards_quarantine_when_commit_succeeds_but_result_is_lost(client, monkeypatch):
    current_time = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    deleted = note(client, title='Uncertain transaction')
    attachment = attach(client, deleted['id'], 'uncertain.txt')
    assert client.delete(f"/api/notes/{deleted['id']}").status_code == 204
    with SessionLocal.begin() as session:
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=31), 'id': deleted['id']},
        )

    attachment_path = STORAGE / attachment['id']
    trash_path = STORAGE / '.trash' / attachment['id']
    original_commit = Session.commit

    def commit_then_fail(session):
        original_commit(session)
        raise RuntimeError('commit result was lost')

    monkeypatch.setattr(Session, 'commit', commit_then_fail)
    with pytest.raises(RuntimeError, match='commit result was lost'):
        purge_deleted(current_time=current_time)

    with SessionLocal() as session:
        assert session.get(Note, deleted['id']) is None
    assert not attachment_path.exists()
    assert not trash_path.exists()


def test_purge_deleted_recovers_quarantined_file_with_live_database_row(client):
    active = note(client, title='Interrupted account deletion')
    attachment = attach(client, active['id'], 'recover.txt')
    attachment_path = STORAGE / attachment['id']
    trash_path = STORAGE / '.trash' / attachment['id']
    trash_path.parent.mkdir(exist_ok=True)
    attachment_path.replace(trash_path)

    assert purge_deleted() == 0

    with SessionLocal() as session:
        assert session.get(Note, active['id']) is not None
    assert attachment_path.read_bytes() == b'recover.txt'
    assert not trash_path.exists()


def test_purge_deleted_skips_a_concurrent_run(client, monkeypatch):
    current_time = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    deleted = note(client, title='Concurrent cleanup')
    attachment = attach(client, deleted['id'], 'concurrent.txt')
    assert client.delete(f"/api/notes/{deleted['id']}").status_code == 204
    with SessionLocal.begin() as session:
        session.execute(
            text('UPDATE notes SET deleted_at = :deleted_at WHERE id = :id'),
            {'deleted_at': current_time - timedelta(days=31), 'id': deleted['id']},
        )

    attachment_path = STORAGE / attachment['id']
    original_replace = Path.replace
    cleanup_started = Event()
    release_cleanup = Event()

    def blocked_replace(path, target):
        if path == attachment_path:
            cleanup_started.set()
            assert release_cleanup.wait(timeout=5)
        return original_replace(path, target)

    monkeypatch.setattr(Path, 'replace', blocked_replace)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(purge_deleted, current_time=current_time)
        assert cleanup_started.wait(timeout=5)
        assert purge_deleted(current_time=current_time) == 0
        release_cleanup.set()
        assert first.result(timeout=5) == 1

    with SessionLocal() as session:
        assert session.get(Note, deleted['id']) is None
