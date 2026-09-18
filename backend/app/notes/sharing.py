from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..auth import User, current_user
from ..database import db, now
from .models import MeetingShare, SharingContact
from .permissions import get_note
from .schemas import PreviousSharesInput, ShareByEmail, ShareOut, SharePermission, SharingContactOut


notes_sharing_router = APIRouter(prefix='/api/notes')
sharing_router = APIRouter(prefix='/api/sharing')


def share_result(share: MeetingShare, user: User):
    return {
        'user_id': user.id,
        'email': user.email,
        'display_name': user.display_name,
        'permission': share.permission,
        'shared_at': share.shared_at,
    }


def list_note_shares(session, note_id):
    rows = session.execute(
        select(MeetingShare, User)
        .join(User, User.id == MeetingShare.user_id)
        .where(MeetingShare.note_id == note_id)
        .order_by(User.email, User.id)
    ).all()
    return [share_result(share, recipient) for share, recipient in rows]


def verified_target(session, email, owner_id):
    targets = session.scalars(
        select(User).where(
            User.email == email,
            User.email_verified.is_(True),
        ).order_by(User.id)
    ).all()
    if len(targets) != 1 or targets[0].id == owner_id:
        raise HTTPException(404, 'Sharing recipient not found')
    return targets[0]


def upsert_share(session, note_id, owner_id, recipient_id, permission):
    session.execute(
        insert(MeetingShare).values(
            note_id=note_id,
            user_id=recipient_id,
            permission=permission,
            shared_at=now(),
        ).on_conflict_do_update(
            constraint='uq_meeting_shares_note_user',
            set_={'permission': permission},
        )
    )
    session.execute(
        insert(SharingContact).values(
            owner_id=owner_id,
            user_id=recipient_id,
        ).on_conflict_do_nothing(constraint='uq_sharing_contacts_owner_user')
    )


@notes_sharing_router.get('/{note_id}/shares', response_model=list[ShareOut])
def shares(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    get_note(session, note_id, user, required='owner')
    return list_note_shares(session, note_id)


@notes_sharing_router.post('/{note_id}/shares', response_model=ShareOut, status_code=201)
def add_share(
    note_id: str,
    payload: ShareByEmail,
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    note = get_note(session, note_id, user, required='owner', lock=True)
    recipient = verified_target(session, str(payload.email), user.id)
    upsert_share(session, note.id, user.id, recipient.id, payload.permission)
    session.commit()
    share = session.scalar(select(MeetingShare).where(
        MeetingShare.note_id == note.id,
        MeetingShare.user_id == recipient.id,
    ))
    return share_result(share, recipient)


@notes_sharing_router.patch('/{note_id}/shares/{user_id}', response_model=ShareOut)
def update_share(
    note_id: str,
    user_id: int,
    payload: SharePermission,
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    get_note(session, note_id, user, required='owner', lock=True)
    row = session.scalar(select(MeetingShare).where(
        MeetingShare.note_id == note_id,
        MeetingShare.user_id == user_id,
    ))
    recipient = session.get(User, user_id)
    if row is None or recipient is None:
        raise HTTPException(404, 'Share not found')
    row.permission = payload.permission
    session.commit()
    session.refresh(row)
    return share_result(row, recipient)


@notes_sharing_router.delete('/{note_id}/shares/{user_id}', status_code=204)
def remove_share(
    note_id: str,
    user_id: int,
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    get_note(session, note_id, user, required='owner', lock=True)
    row = session.scalar(select(MeetingShare).where(
        MeetingShare.note_id == note_id,
        MeetingShare.user_id == user_id,
    ))
    if row is None:
        raise HTTPException(404, 'Share not found')
    session.delete(row)
    session.commit()


@sharing_router.get('/contacts', response_model=list[SharingContactOut])
def sharing_contacts(session: Session = Depends(db), user: User = Depends(current_user)):
    contacts = session.scalars(
        select(User)
        .join(SharingContact, SharingContact.user_id == User.id)
        .where(
            SharingContact.owner_id == user.id,
            User.email_verified.is_(True),
        )
        .order_by(User.email, User.id)
    ).all()
    return [
        {'user_id': contact.id, 'email': contact.email, 'display_name': contact.display_name}
        for contact in contacts
    ]


@notes_sharing_router.post('/{note_id}/shares/previous', response_model=list[ShareOut])
def share_with_previous(
    note_id: str,
    payload: PreviousSharesInput,
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    note = get_note(session, note_id, user, required='owner', lock=True)
    contacts = session.scalars(
        select(User)
        .join(SharingContact, SharingContact.user_id == User.id)
        .where(
            SharingContact.owner_id == user.id,
            SharingContact.user_id.in_(payload.user_ids),
            User.email_verified.is_(True),
            User.id != user.id,
        )
        .order_by(User.email, User.id)
    ).all()
    if len(contacts) != len(payload.user_ids):
        raise HTTPException(409, 'Sharing recipients changed; review them again')
    for contact in contacts:
        upsert_share(session, note.id, user.id, contact.id, payload.permission)
    session.commit()
    return list_note_shares(session, note.id)
