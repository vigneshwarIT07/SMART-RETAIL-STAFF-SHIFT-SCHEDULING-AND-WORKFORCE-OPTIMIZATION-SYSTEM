"""Authentication and current-session schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /api/auth/login``."""

    email: EmailStr = Field(description="Registered work email address.")
    password: str = Field(min_length=1, max_length=128, description="Account password.")


class TokenResponse(BaseModel):
    """The bearer token issued on successful authentication."""

    access_token: str = Field(description="Signed JWT bearer token.")
    token_type: str = Field(default="bearer", description="Always ``bearer``.")
    expires_in: int = Field(description="Token lifetime in seconds.")


class EmployeeSummary(ORMModel):
    """Minimal employee projection embedded in the session payload."""

    id: str
    employee_number: str
    full_name: str
    skill_level: str


class UserResponse(ORMModel):
    """The authenticated user as returned by the API."""

    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    store_id: str | None
    is_active: bool
    last_login_at: datetime | None
    employee: EmployeeSummary | None = None


class ChangePasswordRequest(BaseModel):
    """Self-service password change for the signed-in user."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=72)


class ManagerCreateRequest(BaseModel):
    """Manager-only provisioning of a new manager account.

    Managers cannot self-register; this endpoint is the documented secure
    bootstrap path and is restricted to an existing manager.
    """

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)
    store_id: str | None = Field(
        default=None,
        description="Store to manage. Defaults to the creating manager's store.",
    )


class ManagerCreateResponse(BaseModel):
    """Confirmation of manager provisioning without echoing the password."""

    user: UserResponse
    message: str = Field(description="Explicit note that no password was returned.")