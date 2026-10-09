"""Notification routes: inbox, unread count, mark read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import success
from app.db.session import get_db
from app.models import User
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List the caller's notifications (newest first)."""
    rows = notification_service.list_for_user(
        db, user_id=current_user.id, unread_only=unread_only, limit=limit
    )
    return success(data=jsonable_encoder(rows), message="Notifications")


@router.get("/unread-count")
def unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the caller's unread notification count."""
    result = notification_service.unread_count(db, user_id=current_user.id)
    payload = (
        result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    )
    return success(data=payload, message="Unread count")


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark one notification as read."""
    row = notification_service.mark_read(
        db, user_id=current_user.id, notification_id=notification_id
    )
    return success(data=jsonable_encoder(row), message="Marked as read")


@router.post("/read-all")
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mark all of the caller's notifications as read."""
    count = notification_service.mark_all_read(db, user_id=current_user.id)
    return success(data={"marked": count}, message="All notifications marked read")
