import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base, now


SEARCH_VECTOR_EXPRESSION = """
setweight(to_tsvector('pg_catalog.simple'::regconfig, coalesce(title, '')), 'A') ||
setweight(to_tsvector('pg_catalog.simple'::regconfig, coalesce(attendees, '')), 'B') ||
setweight(to_tsvector('pg_catalog.simple'::regconfig, coalesce(content, '')), 'C')
"""


class Note(Base):
    __tablename__ = 'notes'
    __table_args__ = (
        Index('ix_notes_search_vector', 'search_vector', postgresql_using='gin'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default='')
    attendees: Mapped[str] = mapped_column(String(1000), default='')
    meeting_date: Mapped[date] = mapped_column(Date)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
        nullable=True,
    )
    attachments: Mapped[list['Attachment']] = relationship(cascade='all, delete-orphan', lazy='selectin')
    action_items: Mapped[list['ActionItem']] = relationship(cascade='all, delete-orphan', lazy='selectin', order_by='ActionItem.created_at')
    shares: Mapped[list['MeetingShare']] = relationship(cascade='all, delete-orphan', lazy='selectin')


class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id: Mapped[str] = mapped_column(ForeignKey('notes.id', ondelete='CASCADE'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int]
    content_type: Mapped[str] = mapped_column(String(255), default='application/octet-stream')
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActionItem(Base):
    __tablename__ = 'action_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id: Mapped[str] = mapped_column(ForeignKey('notes.id', ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(String(500))
    owner_name: Mapped[str] = mapped_column(String(200), default='')
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MeetingShare(Base):
    __tablename__ = 'meeting_shares'
    __table_args__ = (
        UniqueConstraint('note_id', 'user_id', name='uq_meeting_shares_note_user'),
        CheckConstraint("permission IN ('view', 'edit')", name='ck_meeting_shares_permission'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[str] = mapped_column(ForeignKey('notes.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    permission: Mapped[str] = mapped_column(String(10))
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SharingContact(Base):
    __tablename__ = 'sharing_contacts'
    __table_args__ = (UniqueConstraint('owner_id', 'user_id', name='uq_sharing_contacts_owner_user'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
