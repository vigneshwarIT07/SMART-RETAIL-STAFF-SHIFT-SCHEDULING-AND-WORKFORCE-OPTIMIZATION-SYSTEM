"""Health routes: liveness plus honest dependency reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import success
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def read_health(db: Session = Depends(get_db)) -> dict:
    """Report API liveness, database reachability and email state.

    ``email_enabled`` is reported honestly: when no SMTP host is configured
    the API says so instead of pretending delivery works.
    """
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "up"
    except Exception:  # pragma: no cover - exercised in deployment, not unit tests
        database = "down"
    return success(
        data={
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.environment,
            "database": database,
            "email_enabled": settings.email_enabled,
            "email_note": (
                "Email delivery is configured."
                if settings.email_enabled
                else "EMAIL_HOST is not configured — notifications are stored in-app only."
            ),
        },
        message="Service health",
    )
