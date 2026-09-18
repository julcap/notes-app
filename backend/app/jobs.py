import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from .database import SessionLocal
from .notes.models import Attachment, Note
from .storage import FILE_CLEANUP_LOCK_ID, STORAGE, discard_quarantined, quarantine_files


PURGE_RETENTION = timedelta(days=30)


def reconcile_quarantine(session, storage: Path) -> None:
    trash = storage / '.trash'
    if not trash.is_dir():
        return
    paths = [path for path in trash.iterdir() if path.is_file()]
    if not paths:
        return
    existing = set(
        session.scalars(
            select(Attachment.id).where(Attachment.id.in_([path.name for path in paths]))
        ).all()
    )
    for path in paths:
        if path.name in existing:
            target = storage / path.name
            if target.exists():
                raise RuntimeError(f'Attachment exists in storage and quarantine: {path.name}')
            path.replace(target)
        else:
            path.unlink()


def try_reconcile_quarantine(*, session_factory=SessionLocal, storage: Path = STORAGE) -> None:
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
    storage: Path = STORAGE,
    current_time: datetime | None = None,
) -> int:
    cutoff = (current_time or datetime.now(timezone.utc)) - PURGE_RETENTION
    purged = 0
    with session_factory() as session:
        locked = session.scalar(
            text('SELECT pg_try_advisory_xact_lock(:lock_id)'),
            {'lock_id': FILE_CLEANUP_LOCK_ID},
        )
        if not locked:
            return 0
        reconcile_quarantine(session, storage)
        notes = session.scalars(
            select(Note)
            .where(Note.deleted_at.is_not(None), Note.deleted_at < cutoff)
            .options(selectinload(Note.attachments))
            .order_by(Note.deleted_at, Note.id)
        ).all()
        attachment_ids = [attachment.id for note in notes for attachment in note.attachments]
        quarantined = quarantine_files(attachment_ids, storage)
        try:
            for note in notes:
                session.delete(note)
                purged += 1
            session.commit()
        except Exception:
            session.rollback()
            try_reconcile_quarantine(session_factory=session_factory, storage=storage)
            raise
        discard_quarantined(quarantined)
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
