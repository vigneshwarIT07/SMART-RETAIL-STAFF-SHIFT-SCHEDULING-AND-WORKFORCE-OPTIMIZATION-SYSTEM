"""In-app notifications and the audit log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import AuditAction, NotificationType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Notification(Base):
    """A message shown to one user in the notifications screen.

    Notifications are the durable record; email is an optional transport.
    A notification row is written even when email delivery is disabled, and
    ``email_status`` records honestly whether an attempt was made.

    ``dedupe_key`` prevents the same message being recorded twice when a
    request is retried or an operation runs more than one code path.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_dedupe", "dedupe_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user: Mapped[User] = relationship(lazy="joined")

    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(
            NotificationType, name="notification_type", native_enum=False, length=30
        ),
        nullable=False,
        default=NotificationType.GENERAL,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Optional link target, e.g. /shifts or /notifications.
    link_url: Mapped[str | None] = mapped_column(String(255))

    # null  -> not attempted (delivery disabled)
    # "sent" -> handed to the mail server
    # "failed" -> attempted and rejected
    email_status: Mapped[str | None] = mapped_column(String(20))
    email_error: Mapped[str | None] = mapped_column(String(255))

    dedupe_key: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Notification user={self.user_id} type={self.notification_type.value}>"


class AuditLog(Base):
    """Append-only record of a state change, attributed to a user.

    Rows are never updated or deleted. ``entity_type`` and ``entity_id``
    identify what changed, and ``details`` holds a JSON snapshot of the
    before and after values for the fields that matter.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_user_created", "user_id", "created_at"),
        Index("ix_audit_store_created", "store_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user: Mapped[User | None] = relationship(lazy="joined")

    store_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", native_enum=False, length=20),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog {self.action.value} {self.entity_type}:{self.entity_id}>"
