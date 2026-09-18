from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import jobs
from app.auth.models import User
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


def enable_notifications(client, *, reminders=False, digest=False, lead=10):
    response = client.put(
        '/api/auth/notification-preferences',
        json={
            'reminders_enabled': reminders,
            'digest_enabled': digest,
            'reminder_lead_minutes': lead,
        },
    )
    assert response.status_code == 200


def scheduled_note(client, title, scheduled_at, meeting_date='2026-09-17'):
    response = client.post(
        '/api/notes',
        json={
            'title': title,
            'content': '',
            'attendees': '',
            'meeting_date': meeting_date,
            'scheduled_at': scheduled_at,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_reminders_respect_opt_in_window_edits_and_normal_deduplication(client):
    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    reminder = scheduled_note(client, 'Planning', '2026-09-18T12:10:00Z')
    sent = []

    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    enable_notifications(client, reminders=True)
    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 1
    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    assert len(sent) == 1
    assert sent[0][0] == 'test@example.com'
    assert 'Planning' in sent[0][2]

    updated = client.put(
        f"/api/notes/{reminder['id']}",
        json={**reminder, 'scheduled_at': '2026-09-18T13:00:00Z'},
    )
    assert updated.status_code == 200
    assert jobs.send_reminders(
        current_time=datetime(2026, 9, 18, 12, 50, tzinfo=timezone.utc),
        sender=lambda *args: sent.append(args),
    ) == 1
    assert len(sent) == 2


def test_reminder_subject_replaces_title_line_breaks(client):
    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    enable_notifications(client, reminders=True)
    scheduled_note(client, 'Planning\r\nBcc: attacker@example.com', '2026-09-18T12:05:00Z')
    sent = []

    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 1
    assert sent[0][1] == 'Meeting starting soon: Planning Bcc: attacker@example.com'
    assert '\r' not in sent[0][1] and '\n' not in sent[0][1]


def test_reminders_skip_deleted_unverified_expired_and_cancelled_notes(raw):
    from conftest import register, signed_in

    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    signed_in(raw)
    enable_notifications(raw, reminders=True)
    deleted = scheduled_note(raw, 'Deleted', '2026-09-18T12:05:00Z')
    assert raw.delete(f"/api/notes/{deleted['id']}").status_code == 204
    scheduled_note(raw, 'Expired', '2026-09-18T11:59:59Z')
    cancelled = scheduled_note(raw, 'Cancelled', '2026-09-18T12:05:00Z')
    assert raw.put(f"/api/notes/{cancelled['id']}", json={**cancelled, 'scheduled_at': None}).status_code == 200

    register(raw, 'unverified@example.com')
    with SessionLocal.begin() as session:
        user = session.query(User).filter_by(email='unverified@example.com').one()
        user.reminders_enabled = True
        session.add(Note(
            owner_id=user.id,
            title='Unverified',
            content='',
            attendees='',
            meeting_date=current_time.date(),
            scheduled_at=current_time + timedelta(minutes=5),
        ))

    sent = []
    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    assert sent == []


def test_failed_reminder_send_retries_without_marking_delivered(client):
    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    enable_notifications(client, reminders=True)
    scheduled_note(client, 'Retry reminder', '2026-09-18T12:05:00Z')

    def fail(*args):
        raise RuntimeError('provider secret: SMTP endpoint and recipient')

    with pytest.raises(RuntimeError, match='Notification delivery failed; retry is safe') as failure:
        jobs.send_reminders(current_time=current_time, sender=fail)
    assert 'provider secret' not in str(failure.value)
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None
    sent = []
    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: sent.append(args)) == 1
    assert len(sent) == 1


def test_one_failed_recipient_does_not_rollback_other_reminders(raw):
    from conftest import signed_in

    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    signed_in(raw)
    enable_notifications(raw, reminders=True)
    scheduled_note(raw, 'First recipient', '2026-09-18T12:01:00Z')
    signed_in(raw, 'other@example.com')
    enable_notifications(raw, reminders=True)
    scheduled_note(raw, 'Second recipient', '2026-09-18T12:02:00Z')
    sent = []

    def fail_first(recipient, subject, body):
        if recipient == 'test@example.com':
            raise RuntimeError('first recipient unavailable')
        sent.append((recipient, subject, body))

    with pytest.raises(RuntimeError, match='Notification delivery failed; retry is safe'):
        jobs.send_reminders(current_time=current_time, sender=fail_first)
    assert [message[0] for message in sent] == ['other@example.com']

    retried = []
    assert jobs.send_reminders(current_time=current_time, sender=lambda *args: retried.append(args)) == 1
    assert [message[0] for message in retried] == ['test@example.com']


def test_concurrent_reminder_jobs_send_once(client):
    current_time = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
    enable_notifications(client, reminders=True)
    scheduled_note(client, 'Concurrent reminder', '2026-09-18T12:05:00Z')
    delivery_started = Event()
    release_delivery = Event()
    sent = []

    def blocked_sender(*args):
        sent.append(args)
        delivery_started.set()
        assert release_delivery.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(
            jobs.send_reminders,
            current_time=current_time,
            sender=blocked_sender,
        )
        assert delivery_started.wait(timeout=5)
        assert jobs.send_reminders(current_time=current_time, sender=blocked_sender) == 0
        release_delivery.set()
        assert first.result(timeout=5) == 1
    assert len(sent) == 1


def test_weekly_digest_uses_previous_week_and_open_owner_actions(client):
    current_time = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
    enable_notifications(client, digest=True)
    first = note(client, title='Monday meeting', meeting_date='2026-09-14')
    note(client, title='Sunday meeting', meeting_date='2026-09-20')
    note(client, title='Boundary excluded', meeting_date='2026-09-21')
    note(client, title='Old excluded', meeting_date='2026-09-13')
    action = client.post(
        f"/api/notes/{first['id']}/action-items",
        json={'text': 'Open follow-up'},
    ).json()
    done = client.post(
        f"/api/notes/{first['id']}/action-items",
        json={'text': 'Completed follow-up'},
    ).json()
    assert client.patch(f"/api/action-items/{done['id']}", json={'done': True}).status_code == 200
    sent = []

    assert jobs.send_weekly_digests(current_time=current_time, sender=lambda *args: sent.append(args)) == 1
    assert jobs.send_weekly_digests(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    assert len(sent) == 1
    body = sent[0][2]
    assert 'Monday meeting' in body and 'Sunday meeting' in body
    assert 'Boundary excluded' not in body and 'Old excluded' not in body
    assert action['text'] in body and done['text'] not in body


def test_weekly_digest_delayed_run_stays_on_monday_week_boundary(client):
    enable_notifications(client, digest=True)
    note(client, title='Previous Monday', meeting_date='2026-09-14')
    note(client, title='Current Monday', meeting_date='2026-09-21')
    sent = []

    assert jobs.send_weekly_digests(
        current_time=datetime(2026, 9, 22, 9, tzinfo=timezone.utc),
        sender=lambda *args: sent.append(args),
    ) == 1
    assert 'Previous Monday' in sent[0][2]
    assert 'Current Monday' not in sent[0][2]
    assert jobs.send_weekly_digests(
        current_time=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
        sender=lambda *args: sent.append(args),
    ) == 0


def test_weekly_digest_skips_opt_out_and_empty_users(client):
    current_time = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
    sent = []
    assert jobs.send_weekly_digests(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    enable_notifications(client, digest=True)
    assert jobs.send_weekly_digests(current_time=current_time, sender=lambda *args: sent.append(args)) == 0
    assert sent == []
