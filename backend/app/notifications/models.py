from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base, now


class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        index=True,
    )
    note_id: Mapped[str | None] = mapped_column(
        ForeignKey('notes.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20))
    delivery_key: Mapped[str] = mapped_column(String(255), unique=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
