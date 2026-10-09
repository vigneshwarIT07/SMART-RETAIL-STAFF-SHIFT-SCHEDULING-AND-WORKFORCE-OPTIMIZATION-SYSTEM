"""Reporting service: working hours, leave breakdown, store summary, CSV export.

All figures derive from live database rows — no mock data, no invented
numbers.  Hours figures reuse the scheduling service so reports and the
dashboard always agree.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AssignmentStatus,
    Attendance,
    AttendanceStatus,
    Employee,
    LeaveRequest,
    LeaveStatus,
    Shift,
    ShiftAssignment,
    ShiftStatus,
)

from . import attendance_service, scheduling_service


def working_hours_report(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Scheduled vs actually-worked hours per employee for the window."""
    employees = db.scalars(select(Employee).where(Employee.store_id == store_id)).all()
    rows: list[dict] = []
    for employee in employees:
        shift_stmt = (
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
        shifts = db.scalars(shift_stmt).all()
        scheduled = sum(s.duration_hours for s in shifts)

        worked_minutes = db.scalar(
            select(func.coalesce(func.sum(Attendance.worked_minutes), 0)).where(
                Attendance.employee_id == employee.id,
                Attendance.attendance_date >= start_date,
                Attendance.attendance_date <= end_date,
                Attendance.worked_minutes.is_not(None),
            )
        )
        worked = round((worked_minutes or 0) / 60, 2)

        late_count = db.scalar(
            select(func.count()).where(
                Attendance.employee_id == employee.id,
                Attendance.attendance_date >= start_date,
                Attendance.attendance_date <= end_date,
                Attendance.status == AttendanceStatus.LATE,
            )
        )
        absent_count = db.scalar(
            select(func.count()).where(
                Attendance.employee_id == employee.id,
                Attendance.attendance_date >= start_date,
                Attendance.attendance_date <= end_date,
                Attendance.status == AttendanceStatus.ABSENT,
            )
        )
        rows.append(
            {
                "employee_id": employee.id,
                "employee_name": scheduling_service._display_name(db, employee),
                "employee_number": employee.employee_number,
                "scheduled_hours": round(scheduled, 2),
                "worked_hours": worked,
                "late_count": late_count or 0,
                "absent_count": absent_count or 0,
            }
        )
    rows.sort(key=lambda row: row["employee_name"].lower())
    return rows


def leave_breakdown(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Approved leave days per employee per leave type in the window."""
    stmt = (
        select(LeaveRequest, Employee)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(
            Employee.store_id == store_id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    totals: dict[tuple[str, str], dict] = {}
    for leave, employee in db.execute(stmt):
        overlap_start = max(leave.start_date, start_date)
        overlap_end = min(leave.end_date, end_date)
        days = (overlap_end - overlap_start).days + 1
        key = (employee.id, leave.leave_type.value)
        if key not in totals:
            totals[key] = {
                "employee_id": employee.id,
                "employee_name": scheduling_service._display_name(db, employee),
                "leave_type": leave.leave_type.value,
                "days": 0,
            }
        totals[key]["days"] += days
    rows = list(totals.values())
    rows.sort(key=lambda row: (row["employee_name"].lower(), row["leave_type"]))
    return rows


def store_summary(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
) -> dict:
    """One compact summary object for the manager dashboard and reports page."""
    employees = db.scalars(select(Employee).where(Employee.store_id == store_id)).all()
    active_employees = [emp for emp in employees if emp.is_active]
    total_shifts = db.scalar(
        select(func.count()).where(
            Shift.store_id == store_id,
            Shift.shift_date >= start_date,
            Shift.shift_date <= end_date,
            Shift.status != ShiftStatus.CANCELLED,
        )
    )
    coverage_rows = scheduling_service.week_coverage(
        db, store_id=store_id, start_date=start_date, end_date=end_date
    )
    coverage = scheduling_service.coverage_summary(coverage_rows)

    attendance_counts: dict[str, int] = {}
    for status in AttendanceStatus:
        count = db.scalar(
            select(func.count())
            .select_from(Attendance)
            .join(Employee, Employee.id == Attendance.employee_id)
            .where(
                Employee.store_id == store_id,
                Attendance.attendance_date >= start_date,
                Attendance.attendance_date <= end_date,
                Attendance.status == status,
            )
        )
        attendance_counts[status.value.lower()] = count or 0

    pending_leave = db.scalar(
        select(func.count())
        .select_from(LeaveRequest)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(
            Employee.store_id == store_id,
            LeaveRequest.status == LeaveStatus.PENDING,
        )
    )
    from app.models import ShiftSwapRequest, SwapStatus

    pending_swaps = db.scalar(
        select(func.count())
        .select_from(ShiftSwapRequest)
        .join(Employee, Employee.id == ShiftSwapRequest.requester_id)
        .where(
            Employee.store_id == store_id,
            ShiftSwapRequest.status == SwapStatus.PENDING,
        )
    )
    missing_clockouts = attendance_service.missing_clockouts(db, store_id=store_id)
    return {
        "employee_count": len(active_employees),
        "total_employees": len(employees),
        "total_shifts": total_shifts or 0,
        "coverage": coverage,
        "attendance": attendance_counts,
        "pending_leave": pending_leave or 0,
        "pending_swaps": pending_swaps or 0,
        "missing_clockouts": len(missing_clockouts),
    }


def dashboard_metrics(
    db: Session,
    *,
    store_id: str,
    today: date,
) -> dict:
    """Eight database-derived metrics for the manager dashboard.

    Keys: today_shifts, today_unassigned, week_understaffed, active_employees,
    pending_leave, pending_swaps, missing_clockouts, week_overtime_flags.
    Every value comes from live queries — nothing is mocked.
    """
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    today_rows = scheduling_service.week_coverage(
        db, store_id=store_id, start_date=today, end_date=today
    )
    week_rows = scheduling_service.week_coverage(
        db, store_id=store_id, start_date=week_start, end_date=week_end
    )
    week_hours = scheduling_service.weekly_hours_report(
        db, store_id=store_id, week_start=week_start
    )
    summary = store_summary(
        db, store_id=store_id, start_date=week_start, end_date=week_end
    )
    return {
        "today_shifts": len(today_rows),
        "today_unassigned": sum(
            1 for row in today_rows if row["coverage_status"].value == "unassigned"
        ),
        "week_understaffed": sum(
            1 for row in week_rows if row["coverage_status"].value == "understaffed"
        ),
        "active_employees": summary["employee_count"],
        "pending_leave": summary["pending_leave"],
        "pending_swaps": summary["pending_swaps"],
        "missing_clockouts": summary["missing_clockouts"],
        "week_overtime_flags": sum(1 for row in week_hours if row["overtime_warning"]),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
    }


def rows_to_csv(rows: Sequence[dict], fieldnames: Sequence[str]) -> str:
    """Serialise report rows to CSV text (UTF-8, header row included)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def build_export(
    kind: str,
    rows: Sequence[dict],
) -> dict:
    """Wrap report rows in a CSV export payload (filename + content type)."""
    specs: dict[str, tuple[str, list[str]]] = {
        "working-hours": (
            "working-hours.csv",
            [
                "employee_id",
                "employee_name",
                "employee_number",
                "scheduled_hours",
                "worked_hours",
                "late_count",
                "absent_count",
            ],
        ),
        "weekly-hours": (
            "weekly-hours.csv",
            [
                "employee_id",
                "employee_name",
                "employee_number",
                "scheduled_hours",
                "contract_hours",
                "overtime_warning",
            ],
        ),
        "fairness": (
            "fairness.csv",
            ["employee_id", "employee_name", "shift_count", "total_hours"],
        ),
        "coverage": (
            "coverage.csv",
            [
                "shift_id",
                "shift_date",
                "start_time",
                "end_time",
                "role_required",
                "required_employees",
                "assigned_count",
                "coverage_status",
                "shift_status",
            ],
        ),
        "leave": (
            "leave.csv",
            ["employee_id", "employee_name", "leave_type", "days"],
        ),
        "attendance": (
            "attendance.csv",
            [
                "id",
                "attendance_date",
                "employee_id",
                "shift_id",
                "clock_in",
                "clock_out",
                "status",
                "worked_minutes",
                "late_minutes",
            ],
        ),
    }
    if kind not in specs:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Unknown export kind '{kind}'.")
    filename, fieldnames = specs[kind]
    serialised = [_serialise_row(row, fieldnames) for row in rows]
    return {
        "filename": filename,
        "content_type": "text/csv",
        "rows": serialised,
        "csv_text": rows_to_csv(serialised, fieldnames),
    }


def _serialise_row(row: dict, fieldnames: Sequence[str]) -> dict:
    """Convert enum/date/time values to plain strings for CSV output."""
    out: dict[str, Any] = {}
    for key in fieldnames:
        value = row.get(key)
        if value is not None and hasattr(value, "value"):
            value = value.value  # type: ignore[union-attr]
        out[key] = "" if value is None else str(value)
    return out


def _unused_iterable() -> Iterable[Any]:  # pragma: no cover - typing aid
    return iter(())
