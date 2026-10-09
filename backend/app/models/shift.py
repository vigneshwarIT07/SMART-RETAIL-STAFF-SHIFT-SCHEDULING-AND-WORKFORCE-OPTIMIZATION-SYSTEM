"""Shift definitions and employee-to-shift assignments."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import AssignmentStatus, ShiftStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.employee import Employee
    from app.models.user import Store


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Shift(Base):
    """A single block of work at a store on a given date.

    ``end_time`` earlier than ``start_time`` denotes an overnight shift; the
    helper :meth:`is_overnight` and the interval utility in
    ``app.services.shift_service`` handle the resulting date arithmetic.
    """

    __tablename__ = "shifts"
    __table_args__ = (
        Index("ix_shifts_store_date", "store_id", "shift_date"),
        Index("ix_shifts_status", "status"),
        UniqueConstraint("store_id", "shift_date", "start_time", name="uq_shift_slot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store: Mapped["Store"] = relationship()

    shift_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)

    role_required: Mapped[str | None] = mapped_column(String(50))
    required_skill: Mapped[str | None] = mapped_column(String(50))
    required_employees: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[ShiftStatus] = mapped_column(
        SAEnum(ShiftStatus, name="shift_status", native_enum=False, length=20),
        nullable=False,
        default=ShiftStatus.DRAFT,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    assignments: Mapped[list["ShiftAssignment"]] = relationship(
        back_populates="shift",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------
    def is_overnight(self) -> bool:
        """True when the shift ends on the calendar day after it starts."""
        return self.end_time <= self.start_time

    @property
    def duration_minutes(self) -> int:
        """Scheduled length in minutes, accounting for overnight shifts."""
        start = datetime.combine(self.shift_date, self.start_time)
        end = datetime.combine(self.shift_date, self.end_time)
        if self.end_time <= self.start_time:
            end += timedelta(days=1)
        return int((end - start).total_seconds() // 60)

    @property
    def duration_hours(self) -> float:
        """Scheduled length in hours, rounded to two decimals."""
        return round(self.duration_minutes / 60, 2)

    def accepts_assignments(self) -> bool:
        """True when new assignments may be added to this shift."""
        return self.status in (ShiftStatus.DRAFT, ShiftStatus.PUBLISHED)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Shift {self.shift_date} {self.start_time}-{self.end_time}>"


class ShiftAssignment(Base):
    """Links one employee to one shift.

    A cancelled assignment is retained rather than deleted so that the audit
    trail shows who was scheduled and who was later removed. Only one live
    row per employee and shift is permitted, enforced by a partial unique
    index created in the Alembic migration.
    """

    __tablename__ = "shift_assignments"
    __table_args__ = (
        Index("ix_assignments_employee_status", "employee_id", "status"),
        Index("ix_assignments_shift_status", "shift_id", "status"),
        UniqueConstraint("shift_id", "employee_id", name="uq_assignment_shift_employee"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, name="assignment_status", native_enum=False, length=20),
        nullable=False,
        default=AssignmentStatus.ASSIGNED,
    )
    assigned_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    is_auto_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    shift: Mapped["Shift"] = relationship(back_populates="assignments")
    employee: Mapped["Employee"] = relationship(lazy="joined")

    @property
    def is_active(self) -> bool:
        """True when the assignment occupies a place on the shift."""
        return self.status in (
            AssignmentStatus.ASSIGNED,
            AssignmentStatus.CONFIRMED,
            AssignmentStatus.COMPLETED,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ShiftAssignment shift={self.shift_id} employee={self.employee_id}>"