import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from .database import SessionLocal
from .notes.models import Attachment, Note
from .storage import FILE_CLEANUP_LOCK_ID, LocalStorage, storage as configured_storage


PURGE_RETENTION = timedelta(days=30)


def storage_backend(value=None):
    return LocalStorage(value) if isinstance(value, Path) else value or configured_storage


def reconcile_quarantine(session, storage=None) -> None:
    backend = storage_backend(storage)
    quarantined = backend.quarantined()
    if not quarantined:
        return
    keys = [item.key for item in quarantined]
    rows = session.execute(
        select(Attachment.id, Attachment.object_key).where(
            (Attachment.object_key.in_(keys)) | (Attachment.id.in_(keys))
        )
    ).all()
    existing = {object_key or attachment_id for attachment_id, object_key in rows}
    for item in quarantined:
        if item.key in existing:
            if backend.exists(item.key):
                if backend.read(item.key) != backend.read(item.quarantine_key):
                    raise RuntimeError(f'Attachment differs between storage and quarantine: {item.key}')
                backend.discard([item])
            else:
                backend.restore([item])
        else:
            if backend.exists(item.key):
                if backend.read(item.key) != backend.read(item.quarantine_key):
                    raise RuntimeError(f'Orphan differs between storage and quarantine: {item.key}')
                backend.delete(item.key)
            backend.discard([item])


def try_reconcile_quarantine(*, session_factory=SessionLocal, storage=None) -> None:
    try:
        with session_factory() as session:
            session.execute(
                text('SELECT pg_advisory_xact_lock(:lock_id)'),
                {'lock_id': FILE_CLEANUP_LOCK_ID},
            )
            reconcile_quarantine(session, storage)
    except Exception:
        pass


def purge_deleted(
    *,
    session_factory=SessionLocal,
    storage=None,
    current_time: datetime | None = None,
) -> int:
    backend = storage_backend(storage)
    cutoff = (current_time or datetime.now(timezone.utc)) - PURGE_RETENTION
    purged = 0
    with session_factory() as session:
        locked = session.scalar(
            text('SELECT pg_try_advisory_xact_lock(:lock_id)'),
            {'lock_id': FILE_CLEANUP_LOCK_ID},
        )
        if not locked:
            return 0
        reconcile_quarantine(session, backend)
        notes = session.scalars(
            select(Note)
            .where(Note.deleted_at.is_not(None), Note.deleted_at < cutoff)
            .options(selectinload(Note.attachments))
            .order_by(Note.deleted_at, Note.id)
        ).all()
        object_keys = [
            attachment.object_key or attachment.id
            for note in notes
            for attachment in note.attachments
        ]
        quarantined = backend.quarantine(object_keys)
        try:
            for note in notes:
                session.delete(note)
                purged += 1
            session.commit()
        except Exception:
            session.rollback()
            try_reconcile_quarantine(session_factory=session_factory, storage=backend)
            raise
        backend.discard(quarantined)
        return purged


def send_reminders(**kwargs):
    from .notifications.service import send_reminders as execute
    return execute(**kwargs)


def send_weekly_digests(**kwargs):
    from .notifications.service import send_weekly_digests as execute
    return execute(**kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m app.jobs')
    parser.add_argument('command', choices=['purge-deleted', 'reminders', 'weekly-digest'])
    args = parser.parse_args(argv)
    if args.command == 'purge-deleted':
        print(f'Purged {purge_deleted()} deleted note(s).')
    elif args.command == 'reminders':
        print(f'Sent {send_reminders()} reminder(s).')
    elif args.command == 'weekly-digest':
        print(f'Sent {send_weekly_digests()} weekly digest(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
