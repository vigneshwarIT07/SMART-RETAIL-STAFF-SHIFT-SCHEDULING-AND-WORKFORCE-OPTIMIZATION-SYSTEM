"""Availability, attendance, leave, swap, notification and report schemas."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AttendanceStatus,
    AvailabilityType,
    LeaveStatus,
    LeaveType,
    SwapStatus,
)
from app.schemas.common import ORMModel


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------
class AvailabilityCreate(BaseModel):
    """Declare when an employee is available or explicitly unavailable."""

    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday.")
    start_time: time
    end_time: time
    availability_type: AvailabilityType = AvailabilityType.AVAILABLE
    note: str | None = Field(default=None, max_length=255)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> AvailabilityCreate:
        """Reject a zero-length window; overnight windows remain valid."""

        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        if (
            self.effective_from
            and self.effective_to
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        return self


class AvailabilityUpdate(BaseModel):
    """Partial availability edit."""

    start_time: time | None = None
    end_time: time | None = None
    availability_type: AvailabilityType | None = None
    note: str | None = Field(default=None, max_length=255)
    effective_from: date | None = None
    effective_to: date | None = None


class AvailabilityResponse(ORMModel):
    """One availability window."""

    id: str
    employee_id: str
    employee_name: str | None = None
    weekday: int
    start_time: time
    end_time: time
    availability_type: AvailabilityType
    note: str | None
    effective_from: date | None
    effective_to: date | None


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
class AttendanceResponse(ORMModel):
    """An attendance record with server-computed fields."""

    id: str
    shift_id: str
    employee_id: str
    employee_name: str | None = None
    attendance_date: date
    clock_in: datetime | None
    clock_out: datetime | None
    status: AttendanceStatus
    worked_minutes: int
    late_minutes: int
    notes: str | None
    was_corrected: bool
    correction_reason: str | None
    corrected_at: datetime | None
    is_missing_clockout: bool = False


class ClockInResponse(BaseModel):
    """Result of a clock-in attempt."""

    attendance: AttendanceResponse
    late_minutes: int
    shift_start: datetime | None
    message: str


class ClockOutResponse(BaseModel):
    """Result of a clock-out attempt."""

    attendance: AttendanceResponse
    worked_minutes: int
    message: str


class AttendanceCorrectionRequest(BaseModel):
    """Manager-only amendment of an attendance record."""

    clock_in: datetime | None = None
    clock_out: datetime | None = None
    status: AttendanceStatus | None = None
    reason: str = Field(
        min_length=5, max_length=500, description="Mandatory audit reason."
    )

    @model_validator(mode="after")
    def _validate(self) -> AttendanceCorrectionRequest:
        """Ensure the amendment is internally consistent."""

        if self.clock_in and self.clock_out and self.clock_out <= self.clock_in:
            raise ValueError("clock_out must be later than clock_in")
        if self.clock_in is None and self.clock_out is None and self.status is None:
            raise ValueError("supply at least one of clock_in, clock_out or status")
        return self


class MissingClockOutRow(BaseModel):
    """A record flagged for manager review because it has no clock-out."""

    attendance_id: str
    employee_id: str
    employee_name: str | None
    shift_id: str
    shift_date: date
    clock_in: datetime | None
    hours_since_clock_in: float


class AttendanceSummary(BaseModel):
    """Attendance roll-up used on the dashboard and reports."""

    period_start: date
    period_end: date
    total_records: int
    present: int
    late: int
    absent: int
    incomplete: int
    excused: int
    total_worked_hours: float
    average_late_minutes: float


# ---------------------------------------------------------------------------
# Leave
# ---------------------------------------------------------------------------
class LeaveRequestCreate(BaseModel):
    """Employee-initiated leave request."""

    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def _validate_dates(self) -> LeaveRequestCreate:
        """Leave must span at least one day and not run backwards."""

        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class LeaveDecision(BaseModel):
    """Manager approval or rejection of a leave request."""

    decision: LeaveStatus = Field(description="Use ``approved`` or ``rejected``.")
    review_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate(self) -> LeaveDecision:
        """Only terminal decisions are accepted here."""

        if self.decision not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
            raise ValueError("decision must be either approved or rejected")
        return self


class LeaveResponse(ORMModel):
    """A leave request including conflict information."""

    id: str
    employee_id: str
    employee_name: str | None = None
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str
    status: LeaveStatus
    has_conflict: bool
    conflict_details: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Shift swaps
# ---------------------------------------------------------------------------
class SwapEligibility(BaseModel):
    """Why a proposed swap is or is not acceptable."""

    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SwapCreate(BaseModel):
    """Employee-initiated swap request between two shifts."""

    target_employee_id: str
    requester_shift_id: str
    target_shift_id: str
    reason: str = Field(min_length=3, max_length=500)


class SwapDecision(BaseModel):
    """Manager approval or rejection of a swap."""

    decision: SwapStatus = Field(description="Use ``approved`` or ``rejected``.")
    review_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate(self) -> SwapDecision:
        """Only terminal decisions are accepted here."""

        if self.decision not in (SwapStatus.APPROVED, SwapStatus.REJECTED):
            raise ValueError("decision must be either approved or rejected")
        return self


class SwapResponse(ORMModel):
    """A swap request with its stored eligibility snapshot."""

    id: str
    requester_id: str
    requester_name: str | None = None
    target_employee_id: str
    target_employee_name: str | None = None
    requester_shift_id: str
    target_shift_id: str
    reason: str
    status: SwapStatus
    has_conflict: bool
    conflict_details: str | None
    eligibility: dict | None = None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class NotificationResponse(ORMModel):
    """An in-app notification."""

    id: str
    notification_type: str
    title: str
    body: str | None
    is_read: bool
    read_at: datetime | None
    link_url: str | None
    email_status: str | None = None
    created_at: datetime


class UnreadCount(BaseModel):
    """Unread notification total for the current user."""

    unread: int


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
class WorkingHoursRow(BaseModel):
    """Worked hours per employee for a reporting period."""

    employee_id: str
    employee_name: str
    employee_number: str
    shifts_worked: int
    scheduled_hours: float
    worked_hours: float
    late_count: int
    absent_count: int


class LeaveBreakdownRow(BaseModel):
    """Leave days grouped by leave type."""

    leave_type: LeaveType
    request_count: int
    total_days: float


class StoreSummary(BaseModel):
    """Headline store metrics for the dashboard."""

    store_name: str
    total_employees: int
    active_employees: int
    shifts_this_week: int
    unassigned_shifts: int
    pending_leave_requests: int
    pending_swap_requests: int
    attendance_anomalies: int


class CsvExportPayload(BaseModel):
    """Server-rendered CSV download."""

    filename: str
    content_type: str = "text/csv"
    rows: int
