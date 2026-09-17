import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, String, Text, Date, DateTime, ForeignKey, select, or_, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session, selectinload

from .database import Base, engine, SessionLocal, now, db
from .auth import router, User, current_user, verified_user, SECRET, SECURE
from starlette.middleware.sessions import SessionMiddleware
STORAGE = Path(os.getenv('UPLOAD_DIR', '/data/uploads'))
MAX_FILE_SIZE = 20 * 1024 * 1024

class Note(Base):
    __tablename__ = 'notes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default='')
    attendees: Mapped[str] = mapped_column(String(1000), default='')
    meeting_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    attachments: Mapped[list['Attachment']] = relationship(cascade='all, delete-orphan', lazy='selectin')

class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id: Mapped[str] = mapped_column(ForeignKey('notes.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default='', max_length=100000)
    attendees: str = Field(default='', max_length=1000)
    meeting_date: date

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Title cannot be blank')
        return value.strip()

class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    size: int

class NoteOut(NoteInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentOut]

@asynccontextmanager
async def lifespan(app):
    STORAGE.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title='Minutes API', lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SECRET, https_only=SECURE, same_site='lax', max_age=600)
app.include_router(router)

@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def get_note(session, note_id, user):
    note = session.get(Note, note_id)
    if note is None or note.owner_id != user.id:
        raise HTTPException(404, 'Note not found')
    return note

@app.get('/api/health')
def health(session: Session = Depends(db)):
    session.execute(text('SELECT 1'))
    return {'status': 'ok'}

@app.get('/api/notes', response_model=list[NoteOut])
def notes(q: str = Query('', max_length=200), session: Session = Depends(db), user: User = Depends(current_user)):
    query = select(Note).where(Note.owner_id == user.id).options(selectinload(Note.attachments))
    if q.strip():
        term = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(or_(Note.title.ilike(term, escape='\\'), Note.content.ilike(term, escape='\\'), Note.attendees.ilike(term, escape='\\')))
    return session.scalars(query.order_by(Note.meeting_date.desc(), Note.updated_at.desc())).all()

@app.post('/api/notes', response_model=NoteOut, status_code=201)
def create_note(payload: NoteInput, session: Session = Depends(db), user: User = Depends(verified_user)):
    note = Note(owner_id=user.id, **payload.model_dump())
    session.add(note)
    session.commit()
    session.refresh(note)
    return note

@app.get('/api/notes/{note_id}', response_model=NoteOut)
def read_note(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    return get_note(session, note_id, user)

@app.put('/api/notes/{note_id}', response_model=NoteOut)
def update_note(note_id: str, payload: NoteInput, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user)
    for key, value in payload.model_dump().items():
        setattr(note, key, value)
    note.updated_at = now()
    session.commit()
    session.refresh(note)
    return note

@app.delete('/api/notes/{note_id}', status_code=204)
def delete_note(note_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user)
    ids = [a.id for a in note.attachments]
    session.delete(note)
    session.commit()
    for item in ids:
        (STORAGE / item).unlink(missing_ok=True)

@app.post('/api/notes/{note_id}/attachments', response_model=AttachmentOut, status_code=201)
def upload(note_id: str, file: UploadFile, session: Session = Depends(db), user: User = Depends(current_user)):
    note = get_note(session, note_id, user)
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
        attachment = Attachment(id=attachment_id, note_id=note.id, filename=filename, size=size)
        session.add(attachment)
        note.updated_at = now()
        session.commit()
        session.refresh(attachment)
        return attachment
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

@app.get('/api/notes/{note_id}/attachments/{attachment_id}')
def download(note_id: str, attachment_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    get_note(session, note_id, user)
    item = session.get(Attachment, attachment_id)
    if item is None or item.note_id != note_id or not (STORAGE / item.id).is_file():
        raise HTTPException(404, 'Attachment not found')
    return FileResponse(STORAGE / item.id, filename=item.filename, media_type='application/octet-stream', headers={'X-Content-Type-Options':'nosniff'})

@app.delete('/api/notes/{note_id}/attachments/{attachment_id}', status_code=204)
def delete_attachment(note_id: str, attachment_id: str, session: Session = Depends(db), user: User = Depends(current_user)):
    get_note(session, note_id, user)
    item = session.get(Attachment, attachment_id)
    if item is None or item.note_id != note_id:
        raise HTTPException(404, 'Attachment not found')
    session.delete(item)
    session.commit()
    (STORAGE / item.id).unlink(missing_ok=True)
