"""Shift, assignment and scheduling schemas."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AssignmentStatus, CoverageStatus, ShiftStatus
from app.schemas.common import ORMModel


class ShiftCreate(BaseModel):
    """Manager payload for creating a single shift slot."""

    shift_date: date
    start_time: time
    end_time: time
    role_required: str | None = Field(default=None, max_length=50)
    required_skill: str | None = Field(default=None, max_length=50)
    required_employees: int = Field(default=1, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=1000)
    publish: bool = Field(
        default=False,
        description="Publish immediately instead of leaving the shift in draft.",
    )

    @model_validator(mode="after")
    def _validate_window(self) -> ShiftCreate:
        """Reject a zero-length shift while still allowing overnight windows."""

        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        if self.required_skill:
            object.__setattr__(
                self, "required_skill", self.required_skill.strip().lower()
            )
        return self


class ShiftUpdate(BaseModel):
    """Partial shift update. Cancelled shifts cannot be edited further."""

    start_time: time | None = None
    end_time: time | None = None
    role_required: str | None = Field(default=None, max_length=50)
    required_skill: str | None = Field(default=None, max_length=50)
    required_employees: int | None = Field(default=None, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=1000)
    status: ShiftStatus | None = None


class ShiftBulkCreate(BaseModel):
    """Create several shifts from a weekly template."""

    start_date: date
    days: list[date] = Field(
        min_length=1,
        description="Concrete calendar dates to create. Kept explicit so the request is auditable.",
    )
    start_time: time
    end_time: time
    role_required: str | None = Field(default=None, max_length=50)
    required_skill: str | None = Field(default=None, max_length=50)
    required_employees: int = Field(default=1, ge=1, le=20)
    notes: str | None = Field(default=None, max_length=1000)
    publish: bool = False

    @model_validator(mode="after")
    def _validate_days(self) -> ShiftBulkCreate:
        """Ensure every requested day falls inside a seven day window."""

        if not self.days:
            raise ValueError("at least one day is required")
        return self


class AssignmentResponse(ORMModel):
    """One employee-to-shift assignment."""

    id: str
    shift_id: str
    employee_id: str
    status: AssignmentStatus
    assigned_by: str | None
    assigned_at: datetime
    cancelled_at: datetime | None
    cancelled_reason: str | None
    notes: str | None
    is_auto_assigned: bool


class AssignmentDetail(AssignmentResponse):
    """Assignment enriched with the employee name for calendar rendering."""

    employee_name: str | None = None
    employee_number: str | None = None


class ShiftResponse(ORMModel):
    """A shift with its server-computed duration and coverage state."""

    id: str
    store_id: str
    shift_date: date
    start_time: time
    end_time: time
    role_required: str | None
    required_skill: str | None
    required_employees: int
    status: ShiftStatus
    notes: str | None
    created_by: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    duration_hours: float = 0.0
    is_overnight: bool = False
    assigned_count: int = 0
    coverage_status: CoverageStatus = CoverageStatus.UNASSIGNED
    assignments: list[AssignmentDetail] = Field(default_factory=list)


class AssignmentCreate(BaseModel):
    """Assign one employee to one shift."""

    shift_id: str
    employee_id: str
    notes: str | None = Field(default=None, max_length=500)
    force: bool = Field(
        default=False,
        description="Manager override. Blocking violations still cannot be forced.",
    )


class AssignmentValidationIssue(BaseModel):
    """A single validation outcome for a proposed assignment."""

    code: str = Field(description="Machine readable rule identifier.")
    message: str = Field(description="Plain-language explanation for the manager.")
    blocking: bool = Field(description="True when the assignment must be refused.")


class AssignmentValidationResult(BaseModel):
    """The complete rule verdict for a proposed assignment."""

    valid: bool
    violations: list[AssignmentValidationIssue] = Field(default_factory=list)
    warnings: list[AssignmentValidationIssue] = Field(default_factory=list)

    @property
    def blocking_reasons(self) -> list[str]:
        """Messages for the violations that prevented the assignment."""

        return [issue.message for issue in self.violations]


class EmployeeAvailabilitySlot(BaseModel):
    """Availability summary for a single weekday, used by the assign dialog."""

    weekday: int
    available: bool = False
    reason: str | None = None


class CalendarDay(BaseModel):
    """One day of the weekly calendar response."""

    date: date
    shifts: list[ShiftResponse] = Field(default_factory=list)


class CalendarResponse(BaseModel):
    """A full week of shifts keyed by ISO weekday for calendar rendering."""

    week_start: date
    week_end: date
    days: list[CalendarDay]
    coverage_summary: dict[str, int] = Field(default_factory=dict)


class CoverageRow(BaseModel):
    """Coverage for a single shift, including who is missing."""

    shift_id: str
    shift_date: date
    start_time: time
    end_time: time
    required_employees: int
    assigned_employees: int
    coverage_status: CoverageStatus
    missing_employees: int
    assigned_employee_ids: list[str] = Field(default_factory=list)
    is_overnight: bool = False


class CoverageResponse(BaseModel):
    """Coverage across a date range."""

    start_date: date
    end_date: date
    rows: list[CoverageRow]
    summary: dict[str, int]


class WeeklyHoursRow(BaseModel):
    """One employee's scheduled hours inside the requested week."""

    employee_id: str
    employee_name: str
    employee_number: str
    shift_count: int
    scheduled_hours: float
    contract_weekly_hours: int
    overtime_hours: float = 0.0
    warning: str | None = None
    is_overtime: bool = False


class FairnessRow(BaseModel):
    """One employee's share of the scheduled hours in the range."""

    employee_id: str
    employee_name: str
    shift_count: int
    scheduled_hours: float
    deviation_from_average: float = 0.0


class SchedulingReport(BaseModel):
    """Aggregate scheduling statistics for the dashboard and reports screen."""

    start_date: date
    end_date: date
    weekly_hours: list[WeeklyHoursRow]
    fairness: list[FairnessRow]
    total_scheduled_hours: float
    average_hours: float
    max_hours: float
    min_hours: float
    hours_spread: float
    overtime_employees: list[str]
    warnings: list[str] = Field(default_factory=list)


class GenerationRequest(BaseModel):
    """Ask the proposal engine for a draft schedule."""

    start_date: date
    end_date: date
    employee_ids: list[str] | None = Field(
        default=None,
        description="Restrict the proposal to these employees. All active staff when omitted.",
    )
    respect_availability: bool = True
    balance_hours: bool = Field(
        default=True, description="Prefer the least-loaded eligible employee."
    )


class ProposedAssignment(BaseModel):
    """One proposed assignment plus the reason it was chosen."""

    shift_id: str
    employee_id: str
    employee_name: str
    reasons: list[str] = Field(default_factory=list)


class UnfillableShift(BaseModel):
    """A shift the engine could not fill, with the blocking reasons."""

    shift_id: str
    shift_date: date
    start_time: time
    end_time: time
    reason: str


class GenerationResult(BaseModel):
    """A complete, reviewable proposal. Nothing is persisted until applied."""

    start_date: date
    end_date: date
    proposals: list[ProposedAssignment]
    unfillable: list[UnfillableShift]
    is_deterministic: bool = True
    applied: bool = Field(
        default=False,
        description="Always False: proposals require explicit confirmation.",
    )
    summary: str


class ApplyGenerationRequest(BaseModel):
    """Explicit manager confirmation that converts a proposal into real rows."""

    start_date: date
    end_date: date
    proposals: list[ProposedAssignment]
    publish: bool = Field(
        default=False,
        description="Publish the affected shifts as part of the same action.",
    )
