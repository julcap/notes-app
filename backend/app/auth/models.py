from sqlalchemy import Boolean, CheckConstraint, Integer, String, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base, now


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    pending_email: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(100))
    email_verified: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(String(100), default='')
    auth_provider: Mapped[str] = mapped_column(String(20), default='local')
    token_version: Mapped[int] = mapped_column(default=0)
    totp_secret: Mapped[str | None] = mapped_column(String(200))
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_lead_minutes: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (
        Index('unique_local_email', 'email', unique=True, postgresql_where=text("auth_provider = 'local'")),
        CheckConstraint(
            'reminder_lead_minutes BETWEEN 1 AND 1440',
            name='ck_users_reminder_lead_minutes',
        ),
    )


class Identity(Base):
    __tablename__ = 'social_identities'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint('provider', 'provider_user_id'),)


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    remember: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class EmailToken(Base):
    __tablename__ = 'email_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class RateBucket(Base):
    __tablename__ = 'auth_rate_limits'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    hits: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)


class BackupCode(Base):
    __tablename__ = 'backup_codes'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    code_hash: Mapped[str] = mapped_column(String(100))
    used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=now)
