from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from ..auth.email import send_email
from ..auth.models import User
from ..database import SessionLocal
from ..notes.models import ActionItem, Note
from .models import NotificationDelivery


REMINDER_LOCK_ID = 718_320_101
DIGEST_LOCK_ID = 718_320_102
DELIVERY_ERROR = 'Notification delivery failed; retry is safe.'


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def reminder_key(user_id: int, note: Note) -> str:
    scheduled = utc(note.scheduled_at).isoformat(timespec='microseconds')
    return f'reminder:{user_id}:{note.id}:{scheduled}'


def reminder_body(note: Note) -> str:
    scheduled = utc(note.scheduled_at).strftime('%Y-%m-%d %H:%M UTC')
    return (
        f'Your meeting "{note.title}" starts at {scheduled}.\n\n'
        'Open Minutes to review the meeting note.'
    )


def reminder_subject(note: Note) -> str:
    return f"Meeting starting soon: {' '.join(note.title.splitlines())}"


def send_reminders(
    *,
    session_factory=SessionLocal,
    current_time: datetime | None = None,
    sender=send_email,
) -> int:
    current_time = utc(current_time or datetime.now(timezone.utc))
    sent = 0
    first_error = None
    with session_factory() as lock_session:
        if not lock_session.scalar(
            text('SELECT pg_try_advisory_lock(:lock_id)'),
            {'lock_id': REMINDER_LOCK_ID},
        ):
            return 0
        try:
            candidates = lock_session.execute(
                select(User.id, Note.id)
                .join(Note, Note.owner_id == User.id)
                .where(
                    User.email_verified.is_(True),
                    User.reminders_enabled.is_(True),
                    Note.deleted_at.is_(None),
                    Note.scheduled_at.is_not(None),
                    Note.scheduled_at > current_time,
                    Note.scheduled_at <= current_time + timedelta(minutes=1440),
                )
                .order_by(Note.scheduled_at, Note.id)
            ).all()
            for user_id, note_id in candidates:
                try:
                    with session_factory.begin() as session:
                        row = session.execute(
                            select(User, Note)
                            .join(Note, Note.owner_id == User.id)
                            .where(
                                User.id == user_id,
                                Note.id == note_id,
                                User.email_verified.is_(True),
                                User.reminders_enabled.is_(True),
                                Note.deleted_at.is_(None),
                                Note.scheduled_at.is_not(None),
                                Note.scheduled_at > current_time,
                            )
                        ).one_or_none()
                        if row is None:
                            continue
                        user, note = row
                        if current_time < note.scheduled_at - timedelta(minutes=user.reminder_lead_minutes):
                            continue
                        key = reminder_key(user.id, note)
                        if session.scalar(
                            select(NotificationDelivery.id).where(
                                NotificationDelivery.delivery_key == key
                            )
                        ):
                            continue
                        sender(user.email, reminder_subject(note), reminder_body(note))
                        session.add(NotificationDelivery(
                            user_id=user.id,
                            note_id=note.id,
                            kind='reminder',
                            delivery_key=key,
                            delivered_at=current_time,
                        ))
                        sent += 1
                except Exception:
                    first_error = first_error or RuntimeError(DELIVERY_ERROR)
        finally:
            lock_session.scalar(
                text('SELECT pg_advisory_unlock(:lock_id)'),
                {'lock_id': REMINDER_LOCK_ID},
            )
    if first_error is not None:
        raise first_error
    return sent


def digest_body(meetings: list[Note], action_items: list[ActionItem], start_date, end_date) -> str:
    lines = [f'Your Minutes weekly digest for {start_date} through {end_date}:', '']
    if meetings:
        lines.extend(['Meetings:', *[f'- {note.meeting_date}: {note.title}' for note in meetings], ''])
    if action_items:
        lines.extend(['Open action items:', *[f'- {item.text}' for item in action_items], ''])
    lines.append('Open Minutes to review the full details.')
    return '\n'.join(lines)


def send_weekly_digests(
    *,
    session_factory=SessionLocal,
    current_time: datetime | None = None,
    sender=send_email,
) -> int:
    current_time = utc(current_time or datetime.now(timezone.utc))
    week_end = current_time.date() - timedelta(days=current_time.weekday())
    week_start = week_end - timedelta(days=7)
    sent = 0
    first_error = None
    with session_factory() as lock_session:
        if not lock_session.scalar(
            text('SELECT pg_try_advisory_lock(:lock_id)'),
            {'lock_id': DIGEST_LOCK_ID},
        ):
            return 0
        try:
            user_ids = lock_session.scalars(
                select(User.id)
                .where(User.email_verified.is_(True), User.digest_enabled.is_(True))
                .order_by(User.id)
            ).all()
            for user_id in user_ids:
                try:
                    with session_factory.begin() as session:
                        user = session.scalar(
                            select(User).where(
                                User.id == user_id,
                                User.email_verified.is_(True),
                                User.digest_enabled.is_(True),
                            )
                        )
                        if user is None:
                            continue
                        key = f'digest:{user.id}:{week_start.isoformat()}'
                        if session.scalar(
                            select(NotificationDelivery.id).where(
                                NotificationDelivery.delivery_key == key
                            )
                        ):
                            continue
                        meetings = session.scalars(
                            select(Note)
                            .where(
                                Note.owner_id == user.id,
                                Note.deleted_at.is_(None),
                                Note.meeting_date >= week_start,
                                Note.meeting_date < week_end,
                            )
                            .order_by(Note.meeting_date, Note.id)
                        ).all()
                        action_items = session.scalars(
                            select(ActionItem)
                            .join(Note, Note.id == ActionItem.note_id)
                            .where(
                                Note.owner_id == user.id,
                                Note.deleted_at.is_(None),
                                ActionItem.done.is_(False),
                            )
                            .order_by(ActionItem.created_at, ActionItem.id)
                        ).all()
                        if not meetings and not action_items:
                            continue
                        sender(
                            user.email,
                            f'Your Minutes weekly digest — {week_start}',
                            digest_body(meetings, action_items, week_start, week_end - timedelta(days=1)),
                        )
                        session.add(NotificationDelivery(
                            user_id=user.id,
                            kind='weekly-digest',
                            delivery_key=key,
                            delivered_at=current_time,
                        ))
                        sent += 1
                except Exception:
                    first_error = first_error or RuntimeError(DELIVERY_ERROR)
        finally:
            lock_session.scalar(
                text('SELECT pg_advisory_unlock(:lock_id)'),
                {'lock_id': DIGEST_LOCK_ID},
            )
    if first_error is not None:
        raise first_error
    return sent
