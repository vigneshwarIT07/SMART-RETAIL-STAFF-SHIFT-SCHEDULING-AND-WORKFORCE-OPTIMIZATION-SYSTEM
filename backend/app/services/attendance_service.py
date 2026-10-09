"""Attendance: clock-in/out, lateness, corrections and review queues.

Policy (explicit so reviewers can audit it)
-------------------------------------------
* Lateness is server-computed: ``late_minutes = max(0, clock_in - shift_start
  - grace)`` where ``grace`` is ``settings.attendance_grace_minutes``.
* ``worked_minutes`` is server-computed from clock-in/out; clients can never
  submit hours directly.
* Nobody is marked ABSENT automatically before the shift ends.  Absence is
  only ever written by an explicit manager action or by the
  end-of-day review after the shift end plus grace has passed.
* Records with a clock-in but no clock-out past
  ``settings.missing_clockout_grace_minutes`` are surfaced by
  :func:`missing_clockouts` for manager review — they are never silently
  closed.
* Manager corrections require a reason, record the manager identity plus
  before/after snapshots in ``attendance_corrections``, and are audit
  logged.  Employees cannot edit their own historical timestamps.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Attendance,
    AttendanceCorrection,
    AttendanceStatus,
    AuditAction,
    Employee,
    Shift,
    ShiftStatus,
    User,
)
from app.models.user import Store

from . import audit_service, shift_service


def _store_for(db: Session, shift: Shift) -> Store | None:
    return db.scalar(select(Store).where(Store.id == shift.store_id))


def _interval(db: Session, shift: Shift) -> tuple[datetime, datetime]:
    store = _store_for(db, shift)
    if store is None:  # pragma: no cover - corrupt data guard
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = datetime.combine(shift.shift_date, shift.start_time, tzinfo=tz)
        end = datetime.combine(shift.shift_date, shift.end_time, tzinfo=tz)
        if shift.end_time <= shift.start_time:
            end += timedelta(days=1)
        return start, end
    return shift_service.shift_interval(store, shift)


def get_or_create_record(
    db: Session, *, shift: Shift, employee: Employee, recorded_by: User
) -> Attendance:
    """Fetch the attendance row for a shift+employee, creating it if needed."""
    record = db.scalar(
        select(Attendance).where(
            Attendance.shift_id == shift.id,
            Attendance.employee_id == employee.id,
        )
    )
    if record is None:
        record = Attendance(
            shift_id=shift.id,
            employee_id=employee.id,
            attendance_date=shift.shift_date,
            status=AttendanceStatus.INCOMPLETE,
            worked_minutes=0,
            late_minutes=0,
            recorded_by=recorded_by.id,
        )
        db.add(record)
        db.flush()
    return record


def clock_in(
    db: Session,
    *,
    shift: Shift,
    employee: Employee,
    recorded_by: User,
    at: datetime | None = None,
) -> dict:
    """Record clock-in; computes lateness server-side.

    Raises ``ConflictError`` when the employee already clocked in.
    """
    from app.core.errors import ConflictError

    now = at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    record = get_or_create_record(
        db, shift=shift, employee=employee, recorded_by=recorded_by
    )
    if record.clock_in is not None:
        raise ConflictError("Already clocked in for this shift.")

    shift_start, _shift_end = _interval(db, shift)
    grace = timedelta(minutes=settings.attendance_grace_minutes)
    late = max(0, int((now - (shift_start + grace)).total_seconds() // 60))
    record.clock_in = now
    record.late_minutes = late
    record.status = AttendanceStatus.LATE if late > 0 else AttendanceStatus.PRESENT
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="attendance",
        entity_id=record.id,
        user_id=recorded_by.id,
        store_id=shift.store_id,
        details={"event": "clock_in", "late_minutes": late},
    )
    db.flush()
    return {"attendance": record, "late_minutes": late, "shift_start": shift_start}


def clock_out(
    db: Session,
    *,
    shift: Shift,
    employee: Employee,
    recorded_by: User,
    at: datetime | None = None,
) -> dict:
    """Record clock-out; computes worked minutes server-side."""
    from app.core.errors import ConflictError

    now = at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    record = get_or_create_record(
        db, shift=shift, employee=employee, recorded_by=recorded_by
    )
    if record.clock_in is None:
        raise ConflictError("Cannot clock out before clocking in.")
    if record.clock_out is not None:
        raise ConflictError("Already clocked out for this shift.")
    if now <= record.clock_in:
        raise ConflictError("Clock-out must be later than clock-in.")

    record.clock_out = now
    record.worked_minutes = int((now - record.clock_in).total_seconds() // 60)
    if record.status == AttendanceStatus.INCOMPLETE:
        record.status = (
            AttendanceStatus.LATE
            if record.late_minutes > 0
            else AttendanceStatus.PRESENT
        )
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="attendance",
        entity_id=record.id,
        user_id=recorded_by.id,
        store_id=shift.store_id,
        details={"event": "clock_out", "worked_minutes": record.worked_minutes},
    )
    db.flush()
    return {"attendance": record, "worked_minutes": record.worked_minutes}


def mark_absent(
    db: Session,
    *,
    shift: Shift,
    employee: Employee,
    marked_by: User,
    notes: str | None = None,
) -> Attendance:
    """Explicit manager action marking an employee absent.

    Refuses to mark absence before the shift end (plus grace) has passed —
    the policy forbids pre-emptive absence.
    """
    from app.core.errors import ConflictError

    _start, shift_end = _interval(db, shift)
    horizon = shift_end + timedelta(minutes=settings.attendance_grace_minutes)
    if datetime.now(UTC) < horizon:
        raise ConflictError(
            "Shift has not ended yet; absence cannot be recorded early."
        )
    record = get_or_create_record(
        db, shift=shift, employee=employee, recorded_by=marked_by
    )
    if record.clock_in is not None:
        raise ConflictError("Employee clocked in; correct the record instead.")
    record.status = AttendanceStatus.ABSENT
    record.notes = notes
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="attendance",
        entity_id=record.id,
        user_id=marked_by.id,
        store_id=shift.store_id,
        details={"event": "mark_absent"},
    )
    db.flush()
    return record


def correct_record(
    db: Session,
    *,
    record: Attendance,
    manager: User,
    clock_in: datetime | None = None,
    clock_out: datetime | None = None,
    status: AttendanceStatus | None = None,
    reason: str,
) -> Attendance:
    """Manager correction with mandatory reason and before/after snapshot."""
    snapshot = AttendanceCorrection(
        attendance_id=record.id,
        manager_id=manager.id,
        reason=reason,
        previous_clock_in=record.clock_in,
        previous_clock_out=record.clock_out,
        previous_status=record.status,
        new_clock_in=clock_in if clock_in is not None else record.clock_in,
        new_clock_out=clock_out if clock_out is not None else record.clock_out,
        new_status=status if status is not None else record.status,
    )
    db.add(snapshot)
    if clock_in is not None:
        record.clock_in = clock_in
    if clock_out is not None:
        record.clock_out = clock_out
        if record.clock_in is not None and clock_out > record.clock_in:
            record.worked_minutes = int(
                (clock_out - record.clock_in).total_seconds() // 60
            )
    if status is not None:
        record.status = status
    record.was_corrected = True
    record.correction_reason = reason
    record.corrected_by = manager.id
    record.corrected_at = datetime.now(UTC)
    db.flush()
    shift = db.scalar(select(Shift).where(Shift.id == record.shift_id))
    audit_service.log_action(
        db,
        action=AuditAction.CORRECTION,
        entity_type="attendance",
        entity_id=record.id,
        user_id=manager.id,
        store_id=shift.store_id if shift else manager.store_id,
        details={"reason": reason},
    )
    db.flush()
    return record


def missing_clockouts(
    db: Session,
    *,
    store_id: str,
    older_than_minutes: int | None = None,
) -> list[dict]:
    """Records clocked in but never out, past the review grace period."""

    cutoff_minutes = (
        older_than_minutes
        if older_than_minutes is not None
        else settings.missing_clockout_grace_minutes
    )
    horizon = datetime.now(UTC) - timedelta(minutes=cutoff_minutes)
    stmt = (
        select(Attendance, Shift)
        .join(Shift, Shift.id == Attendance.shift_id)
        .where(
            Shift.store_id == store_id,
            Attendance.clock_in.is_not(None),
            Attendance.clock_out.is_(None),
            Attendance.clock_in < horizon,
        )
        .order_by(Attendance.clock_in)
    )
    rows: list[dict] = []
    for record, shift in db.execute(stmt):
        user = db.scalar(_select_user(record.employee_id))
        now = datetime.now(UTC)
        clock_in = record.clock_in
        if clock_in is not None and clock_in.tzinfo is None:
            clock_in = clock_in.replace(tzinfo=UTC)
        rows.append(
            {
                "attendance_id": record.id,
                "employee_id": record.employee_id,
                "employee_name": user.full_name if user else None,
                "shift_id": shift.id,
                "shift_date": shift.shift_date,
                "clock_in": record.clock_in,
                "hours_since_clock_in": (
                    round((now - clock_in).total_seconds() / 3600, 1)
                    if clock_in
                    else 0.0
                ),
            }
        )
    return rows


def _select_user(user_id: str):  # small helper keeps imports local
    from app.models.user import User

    return select(User).where(User.id == user_id)


def summarize(
    db: Session,
    *,
    store_id: str,
    start: date,
    end: date,
) -> dict:
    """Attendance roll-up for a store and date window."""
    stmt = (
        select(
            Attendance.status,
            func.count(),
            func.coalesce(func.sum(Attendance.worked_minutes), 0),
            func.coalesce(func.avg(Attendance.late_minutes), 0),
        )
        .join(Shift, Shift.id == Attendance.shift_id)
        .where(
            Shift.store_id == store_id,
            Attendance.attendance_date >= start,
            Attendance.attendance_date <= end,
        )
        .group_by(Attendance.status)
    )
    counts = {
        AttendanceStatus.PRESENT: 0,
        AttendanceStatus.LATE: 0,
        AttendanceStatus.ABSENT: 0,
        AttendanceStatus.INCOMPLETE: 0,
        AttendanceStatus.EXCUSED: 0,
    }
    total_minutes = 0
    late_total = 0.0
    late_rows = 0
    total_records = 0
    for status, count, minutes, avg_late in db.execute(stmt):
        counts[status] = int(count or 0)
        total_records += int(count or 0)
        total_minutes += int(minutes or 0)
        if status == AttendanceStatus.LATE:
            late_total = float(avg_late or 0)
            late_rows = int(count or 0)
    _ = late_rows
    return {
        "period_start": start,
        "period_end": end,
        "total_records": total_records,
        "present": counts[AttendanceStatus.PRESENT],
        "late": counts[AttendanceStatus.LATE],
        "absent": counts[AttendanceStatus.ABSENT],
        "incomplete": counts[AttendanceStatus.INCOMPLETE],
        "excused": counts[AttendanceStatus.EXCUSED],
        "total_worked_hours": round(total_minutes / 60, 2),
        "average_late_minutes": round(late_total, 1),
    }


def list_records(
    db: Session,
    *,
    store_id: str,
    start: date | None = None,
    end: date | None = None,
    employee_id: str | None = None,
    status: AttendanceStatus | None = None,
) -> Sequence[Attendance]:
    """Filtered attendance records for a store."""
    stmt = (
        select(Attendance)
        .join(Shift, Shift.id == Attendance.shift_id)
        .where(Shift.store_id == store_id)
        .order_by(Attendance.attendance_date.desc(), Attendance.clock_in.desc())
    )
    if start is not None:
        stmt = stmt.where(Attendance.attendance_date >= start)
    if end is not None:
        stmt = stmt.where(Attendance.attendance_date <= end)
    if employee_id is not None:
        stmt = stmt.where(Attendance.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(Attendance.status == status)
    # Exclude cancelled shifts from operational views.
    stmt = stmt.where(Shift.status != ShiftStatus.CANCELLED)
    return db.scalars(stmt).all()
