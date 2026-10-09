"""In-app notifications with idempotent creation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import NotificationType, UserRole
from app.models.notification import Notification
from app.models.user import User
from app.schemas.operations import UnreadCount


def _utcnow() -> datetime:
    """Current timezone-aware UTC time."""

    return datetime.now(timezone.utc)


def create_notification(
    db: Session,
    *,
    user_id: str,
    notification_type: NotificationType | str,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    dedupe_key: str | None = None,
) -> Notification:
    """Create a notification, returning the existing one on retry.

    When ``dedupe_key`` is supplied and a row already carries it, the
    existing row is returned unchanged so retried requests never create (or
    email) duplicates.
    """

    if dedupe_key:
        existing = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    notification = Notification(
        user_id=user_id,
        notification_type=(
            notification_type.value
            if isinstance(notification_type, NotificationType)
            else notification_type
        ),
        title=title,
        body=body,
        link_url=link_url,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    db.flush()
    return notification


def notify_store_managers(
    db: Session,
    *,
    store_id: str,
    notification_type: NotificationType | str,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    dedupe_key: str | None = None,
) -> list[Notification]:
    """Notify every active manager of one store (used for leave/swap alerts)."""

    manager_ids = db.scalars(
        select(User.id).where(
            User.store_id == store_id,
            User.role == UserRole.MANAGER,
            User.is_active.is_(True),
        )
    ).all()
    created: list[Notification] = []
    for index, manager_id in enumerate(manager_ids):
        key = f"{dedupe_key}:{manager_id}" if dedupe_key else None
        _ = index
        created.append(
            create_notification(
                db,
                user_id=manager_id,
                notification_type=notification_type,
                title=title,
                body=body,
                link_url=link_url,
                dedupe_key=key,
            )
        )
    return created


def list_for_user(
    db: Session, *, user_id: str, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    """Newest-first notifications for one user."""

    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list(db.scalars(stmt).all())


def unread_count(db: Session, *, user_id: str) -> UnreadCount:
    """Number of unread notifications for one user."""

    total = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )
    return UnreadCount(unread=int(total or 0))


def mark_read(db: Session, *, user_id: str, notification_id: str) -> Notification | None:
    """Mark one notification read; returns None when it is not ours."""

    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if notification is None:
        return None
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = _utcnow()
        db.flush()
    return notification


def mark_all_read(db: Session, *, user_id: str) -> int:
    """Mark every notification of one user read; returns the count changed."""

    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.flush()
    return len(rows)
