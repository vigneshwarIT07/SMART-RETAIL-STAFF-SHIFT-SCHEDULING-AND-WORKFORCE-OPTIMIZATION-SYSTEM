"""Scheduling reports: coverage, weekly hours, fairness and conflicts.

Read-only analytics over shifts and assignments for one store.  Hours are
treated as configurable business rules (see :mod:`app.core.config`) — this
module never claims legal labour-law compliance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AssignmentStatus,
    AvailabilityType,
    CoverageStatus,
    Employee,
    LeaveRequest,
    LeaveStatus,
    Shift,
    ShiftAssignment,
    ShiftStatus,
)
from app.models.attendance import Availability
from app.models.user import Store, User

from . import assignment_service, shift_service


def coverage_status(shift: Shift, active_count: int) -> CoverageStatus:
    """Coverage label for one shift given its active assignment count."""
    if shift.status == ShiftStatus.CANCELLED:
        return CoverageStatus.CANCELLED
    if active_count <= 0:
        return CoverageStatus.UNASSIGNED
    if active_count < (shift.required_employees or 1):
        return CoverageStatus.UNDERSTAFFED
    return CoverageStatus.FULLY_STAFFED


def week_coverage(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """One coverage row per shift in the window, with assignment counts."""
    shifts = db.scalars(
        select(Shift)
        .where(
            Shift.store_id == store_id,
            Shift.shift_date >= start_date,
            Shift.shift_date <= end_date,
        )
        .order_by(Shift.shift_date, Shift.start_time)
    ).all()
    rows: list[dict] = []
    for shift in shifts:
        count = assignment_service.active_assignment_count(db, shift.id)
        status = coverage_status(shift, count)
        rows.append(
            {
                "shift_id": shift.id,
                "shift_date": shift.shift_date,
                "start_time": shift.start_time,
                "end_time": shift.end_time,
                "role_required": shift.role_required,
                "required_employees": shift.required_employees,
                "assigned_count": count,
                "coverage_status": status,
                "shift_status": shift.status,
            }
        )
    return rows


def coverage_summary(rows: Sequence[dict]) -> dict:
    """Aggregate counts of shifts by coverage status."""
    summary = {
        "total": len(rows),
        "fully_staffed": 0,
        "understaffed": 0,
        "unassigned": 0,
        "cancelled": 0,
    }
    for row in rows:
        status = row["coverage_status"]
        if status == CoverageStatus.FULLY_STAFFED:
            summary["fully_staffed"] += 1
        elif status == CoverageStatus.UNDERSTAFFED:
            summary["understaffed"] += 1
        elif status == CoverageStatus.UNASSIGNED:
            summary["unassigned"] += 1
        elif status == CoverageStatus.CANCELLED:
            summary["cancelled"] += 1
    return summary


def weekly_hours_report(
    db: Session,
    *,
    store_id: str,
    week_start: date,
    overtime_threshold: float | None = None,
) -> list[dict]:
    """Scheduled hours per active employee for the ISO week of ``week_start``.

    Employees projected above ``overtime_threshold`` (default from settings)
    are flagged so managers can rebalance before publishing.
    """
    week_start = week_start - timedelta(days=week_start.weekday())
    threshold = (
        overtime_threshold if overtime_threshold is not None else settings.overtime_warning_hours
    )
    employees = db.scalars(
        select(Employee).where(Employee.store_id == store_id, Employee.status == "ACTIVE")
    ).all()
    rows: list[dict] = []
    for employee in employees:
        hours = assignment_service.weekly_hours(db, employee.id, week_start)
        rows.append(
            {
                "employee_id": employee.id,
                "employee_name": _display_name(db, employee),
                "employee_number": employee.employee_number,
                "scheduled_hours": float(hours),
                "contract_hours": employee.contract_weekly_hours or 0,
                "overtime_warning": float(hours) > threshold,
            }
        )
    rows.sort(key=lambda row: row["scheduled_hours"], reverse=True)
    return rows


def fairness_report(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Shift-count and hour spread per employee across the window."""
    employees = db.scalars(select(Employee).where(Employee.store_id == store_id)).all()
    rows: list[dict] = []
    for employee in employees:
        stmt = (
            select(Shift)
            .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.status.notin_(
                    [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
                ),
                Shift.status != ShiftStatus.CANCELLED,
                Shift.shift_date >= start_date,
                Shift.shift_date <= end_date,
            )
        )
        shifts = db.scalars(stmt).all()
        total = sum(Decimal(str(s.duration_hours)) for s in shifts)
        rows.append(
            {
                "employee_id": employee.id,
                "employee_name": _display_name(db, employee),
                "shift_count": len(shifts),
                "total_hours": float(total),
            }
        )
    rows.sort(key=lambda row: row["total_hours"], reverse=True)
    return rows


