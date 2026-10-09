"""Employee directory and provisioning schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import EmployeeStatus, SkillLevel
from app.schemas.common import ORMModel


class EmployeeCreate(BaseModel):
    """Manager-only payload that provisions a login and employee record together."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)
    employee_number: str | None = Field(
        default=None,
        max_length=20,
        description="Optional. Generated as EMP-XXXX when omitted.",
    )
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    hire_date: date | None = None
    skill_level: SkillLevel = SkillLevel.JUNIOR
    skills: list[str] = Field(default_factory=list)
    contract_weekly_hours: int = Field(default=40, ge=0, le=80)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    is_keyholder: bool = False

    @field_validator("skills")
    @classmethod
    def _normalise_skills(cls, value: list[str]) -> list[str]:
        """Trim, de-duplicate and sort skills so comparisons stay deterministic."""

        cleaned = {item.strip().lower() for item in value if item and item.strip()}
        return sorted(cleaned)


class EmployeeUpdate(BaseModel):
    """Partial employee update. Passwords are not editable here."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    hire_date: date | None = None
    skill_level: SkillLevel | None = None
    skills: list[str] | None = None
    contract_weekly_hours: int | None = Field(default=None, ge=0, le=80)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    is_keyholder: bool | None = None
    status: EmployeeStatus | None = None

    @field_validator("skills")
    @classmethod
    def _normalise_skills(cls, value: list[str] | None) -> list[str] | None:
        """Apply the same normalisation as :class:`EmployeeCreate`."""

        if value is None:
            return None
        cleaned = {item.strip().lower() for item in value if item and item.strip()}
        return sorted(cleaned)


class EmployeeResponse(ORMModel):
    """An employee profile as returned by the API.

    ``email`` and ``full_name`` originate from the linked ``users`` row and are
    populated by the service layer, never by the browser.
    """

    id: str
    employee_number: str
    store_id: str
    email: EmailStr
    full_name: str
    phone: str | None
    address: str | None
    date_of_birth: date | None
    hire_date: date | None
    skill_level: SkillLevel
    skills: list[str] = Field(default_factory=list)
    contract_weekly_hours: int
    hourly_rate: Decimal | None
    is_keyholder: bool
    status: EmployeeStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime