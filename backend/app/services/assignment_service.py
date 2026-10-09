"""Assignment validation and lifecycle service.

Implements the ten assignment rules required by the product specification.
Every rule lives here — routers only translate service results into HTTP.

Rule summary (rule codes map 1:1 to the specification)
------------------------------------------------------
1.  ``employee-inactive``   — employee must be ACTIVE.
2.  ``wrong-store``         — employee must belong to the shift's store.
3.  ``overlap``             — no overlapping active assignment (UTC intervals).
4.  ``unavailable``         — no UNAVAILABLE availability row covering the shift.
5.  ``on-leave``            — no approved leave request overlapping shift dates.
6.  ``skill-mismatch``      — employee must hold ``shift.required_skill``.
7.  ``weekly-hours``        — projected ISO week hours must stay within the cap.
8.  ``rest-interval``       — minimum rest hours between adjacent shifts.
9.  ``consecutive-days``    — maximum consecutive working days.
10. ``shift-closed``        — shift must be DRAFT or PUBLISHED.

Blocking semantics: a violation blocks assignment unless the caller passes
``force=True`` (manager override).  Overrides are recorded in the audit log
by the caller so they stay visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AssignmentStatus,
    AuditAction,
    AvailabilityType,
    Employee,
    LeaveRequest,
    LeaveStatus,
    Shift,
    ShiftAssignment,
    ShiftStatus,
    User,
)
from app.models.attendance import Availability
from app.models.user import Store

from . import audit_service, notification_service, shift_service

# Blocking rule codes — everything else is advisory (a warning).
_BLOCKING_RULES = frozenset(
    {
        "employee-inactive",
        "wrong-store",
        "overlap",
        "on-leave",
        "shift-closed",
    }
)


def _blocking(code: str) -> bool:
    """Return True when a rule violation must block assignment."""
    return code in _BLOCKING_RULES


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return the UTC day bounds for a calendar date."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def weekly_hours(
    db: Session,
    employee_id: str,
    week_start: date,
) -> Decimal:
    """Return scheduled hours for the ISO week starting ``week_start``.

    Sums the duration of shifts linked to non-cancelled assignments whose
    ``shift_date`` falls inside the seven-day window.
    """
    week_end = week_start + timedelta(days=7)
    stmt = (
        select(Shift)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            ),
            Shift.shift_date >= week_start,
            Shift.shift_date < week_end,
            Shift.status != ShiftStatus.CANCELLED,
        )
    )
    total = Decimal("0")
    for shift in db.scalars(stmt).all():
        total += Decimal(str(shift.duration_hours))
    return total


def consecutive_work_days(
    db: Session,
    employee_id: str,
    anchor: date,
) -> int:
    """Count consecutive scheduled days ending on ``anchor`` (inclusive)."""
    worked: set[date] = set()
    stmt = (
        select(Shift.shift_date)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            ),
            Shift.shift_date <= anchor,
            Shift.shift_date >= anchor - timedelta(days=30),
            Shift.status != ShiftStatus.CANCELLED,
        )
    )
    for row in db.execute(stmt):
        worked.add(row[0])
    streak = 0
    cursor = anchor
    while cursor in worked:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _interval(db: Session, shift: Shift) -> tuple[datetime, datetime]:
    """UTC interval for a shift, loading its store for timezone handling."""
    store = db.scalar(select(Store).where(Store.id == shift.store_id))
    if store is None:  # pragma: no cover - corrupt data guard
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = datetime.combine(shift.shift_date, shift.start_time, tzinfo=tz)
        end = datetime.combine(shift.shift_date, shift.end_time, tzinfo=tz)
        if shift.end_time <= shift.start_time:
            end += timedelta(days=1)
        return start, end
    return shift_service.shift_interval(store, shift)


def validate_assignment(
    db: Session,
    shift: Shift,
    employee: Employee,
    *,
    force: bool = False,
    max_weekly_hours: int | None = None,
    min_rest_hours: int | None = None,
    max_consecutive_days: int | None = None,
) -> dict:
    """Validate assigning ``employee`` to ``shift``.

    Returns ``{"valid", "violations", "warnings"}`` where each issue is a
    ``{"code", "message", "blocking"}`` mapping.  ``valid`` is True when no
    *blocking* violation exists, or when ``force`` is set.
    """
    violations: list[dict] = []
    warnings: list[dict] = []

    def add(code: str, message: str) -> None:
        issue = {"code": code, "message": message, "blocking": _blocking(code)}
        (violations if issue["blocking"] else warnings).append(issue)

    # Rule 10 — shift must accept assignments.
    if not shift.accepts_assignments():
        add("shift-closed", f"Shift is {shift.status.value}; assignments are closed.")

    # Rule 1 — employee must be active.
    if not employee.is_active:
        add(
            "employee-inactive",
            f"Employee is {employee.status.value}; only active staff can be assigned.",
        )

    # Rule 2 — same store.
    if employee.store_id != shift.store_id:
        add(
            "wrong-store",
            "Employee belongs to a different store and cannot take this shift.",
        )

    # Rule 3 — no overlapping active assignment (UTC comparison).
    new_start, new_end = _interval(db, shift)
    overlap_stmt = (
        select(Shift, ShiftAssignment)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id == employee.id,
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            ),
            Shift.id != shift.id,
            Shift.status != ShiftStatus.CANCELLED,
        )
    )
    for other, _link in db.execute(overlap_stmt):
        other_start, other_end = _interval(db, other)
        if new_start < other_end and other_start < new_end:
            add(
                "overlap",
                f"Overlaps {other.shift_date} "
                f"{other.start_time.strftime('%H:%M')}-{other.end_time.strftime('%H:%M')}.",
            )
            break

    # Rule 4 — availability must not mark the window unavailable.
    weekday = shift.shift_date.weekday()
    avail_stmt = select(Availability).where(
        Availability.employee_id == employee.id,
        Availability.weekday == weekday,
        Availability.availability_type == AvailabilityType.UNAVAILABLE,
    )
    for row in db.scalars(avail_stmt).all():
        if not row.effective_from or row.effective_from <= shift.shift_date:
            if not row.effective_to or row.effective_to >= shift.shift_date:
                # UNAVAILABLE rows: covers() reports overlap with the shift
                # window; AVAILABLE rows never block here.
                if row.covers(shift.start_time, shift.end_time):
                    add(
                        "unavailable",
                        "Employee marked themselves unavailable for this time.",
                    )
                    break

    # Rule 5 — approved leave conflict.
    leave_stmt = select(LeaveRequest).where(
        LeaveRequest.employee_id == employee.id,
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= shift.shift_date,
        LeaveRequest.end_date >= shift.shift_date,
    )
    if db.scalars(leave_stmt).first() is not None:
        add("on-leave", "Employee has approved leave covering this date.")

    # Rule 6 — skill match (warning; managers may train into a role).
    if shift.required_skill and not employee.has_skill(shift.required_skill):
        add(
            "skill-mismatch",
            f"Shift needs '{shift.required_skill}' which the employee lacks.",
        )

    # Rule 7 — weekly hours cap (warning; overtime is allowed but flagged).
    cap = (
        max_weekly_hours if max_weekly_hours is not None else settings.max_weekly_hours
    )
    week_start = shift.shift_date - timedelta(days=shift.shift_date.weekday())
    projected = weekly_hours(db, employee.id, week_start) + Decimal(
        str(shift.duration_hours)
    )
    if projected > cap:
        add(
            "weekly-hours",
            f"Week total would be {projected:.1f}h against a {cap}h cap.",
        )

    # Rule 8 — minimum rest between adjacent shifts (warning).
    rest_floor = (
        min_rest_hours
        if min_rest_hours is not None
        else settings.min_rest_hours_between_shifts
    )
    adjacent_stmt = (
        select(Shift)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id == employee.id,
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            ),
            Shift.id != shift.id,
            Shift.status != ShiftStatus.CANCELLED,
            Shift.shift_date >= shift.shift_date - timedelta(days=2),
            Shift.shift_date <= shift.shift_date + timedelta(days=2),
        )
    )
    for other in db.scalars(adjacent_stmt).all():
        other_start, other_end = _interval(db, other)
        gap = (
            (new_start - other_end).total_seconds() / 3600
            if new_start >= other_end
            else (other_start - new_end).total_seconds() / 3600
        )
        if 0 <= gap < rest_floor:
            add(
                "rest-interval",
                f"Only {gap:.1f}h rest against a {rest_floor}h minimum.",
            )
            break

    # Rule 9 — consecutive working days (warning).
    day_cap = (
        max_consecutive_days
        if max_consecutive_days is not None
        else settings.max_consecutive_work_days
    )
    streak = consecutive_work_days(
        db, employee.id, shift.shift_date - timedelta(days=1)
    )
    if streak + 1 > day_cap:
        add(
            "consecutive-days",
            f"Would work {streak + 1} consecutive days (limit {day_cap}).",
        )

    blocking = [issue for issue in violations if issue["blocking"]]
    return {
        "valid": not blocking or force,
        "violations": violations,
        "warnings": warnings,
    }


def assign_employee(
    db: Session,
    shift: Shift,
    employee: Employee,
    assigned_by: User,
    *,
    notes: str | None = None,
    force: bool = False,
    is_auto_assigned: bool = False,
) -> ShiftAssignment:
    """Assign an employee after validation; raises on blocking violations."""
    result = validate_assignment(db, shift, employee, force=force)
    if not result["valid"]:
        from app.core.errors import ConflictError

        raise ConflictError("; ".join(i["message"] for i in result["violations"]))

    existing_stmt = select(ShiftAssignment).where(
        ShiftAssignment.shift_id == shift.id,
        ShiftAssignment.employee_id == employee.id,
    )
    existing = db.scalars(existing_stmt).first()
    if existing is not None and existing.status not in (
        AssignmentStatus.CANCELLED,
        AssignmentStatus.NO_SHOW,
    ):
        from app.core.errors import ConflictError

        raise ConflictError("Employee is already assigned to this shift.")

    if existing is not None:
        existing.status = AssignmentStatus.ASSIGNED
        existing.assigned_by = assigned_by.id
        existing.assigned_at = datetime.now(UTC)
        existing.cancelled_at = None
        existing.cancelled_reason = None
        existing.notes = notes
        existing.is_auto_assigned = is_auto_assigned
        assignment = existing
    else:
        assignment = ShiftAssignment(
            shift_id=shift.id,
            employee_id=employee.id,
            status=AssignmentStatus.ASSIGNED,
            assigned_by=assigned_by.id,
            notes=notes,
            is_auto_assigned=is_auto_assigned,
        )
        db.add(assignment)
    db.flush()

    audit_service.log_action(
        db,
        action=AuditAction.ASSIGNMENT,
        entity_type="shift_assignment",
        entity_id=assignment.id,
        user_id=assigned_by.id,
        store_id=shift.store_id,
        details={
            "shift_id": shift.id,
            "employee_id": employee.id,
            "forced": force,
            "auto": is_auto_assigned,
        },
    )
    # Notify the employee's linked user account, if any.
    manager_user = assigned_by
    employee_user_stmt = select(User).where(User.id == employee.id)
    employee_user = db.scalars(employee_user_stmt).first()
    if employee_user is not None:
        notification_service.create_notification(
            db,
            user_id=employee_user.id,
            notification_type="ASSIGNMENT",
            title=f"Assigned: {shift.shift_date} {shift.start_time.strftime('%H:%M')}",
            body=(
                f"You were assigned to {shift.role_required or 'a shift'} on "
                f"{shift.shift_date} ({shift.start_time.strftime('%H:%M')}-"
                f"{shift.end_time.strftime('%H:%M')})."
            ),
            link_url=f"/shifts?date={shift.shift_date.isoformat()}",
            dedupe_key=f"assign-{shift.id}-{employee.id}-{shift.updated_at.date().isoformat() if shift.updated_at else 'new'}",
        )
    db.flush()
    _ = manager_user
    return assignment


def unassign_employee(
    db: Session,
    assignment: ShiftAssignment,
    removed_by: User,
    *,
    reason: str | None = None,
) -> ShiftAssignment:
    """Cancel an assignment, recording who removed it and why."""
    assignment.status = AssignmentStatus.CANCELLED
    assignment.cancelled_at = datetime.now(UTC)
    assignment.cancelled_reason = reason
    db.flush()
    shift_stmt = select(Shift).where(Shift.id == assignment.shift_id)
    shift = db.scalars(shift_stmt).first()
    audit_service.log_action(
        db,
        action=AuditAction.UNASSIGNMENT,
        entity_type="shift_assignment",
        entity_id=assignment.id,
        user_id=removed_by.id,
        store_id=shift.store_id if shift else removed_by.store_id,
        details={"employee_id": assignment.employee_id, "reason": reason},
    )
    db.flush()
    return assignment


def list_assignments_for_shift(db: Session, shift_id: str) -> Sequence[ShiftAssignment]:
    """Return all assignments for a shift, active first."""
    stmt = (
        select(ShiftAssignment)
        .where(ShiftAssignment.shift_id == shift_id)
        .order_by(ShiftAssignment.assigned_at)
    )
    return db.scalars(stmt).all()


def list_assignments_for_employee(
    db: Session,
    employee_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    include_cancelled: bool = False,
) -> Sequence[ShiftAssignment]:
    """Return assignments for an employee, optionally within a date window."""
    conditions = [ShiftAssignment.employee_id == employee_id]
    if not include_cancelled:
        conditions.append(
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            )
        )
    stmt = select(ShiftAssignment).where(and_(*conditions))
    if start is not None or end is not None:
        stmt = stmt.join(Shift, Shift.id == ShiftAssignment.shift_id)
        if start is not None:
            stmt = stmt.where(Shift.shift_date >= start)
        if end is not None:
            stmt = stmt.where(Shift.shift_date <= end)
        stmt = stmt.order_by(Shift.shift_date, Shift.start_time)
    return db.scalars(stmt).all()


def confirm_assignment(db: Session, assignment: ShiftAssignment) -> ShiftAssignment:
    """Mark an assignment CONFIRMED (employee acknowledgement)."""
    if assignment.status == AssignmentStatus.ASSIGNED:
        assignment.status = AssignmentStatus.CONFIRMED
        db.flush()
    return assignment


def active_assignment_count(db: Session, shift_id: str) -> int:
    """Count active (non-cancelled) assignments on a shift."""
    from sqlalchemy import func

    stmt = select(func.count()).where(
        ShiftAssignment.shift_id == shift_id,
        ShiftAssignment.status.notin_(
            [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
        ),
    )
    return int(db.scalar(stmt) or 0)


def find_eligible_employees(
    db: Session,
    shift: Shift,
    candidates: Sequence[Employee],
) -> list[dict]:
    """Rank candidates for a shift by validation outcome, fewest hours first."""
    week_start = shift.shift_date - timedelta(days=shift.shift_date.weekday())
    ranked: list[dict] = []
    for employee in candidates:
        result = validate_assignment(db, shift, employee)
        hours = weekly_hours(db, employee.id, week_start)
        ranked.append(
            {
                "employee": employee,
                "valid": result["valid"],
                "violations": result["violations"],
                "warnings": result["warnings"],
                "weekly_hours": hours,
            }
        )
    ranked.sort(
        key=lambda row: (
            not row["valid"],
            len(row["violations"]) + len(row["warnings"]),
            float(row["weekly_hours"]),
        )
    )
    return ranked
