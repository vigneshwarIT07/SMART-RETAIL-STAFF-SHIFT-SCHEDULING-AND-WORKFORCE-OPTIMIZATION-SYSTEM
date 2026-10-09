"""Employee availability windows and attendance records."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import AssignmentStatus, AttendanceStatus, AvailabilityType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.employee import Employee
    from app.models.shift import Shift


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Availability(Base):
    """A window during which an employee is available or unavailable.

    One row per employee, weekday and start time is permitted. An
    ``unavailable`` row blocks assignment inside the window; an ``available``
    row expresses willingness for the remaining working hours of the day.
    """

    __tablename__ = "availability"
    __table_args__ = (
        Index("ix_availability_employee_weekday", "employee_id", "weekday"),
        UniqueConstraint(
            "employee_id", "weekday", "start_time", name="uq_availability_employee_slot"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee: Mapped[Employee] = relationship(lazy="joined")

    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)
    availability_type: Mapped[AvailabilityType] = mapped_column(
        SAEnum(
            AvailabilityType, name="availability_type", native_enum=False, length=20
        ),
        nullable=False,
        default=AvailabilityType.AVAILABLE,
    )
    note: Mapped[str | None] = mapped_column(String(255))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def covers(self, day_start: time, day_end: time) -> bool:
        """True when this window fully contains the ``[day_start, day_end]`` range.

        An overnight window (end at or before start) is treated as extending
        into the following day and is only satisfied by an overnight shift.
        """
        if self.availability_type == AvailabilityType.UNAVAILABLE:
            return _overlaps(self.start_time, self.end_time, day_start, day_end)
        if self.end_time <= self.start_time:
            return day_end <= self.start_time or day_start >= self.end_time
        return self.start_time <= day_start and day_end <= self.end_time

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Availability employee={self.employee_id} day={self.weekday}>"


def _overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """True when the half-open window ``[a_start, a_end)`` intersects ``[b_start, b_end)``."""
    return a_start < b_end and b_start < a_end


class Attendance(Base):
    """One clock-in / clock-out record for one assignment.

    ``worked_minutes`` is always computed on the server from the two
    timestamps; the client never supplies it. ``status`` is likewise derived,
    except where a manager has applied an explicit correction, which is
    recorded separately in ``was_corrected`` and ``correction_reason``.
    """

    __tablename__ = "attendance"
    __table_args__ = (
        Index("ix_attendance_employee_date", "employee_id", "attendance_date"),
        Index("ix_attendance_status", "status"),
        UniqueConstraint(
            "shift_id", "employee_id", name="uq_attendance_shift_employee"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    shift_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("shifts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee: Mapped[Employee] = relationship(lazy="joined")
    shift: Mapped[Shift] = relationship(lazy="joined")

    clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(
            AttendanceStatus, name="attendance_status", native_enum=False, length=20
        ),
        nullable=False,
        default=AttendanceStatus.INCOMPLETE,
    )
    worked_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    notes: Mapped[str | None] = mapped_column(Text)
    was_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    corrected_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recorded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def is_complete(self) -> bool:
        """True when both clock events exist and minutes were computed."""
        return self.clock_in is not None and self.clock_out is not None

    @property
    def is_missing_clockout(self) -> bool:
        """True when clocked in but never clocked out."""
        return self.clock_in is not None and self.clock_out is None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Attendance employee={self.employee_id} status={self.status.value}>"


class AttendanceCorrection(Base):
    """Audit trail row written whenever a manager alters an attendance record."""

    __tablename__ = "attendance_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    attendance_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("attendance.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manager_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    previous_clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# Re-exported so callers can import the enum from one place.
__all__ = [
    "Attendance",
    "AttendanceCorrection",
    "Availability",
    "AssignmentStatus",
]