def conflict_list(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """All current assignment violations/warnings in the window.

    Re-runs :func:`assignment_service.validate_assignment` for every active
    assignment so managers see conflicts introduced by later edits (leave
    approvals, shift time changes) in one place.

    Performance: validation is rule-identical to the single-shot path, but
    every row it needs is preloaded here in a handful of queries and handed
    over as a snapshot (``ctx``).  Without this, each assignment costs ~10
    roundtrips (plus one per neighbouring shift for timezone intervals),
    which stalls past a minute on hosted Postgres once a week holds a few
    dozen assignments.
    """
    stmt = (
        select(Shift, ShiftAssignment, Employee)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .join(Employee, Employee.id == ShiftAssignment.employee_id)
        .where(
            Shift.store_id == store_id,
            Shift.shift_date >= start_date,
            Shift.shift_date <= end_date,
            ShiftAssignment.status.notin_([AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]),
        )
        .order_by(Shift.shift_date, Shift.start_time)
    )
    window_rows = db.execute(stmt).all()
    if not window_rows:
        return []

    employee_ids = sorted({employee.id for _, _, employee in window_rows})
    store = db.scalar(select(Store).where(Store.id == store_id))
    if store is None:  # pragma: no cover - window rows imply the store exists
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Store {store_id} not found.")

    # Every active assignment of the involved employees (any date): one query.
    # Non-cancelled shifts only, mirroring each rule's own filters.
    all_stmt = (
        select(Shift, ShiftAssignment)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id.in_(employee_ids),
            ShiftAssignment.status.notin_([AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]),
            Shift.status != ShiftStatus.CANCELLED,
        )
        .order_by(Shift.shift_date, Shift.start_time)
    )
    emp_shifts: dict[str, list] = {eid: [] for eid in employee_ids}
    worked_dates: dict[str, set[date]] = {eid: set() for eid in employee_ids}
    week_hours: dict[tuple[str, date], Decimal] = {}
    intervals: dict[str, tuple] = {}
    for other_shift, link in db.execute(all_stmt):
        start, end = shift_service.shift_interval(store, other_shift)
        intervals.setdefault(other_shift.id, (start, end))
        emp_shifts[link.employee_id].append((other_shift, start, end))
        worked_dates[link.employee_id].add(other_shift.shift_date)
        monday = other_shift.shift_date - timedelta(days=other_shift.shift_date.weekday())
        key = (link.employee_id, monday)
        week_hours[key] = week_hours.get(key, Decimal("0")) + Decimal(
            str(other_shift.duration_hours)
        )
    # Intervals for window shifts even when they carry no active assignment.
    for shift, _, _ in window_rows:
        intervals.setdefault(shift.id, shift_service.shift_interval(store, shift))

    unavailable: dict[str, list] = {eid: [] for eid in employee_ids}
    for row in db.scalars(
        select(Availability).where(
            Availability.employee_id.in_(employee_ids),
            Availability.availability_type == AvailabilityType.UNAVAILABLE,
        )
    ).all():
        unavailable[row.employee_id].append(row)

    leave: dict[str, list] = {eid: [] for eid in employee_ids}
    for row in db.scalars(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(employee_ids),
            LeaveRequest.status == LeaveStatus.APPROVED,
        )
    ).all():
        leave[row.employee_id].append(row)

    names = {employee.id: employee.employee_number or employee.id for _, _, employee in window_rows}
    for user in db.scalars(select(User).where(User.id.in_(employee_ids))).all():
        if user.full_name:
            names[user.id] = user.full_name

    ctx = {
        "intervals": intervals,
        "emp_shifts": emp_shifts,
        "unavailable": unavailable,
        "leave": leave,
        "week_hours": week_hours,
        "worked_dates": worked_dates,
    }
    conflicts: list[dict] = []
    for shift, _link, employee in window_rows:
        result = assignment_service.validate_assignment(db, shift, employee, ctx=ctx)
        for issue in result["violations"] + result["warnings"]:
            conflicts.append(
                {
                    "shift_id": shift.id,
                    "shift_date": shift.shift_date,
                    "employee_id": employee.id,
                    "employee_name": names.get(employee.id),
                    "code": issue["code"],
                    "message": issue["message"],
                    "blocking": issue["blocking"],
                }
            )
    return conflicts


def calendar_weeks(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Group shifts (with assignments) into day buckets for the calendar UI."""
    shifts = db.scalars(
        select(Shift)
        .where(
            Shift.store_id == store_id,
            Shift.shift_date >= start_date,
            Shift.shift_date <= end_date,
        )
        .order_by(Shift.shift_date, Shift.start_time)
    ).all()
    by_day: dict[date, list[dict]] = defaultdict(list)
    for shift in shifts:
        links = assignment_service.list_assignments_for_shift(db, shift.id)
        assigned = [
            {
                "assignment_id": link.id,
                "employee_id": link.employee_id,
                "status": link.status,
            }
            for link in links
            if link.status not in (AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW)
        ]
        count = len(assigned)
        by_day[shift.shift_date].append(
            {
                "shift": shift,
                "assigned_count": count,
                "coverage_status": coverage_status(shift, count),
                "assignments": assigned,
            }
        )
    days = []
    cursor = start_date
    while cursor <= end_date:
        days.append({"date": cursor, "shifts": by_day.get(cursor, [])})
        cursor += timedelta(days=1)
    return days


def _display_name(db: Session, employee: Employee) -> str:
    """Best-effort display name for an employee row."""
    from sqlalchemy import select as _select

    from app.models.user import User

    user = db.scalar(_select(User).where(User.id == employee.id))
    if user is not None and user.full_name:
        return user.full_name
    return employee.employee_number or employee.id
