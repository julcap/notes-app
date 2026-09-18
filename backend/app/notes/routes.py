import uuid
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import and_, func, literal_column, or_, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, selectinload

from ..auth import User, current_user, verified_user
from ..database import db, now
from ..jobs import try_reconcile_quarantine
from ..storage import FILE_CLEANUP_LOCK_ID, MAX_FILE_SIZE, STORAGE, discard_quarantined, quarantine_files
from .attachments import BINARY_CONTENT_TYPE, stored_content_type, verified_inline_content_type
from .export import export_filename, markdown_export, pdf_export
from .models import ActionItem, Attachment, MeetingShare, Note
from .permissions import apply_permission, get_action_item, get_note, lock_account
from .schemas import ActionItemInput, ActionItemOut, ActionItemPatch, AttachmentOut, NoteInput, NoteOut, NotePage

router = APIRouter(prefix='/api/notes')
action_items_router = APIRouter(prefix='/api/action-items')


@router.get('', response_model=NotePage)
def notes(
    q: str = Query('', max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    share_join = and_(MeetingShare.note_id == Note.id, MeetingShare.user_id == user.id)
    filters = [or_(Note.owner_id == user.id, MeetingShare.user_id == user.id), Note.deleted_at.is_(None)]
    order = (Note.meeting_date.desc(), Note.updated_at.desc(), Note.id.asc())
    if q.strip():
        search_vector = literal_column('notes.search_vector', postgresql.TSVECTOR())
        search_query = func.plainto_tsquery(literal_column("'pg_catalog.simple'::regconfig"), q.strip())
        filters.append(search_vector.op('@@')(search_query))
        order = (func.ts_rank(search_vector, search_query).desc(), *order)
    total = session.scalar(select(func.count()).select_from(Note).outerjoin(MeetingShare, share_join).where(*filters)) or 0
    query = (
        select(Note, MeetingShare.permission)
        .outerjoin(MeetingShare, share_join)
        .where(*filters)
        .options(selectinload(Note.attachments))
        .order_by(*order)
        .offset(skip)
        .limit(limit)
    )
    items = [apply_permission(note, user.id, permission) for note, permission in session.execute(query).all()]
    return {'items': items, 'total': total}


@router.post('', response_model=NoteOut, status_code=201)
def create_note(payload: NoteInput, session: Session = Depends(db), user: User = Depends(verified_user)):
    lock_account(session, user.id)
    if session.scalar(select(User.id).where(User.id == user.id)) is None:
        raise HTTPException(401, 'Invalid or expired token')
    note = Note(owner_id=user.id, **payload.model_dump())
    session.add(note)
    session.commit()
    session.refresh(note)
    return apply_permission(note, user.id)


@router.get('/{note_id}', response_model=NoteOut)
def read_note(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    return get_note(session, note_id, user)


@router.get('/{note_id}/export')
def export_note(
    note_id: str,
    format: Literal['md', 'pdf'],
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    note = get_note(session, note_id, user)
    if format == 'pdf':
        filename = export_filename(note.title, 'pdf')
        return Response(
            pdf_export(note),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff',
            },
        )
    filename = export_filename(note.title, 'md')
    return Response(
        markdown_export(note).encode(),
        media_type='text/markdown',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@router.put('/{note_id}', response_model=NoteOut)
def update_note(note_id: str, payload: NoteInput, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user, required='edit', lock=True)
    if not note.is_owner and payload.scheduled_at != note.scheduled_at:
        raise HTTPException(403, 'Only the owner can change scheduling')
    for key, value in payload.model_dump().items():
        if key == 'scheduled_at' and not note.is_owner:
            continue
        setattr(note, key, value)
    note.updated_at = now()
    session.commit()
    session.refresh(note)
    return note


@router.delete('/{note_id}', status_code=204)
def delete_note(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user, required='owner', lock=True)
    note.deleted_at = now()
    session.commit()


@router.post('/{note_id}/undelete', response_model=NoteOut)
def undelete_note(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user, required='owner', include_deleted=True, lock=True)
    if note.deleted_at is None:
        raise HTTPException(404, 'Note not found')
    if now() - note.deleted_at > timedelta(seconds=15):
        raise HTTPException(409, 'Undo window has expired')
    note.deleted_at = None
    session.commit()
    session.refresh(note)
    return note


@router.post('/{note_id}/action-items', response_model=ActionItemOut, status_code=201)
def create_action_item(note_id: str, payload: ActionItemInput, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user, required='edit', lock=True)
    item = ActionItem(note_id=note.id, **payload.model_dump())
    session.add(item)
    note.updated_at = now()
    session.commit()
    session.refresh(item)
    return item


@router.post('/{note_id}/attachments', response_model=AttachmentOut, status_code=201)
def upload(note_id: str, file: UploadFile, session: Session = Depends(db), user: User = Depends(current_user)):
    session.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'), {'lock_id': FILE_CLEANUP_LOCK_ID})
    note = get_note(session, note_id, user, required='edit', lock=True)
    attachment_id = str(uuid.uuid4())
    path = STORAGE / attachment_id
    size = 0
    try:
        with path.open('wb') as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(413, 'Files must be 20 MB or smaller')
                target.write(chunk)
        filename = Path((file.filename or 'attachment').replace('\\', '/')).name[:255] or 'attachment'
        attachment = Attachment(
            id=attachment_id,
            note_id=note.id,
            filename=filename,
            size=size,
            content_type=stored_content_type(filename, file.content_type),
        )
        session.add(attachment)
        note.updated_at = now()
        session.commit()
        session.refresh(attachment)
        return attachment
    except Exception:
        session.rollback()
        quarantine_files([attachment_id])
        try_reconcile_quarantine()
        raise
    finally:
        file.file.close()


@router.get('/{note_id}/attachments/{attachment_id}')
def download(
    note_id: str,
    attachment_id: str,
    inline: bool = False,
    session: Session = Depends(db),
    user: User = Depends(current_user),
):
    get_note(session, note_id, user)
    item = session.get(Attachment, attachment_id)
    path = STORAGE / item.id if item is not None else None
    if item is None or item.note_id != note_id or path is None or not path.is_file():
        raise HTTPException(404, 'Attachment not found')
    verified_type = verified_inline_content_type(path) if inline else None
    is_safe_inline = verified_type is not None and verified_type == item.content_type
    return FileResponse(
        path,
        filename=item.filename,
        media_type=verified_type if is_safe_inline else BINARY_CONTENT_TYPE,
        content_disposition_type='inline' if is_safe_inline else 'attachment',
        headers={
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store',
        },
    )


@router.delete('/{note_id}/attachments/{attachment_id}', status_code=204)
def delete_attachment(note_id: str, attachment_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    session.execute(text('SELECT pg_advisory_xact_lock(:lock_id)'), {'lock_id': FILE_CLEANUP_LOCK_ID})
    get_note(session, note_id, user, required='edit', lock=True)
    item = session.get(Attachment, attachment_id)
    if item is None or item.note_id != note_id:
        raise HTTPException(404, 'Attachment not found')
    quarantined = quarantine_files([item.id])
    try:
        session.delete(item)
        session.commit()
    except Exception:
        session.rollback()
        try_reconcile_quarantine()
        raise
    discard_quarantined(quarantined)


@action_items_router.patch('/{item_id}', response_model=ActionItemOut)
def update_action_item(item_id: str, payload: ActionItemPatch, session: Session = Depends(db), user: User = Depends(current_user)):
    item = get_action_item(session, item_id, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    session.refresh(item)
    return item


@action_items_router.delete('/{item_id}', status_code=204)
def delete_action_item(item_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    item = get_action_item(session, item_id, user)
    session.delete(item)
    session.commit()
