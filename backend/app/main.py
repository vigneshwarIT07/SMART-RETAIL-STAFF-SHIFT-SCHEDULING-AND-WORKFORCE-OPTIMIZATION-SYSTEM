"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload --port 8000

Interactive API docs are served at ``/docs`` (Swagger UI).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    attendance,
    auth,
    availability,
    employees,
    health,
    leave,
    notifications,
    reports,
    scheduling,
    shifts,
    stores,
    swaps,
)
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

settings = get_settings()
# Refuse to boot in production with placeholder secrets or local URLs.
settings.validate_production_secrets()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Retail Staff Shift Scheduling Platform — roster management, "
        "attendance, leave and shift swaps for a single retail store."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

register_exception_handlers(app)

_PREFIX = settings.api_prefix
for _router in (
    health.router,
    auth.router,
    stores.router,
    employees.router,
    shifts.router,
    scheduling.router,
    availability.router,
    attendance.router,
    leave.router,
    swaps.router,
    notifications.router,
    reports.router,
):
    app.include_router(_router, prefix=_PREFIX)


@app.get("/", include_in_schema=False)
def read_root() -> dict:
    """Plain-text-safe landing payload pointing at docs and health."""
    return {
        "success": True,
        "data": {"docs": "/docs", "health": f"{_PREFIX}/health"},
        "message": f"{settings.app_name} API",
    }
