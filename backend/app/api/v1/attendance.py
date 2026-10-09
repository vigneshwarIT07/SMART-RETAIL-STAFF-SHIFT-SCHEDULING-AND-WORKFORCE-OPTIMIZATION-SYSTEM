"""Attendance routes: clock-in/out, absence marking, corrections, review."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import (
    assert_employee_visible,
    get_current_user,
    get_managed_store_id,
    require_manager,
)
from app.core.errors import NotFoundError, success
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models import Employee, User
from app.models.enums import AttendanceStatus
from app.schemas.operations import (
    AttendanceCorrectionRequest,
    AttendanceResponse,
    AttendanceSummary,
    MissingClockOutRow,
)
from app.services import attendance_service, shift_service

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _payload(record) -> dict:
    return AttendanceResponse.model_validate(record).model_dump(mode="json")


def _resolve_shift_employee(
    db: Session, shift_id: str, employee_id: str, current_user: User
):
    shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=shift_id
    )
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, current_user)
    return shift, employee


@router.get("")
def list_attendance(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    status: AttendanceStatus | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List attendance records (employees see their own; managers see store)."""
    scope_employee: str | None = employee_id
    if current_user.role.value != "manager":
        scope_employee = current_user.id
    elif employee_id is not None:
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        assert_employee_visible(employee, current_user)
    records = attendance_service.list_records(
        db,
        store_id=current_user.store_id,
        start=start,
        end=end,
        employee_id=scope_employee,
        status=status,
    )
    return success(data=[_payload(r) for r in records], message="Attendance")


@router.post("/clock-in")
def clock_in(
    shift_id: str,
    employee_id: str,
    request: Request,
    at: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record a clock-in (server timestamp unless an explicit one is given)."""
    _ = request
    shift, employee = _resolve_shift_employee(db, shift_id, employee_id, current_user)
    result = attendance_service.clock_in(
        db, shift=shift, employee=employee, recorded_by=current_user, at=at
    )
    record = result.get("attendance", result.get("record")) if isinstance(result, dict) else result
    return success(data=_payload(record), message="Clocked in")


@router.post("/clock-out")
def clock_out(
    shift_id: str,
    employee_id: str,
    request: Request,
    at: datetime | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record a clock-out (server computes worked minutes)."""
    _ = request
    shift, employee = _resolve_shift_employee(db, shift_id, employee_id, current_user)
    result = attendance_service.clock_out(
        db, shift=shift, employee=employee, recorded_by=current_user, at=at
    )
    record = result.get("attendance", result.get("record")) if isinstance(result, dict) else result
    return success(data=_payload(record), message="Clocked out")


@router.post("/mark-absent")
def mark_absent(
    shift_id: str,
    employee_id: str,
    request: Request,
    notes: str | None = Query(default=None, max_length=500),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Mark an assignment absent (manager only; refused before shift end)."""
    _ = request
    shift, employee = _resolve_shift_employee(
        db, shift_id, employee_id, manager
    )
    record = attendance_service.mark_absent(
        db, shift=shift, employee=employee, marked_by=manager, notes=notes
    )
    return success(data=_payload(record), message="Marked absent")


@router.get("/missing-clockouts")
def missing_clockouts(
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Review queue: clocked-in records with no clock-out past the grace time."""
    from app.core.config import settings

    rows = attendance_service.missing_clockouts(
        db,
        store_id=get_managed_store_id(manager),
        older_than_minutes=settings.missing_clockout_grace_minutes,
    )
    body = [MissingClockOutRow(**r).model_dump(mode="json") for r in rows]
    return success(data=body, message="Missing clock-outs")


@router.get("/summary")
def attendance_summary(
    start: date = Query(),
    end: date = Query(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Attendance roll-up for a date range."""
    data = attendance_service.summarize(
        db, store_id=current_user.store_id, start=start, end=end
    )
    body = AttendanceSummary(**data).model_dump(mode="json")
    return success(data=body, message="Attendance summary")


@router.post("/{record_id}/correct")
def correct_record(
    record_id: str,
    payload: AttendanceCorrectionRequest,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Correct a record (manager only; requires reason; snapshots + audits)."""
    from app.models import Attendance

    _ = request
    record = db.get(Attendance, record_id)
    if record is None:
        raise NotFoundError("Attendance record not found")
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=record.shift_id
    )
    _ = shift
    record = attendance_service.correct_record(
        db,
        record=record,
        manager=manager,
        clock_in=payload.clock_in,
        clock_out=payload.clock_out,
        status=payload.status,
        reason=payload.reason,
    )
    _ = client_ip
    return success(data=_payload(record), message="Attendance corrected")
