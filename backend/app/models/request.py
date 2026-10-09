"""Leave requests and shift swap requests.

Both features share a shape: an employee raises a request, the manager
decides, and the decision is revalidated against current data at approval
time so a request cannot be granted against state that has since changed.
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
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import LeaveStatus, LeaveType, SwapStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.employee import Employee
    from app.models.shift import Shift


def _uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class LeaveRequest(Base):
    """A request from an employee to be absent for a date range."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_employee_status", "employee_id", "status"),
        Index("ix_leave_dates", "start_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee: Mapped[Employee] = relationship(lazy="joined")

    leave_type: Mapped[LeaveType] = mapped_column(
        SAEnum(LeaveType, name="leave_type", native_enum=False, length=20),
        nullable=False,
        default=LeaveType.ANNUAL,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    status: Mapped[LeaveStatus] = mapped_column(
        SAEnum(LeaveStatus, name="leave_status", native_enum=False, length=20),
        nullable=False,
        default=LeaveStatus.PENDING,
    )
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_details: Mapped[str | None] = mapped_column(Text)

    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

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
    def is_pending(self) -> bool:
        """True while the request awaits a manager decision."""
        return self.status == LeaveStatus.PENDING

    def overlaps_shift_dates(self, shift_dates: list[date]) -> bool:
        """True when any supplied shift date falls inside the leave range."""
        for shift_date in shift_dates:
            if self.start_date <= shift_date <= self.end_date:
                return True
        return False

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LeaveRequest employee={self.employee_id} status={self.status.value}>"


class ShiftSwapRequest(Base):
    """A request to hand one shift to a colleague.

    ``requester`` gives up their shift and ``target`` picks up the
    counterpart shift, which is what makes this a two-sided atomic swap
    rather than a reassignment. Either both changes apply or neither does.
    """

    __tablename__ = "shift_swap_requests"
    __table_args__ = (
        Index("ix_swaps_requester_status", "requester_id", "status"),
        Index("ix_swaps_target_status", "target_employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    requester_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester: Mapped[Employee] = relationship(
        foreign_keys=[requester_id], lazy="joined"
    )

    target_employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_employee: Mapped[Employee] = relationship(
        foreign_keys=[target_employee_id], lazy="joined"
    )

    requester_shift_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    requester_shift: Mapped[Shift] = relationship(
        foreign_keys=[requester_shift_id], lazy="joined"
    )

    target_shift_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    target_shift: Mapped[Shift] = relationship(
        foreign_keys=[target_shift_id], lazy="joined"
    )

    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SwapStatus] = mapped_column(
        SAEnum(SwapStatus, name="swap_status", native_enum=False, length=20),
        nullable=False,
        default=SwapStatus.PENDING,
    )

    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_details: Mapped[str | None] = mapped_column(Text)
    eligibility: Mapped[dict | None] = mapped_column(JSON)

    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

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
    def is_pending(self) -> bool:
        """True while the request awaits a manager decision."""
        return self.status == SwapStatus.PENDING

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ShiftSwapRequest requester={self.requester_id} status={self.status.value}>"
