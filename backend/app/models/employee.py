"""Employee records.

An employee row shares its primary key with the linked ``users`` row so that
the server can derive the acting employee from the authenticated user without
trusting anything sent by the browser.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import EmployeeStatus, SkillLevel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import Store, User


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Employee(Base):
    """A staff member who can be assigned to shifts."""

    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_store_status", "store_id", "status"),
        Index("ix_employees_store_skill", "store_id", "skill_level"),
    )

    # Shared primary key with the linked user account.
    id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    employee_number: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )
    store_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store: Mapped[Store] = relationship(back_populates="employees")

    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    hire_date: Mapped[date | None] = mapped_column(Date)

    skill_level: Mapped[SkillLevel] = mapped_column(
        SAEnum(SkillLevel, name="skill_level", native_enum=False, length=20),
        nullable=False,
        default=SkillLevel.JUNIOR,
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(EmployeeStatus, name="employee_status", native_enum=False, length=20),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
    )

    # Role tags this employee can cover, e.g. ["till", "keyholder", "stockroom"].
    skills: Mapped[list | None] = mapped_column(JSON)

    contract_weekly_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40
    )
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))

    is_keyholder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="employee", viewonly=True)

    @property
    def is_active(self) -> bool:
        """True when the employee may be assigned to shifts."""
        return self.status == EmployeeStatus.ACTIVE

    def has_skill(self, required: str | None) -> bool:
        """Return True when the employee holds ``required``.

        An empty or ``None`` requirement is satisfied by everybody, which
        keeps shifts that need no particular skill assignable to the whole
        active team.
        """
        if not required:
            return True
        return required in (self.skills or [])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Employee {self.employee_number} status={self.status.value}>"
