"""Append-only audit logging."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import AuditAction
from app.models.notification import AuditLog


def log_action(
    db: Session,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: str | None = None,
    user_id: str | None = None,
    store_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Append one audit row and flush it.

    Audit rows are never updated or deleted by the application; only the
    database administrator can prune them. The caller owns the commit.
    """

    entry = AuditLog(
        user_id=user_id,
        store_id=store_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
    return entry
