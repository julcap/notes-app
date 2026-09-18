from typing import Literal

from fastapi import HTTPException
from sqlalchemy import and_, select, text

from .models import ActionItem, MeetingShare, Note


Permission = Literal['owner', 'edit', 'view']
REQUIRED_LEVEL = {'view': 1, 'edit': 2, 'owner': 3}
ACCOUNT_LOCK_NAMESPACE = 1313821765


def lock_account(session, user_id: int):
    session.execute(
        text('SELECT pg_advisory_xact_lock(:namespace, :user_id)'),
        {'namespace': ACCOUNT_LOCK_NAMESPACE, 'user_id': user_id},
    )


def apply_permission(note: Note, user_id: int, shared_permission: str | None = None) -> Note:
    permission = 'owner' if note.owner_id == user_id else shared_permission
    note.effective_permission = permission
    note.is_owner = permission == 'owner'
    return note


def get_note(
    session,
    note_id: str,
    user,
    required: Literal['view', 'edit', 'owner'] = 'view',
    include_deleted: bool = False,
    lock: bool = False,
) -> Note:
    if lock:
        note = session.scalar(
            select(Note).where(Note.id == note_id).with_for_update()
        )
        if note is None:
            raise HTTPException(404, 'Note not found')
        shared_permission = None
        if note.owner_id != user.id:
            shared_permission = session.scalar(select(MeetingShare.permission).where(
                MeetingShare.note_id == note.id,
                MeetingShare.user_id == user.id,
            ))
    else:
        row = session.execute(
            select(Note, MeetingShare.permission).outerjoin(
                MeetingShare,
                and_(MeetingShare.note_id == Note.id, MeetingShare.user_id == user.id),
            ).where(Note.id == note_id)
        ).one_or_none()
        if row is None:
            raise HTTPException(404, 'Note not found')
        note, shared_permission = row
    permission = 'owner' if note.owner_id == user.id else shared_permission
    if note.deleted_at is not None and not (include_deleted and permission == 'owner'):
        raise HTTPException(404, 'Note not found')
    if permission is None:
        raise HTTPException(404, 'Note not found')
    if REQUIRED_LEVEL[permission] < REQUIRED_LEVEL[required]:
        if required == 'owner':
            raise HTTPException(404, 'Note not found')
        raise HTTPException(403, 'Insufficient note permission')
    return apply_permission(note, user.id, shared_permission)


def get_action_item(session, item_id: str, user, required: Literal['view', 'edit'] = 'edit') -> ActionItem:
    note_id = session.scalar(select(ActionItem.note_id).where(ActionItem.id == item_id))
    if note_id is None:
        raise HTTPException(404, 'Action item not found')
    try:
        get_note(session, note_id, user, required=required, lock=True)
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(404, 'Action item not found') from error
        raise
    item = session.scalar(select(ActionItem).where(
        ActionItem.id == item_id,
        ActionItem.note_id == note_id,
    ))
    if item is None:
        raise HTTPException(404, 'Action item not found')
    return item
