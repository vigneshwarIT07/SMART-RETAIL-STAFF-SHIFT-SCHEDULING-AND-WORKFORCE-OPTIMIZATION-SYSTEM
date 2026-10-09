"""Store schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class StoreCreate(ORMModel):
    """Payload for creating a store (manager only)."""

    name: str = Field(min_length=2, max_length=120)
    code: str = Field(
        min_length=2, max_length=20, description="Short unique store code."
    )
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    timezone: str = Field(
        default="UTC", description="IANA timezone name, e.g. Europe/London."
    )


class StoreUpdate(ORMModel):
    """Partial update payload for a store."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class StoreResponse(ORMModel):
    """A store as returned by the API."""

    id: str
    name: str
    code: str
    address: str | None
    phone: str | None
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
