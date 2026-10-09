"""Leave request routes: file, review, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
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
from app.models import Employee, LeaveRequest, User
from app.models.enums import LeaveStatus
from app.schemas.operations import LeaveDecision, LeaveRequestCreate
from app.services import leave_service

router = APIRouter(prefix="/leave", tags=["leave"])


def _resolve_employee(db: Session, employee_id: str, user: User) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, user)
    return employee


def _resolve_request(db: Session, request_id: str, user: User) -> LeaveRequest:
    req = db.get(LeaveRequest, request_id)
    if req is None:
        raise NotFoundError("Leave request not found")
    employee = db.get(Employee, req.employee_id)
    if employee is None or employee.store_id != user.store_id:
        raise NotFoundError("Leave request not found")
    if user.role.value != "manager" and req.employee_id != user.id:
        raise NotFoundError("Leave request not found")
    return req


@router.get("")
def list_leave(
    employee_id: str | None = Query(default=None),
    status: LeaveStatus | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List leave requests (employees see their own; managers see store)."""
    scope_employee = employee_id
    if current_user.role.value != "manager":
        scope_employee = current_user.id
    elif employee_id is not None:
        _resolve_employee(db, employee_id, current_user)
        scope_employee = employee_id
    rows = leave_service.list_requests(
        db, store_id=current_user.store_id,
        employee_id=scope_employee, status=status,
    )
    return success(data=jsonable_encoder(rows), message="Leave requests")


@router.post("", status_code=201)
def file_leave(
    payload: LeaveRequestCreate,
    request: Request,
    employee_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """File a leave request (managers may file on behalf of store staff)."""
    _ = request
    target_id = employee_id or current_user.id
    employee = _resolve_employee(db, target_id, current_user)
    req = leave_service.file_request(
        db,
        employee=employee,
        start_date=payload.start_date,
        end_date=payload.end_date,
        leave_type=payload.leave_type,
        reason=payload.reason,
    )
    return success(
        data=jsonable_encoder(req), message="Leave request filed", status_code=201
    )


@router.get("/{request_id}")
def read_leave(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return one leave request."""
    req = _resolve_request(db, request_id, current_user)
    return success(data=jsonable_encoder(req), message="Leave request")


@router.post("/{request_id}/decide")
def decide_leave(
    request_id: str,
    payload: LeaveDecision,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Approve or reject a leave request (approval cancels clashing shifts)."""
    _ = request
    req = _resolve_request(db, request_id, manager)
    _ = get_managed_store_id(manager)
    req = leave_service.decide_request(
        db, request=req, reviewer=manager,
        decision=payload.decision, review_note=payload.review_note,
    )
    _ = client_ip
    return success(
        data=jsonable_encoder(req), message=f"Leave {payload.decision}"
    )


@router.post("/{request_id}/cancel")
def cancel_leave(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel a pending leave request (owner or manager)."""
    req = _resolve_request(db, request_id, current_user)
    req = leave_service.cancel_request(db, request=req, cancelled_by=current_user)
    return success(data=jsonable_encoder(req), message="Leave request cancelled")
