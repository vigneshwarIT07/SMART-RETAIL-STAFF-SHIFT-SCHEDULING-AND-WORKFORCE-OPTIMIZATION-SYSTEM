"""Availability routes: employees manage their weekly availability."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import (
    assert_employee_visible,
    get_current_user,
    require_manager,
)
from app.core.errors import NotFoundError, success
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models import Employee, User
from app.schemas.operations import (
    AvailabilityCreate,
    AvailabilityResponse,
    AvailabilityUpdate,
)
from app.services import availability_service

router = APIRouter(prefix="/availability", tags=["availability"])


def _payload(row) -> dict:
    return AvailabilityResponse.model_validate(row).model_dump(mode="json")


def _resolve_employee(
    db: Session, employee_id: str, current_user: User
) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, current_user)
    return employee


@router.get("/employees/{employee_id}")
def list_availability(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List one employee's availability entries."""
    employee = _resolve_employee(db, employee_id, current_user)
    rows = availability_service.list_availability(db, employee=employee, user=current_user)
    return success(data=[_payload(r) for r in rows], message="Availability")


@router.post("/employees/{employee_id}", status_code=201)
def create_availability(
    employee_id: str,
    payload: AvailabilityCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Add an availability entry for an employee."""
    _ = request
    employee = _resolve_employee(db, employee_id, current_user)
    row = availability_service.create_availability(
        db, employee=employee, user=current_user, payload=payload
    )
    return success(data=_payload(row), message="Availability added", status_code=201)


@router.get("/employees/{employee_id}/mine")
def read_own_availability(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Alias kept for older clients: same as listing the employee's entries."""
    return list_availability(employee_id, current_user, db)


@router.patch("/{row_id}")
def update_availability(
    row_id: str,
    payload: AvailabilityUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Update one availability entry."""
    _ = request
    row = availability_service.get_row(db, row_id=row_id)
    employee = _resolve_employee(db, row.employee_id, current_user)
    row = availability_service.update_availability(
        db, row=row, employee=employee, user=current_user, payload=payload
    )
    return success(data=_payload(row), message="Availability updated")


@router.delete("/{row_id}")
def delete_availability(
    row_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Delete one availability entry."""
    _ = request
    row = availability_service.get_row(db, row_id=row_id)
    employee = _resolve_employee(db, row.employee_id, current_user)
    availability_service.delete_availability(
        db, row=row, employee=employee, user=current_user
    )
    return success(message="Availability deleted")


@router.get("/review")
def review_all(
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Manager view: every availability entry in the store."""
    from sqlalchemy import select

    from app.models import Availability

    _ = db
    rows = db.scalars(
        select(Availability)
        .join(Employee, Availability.employee_id == Employee.id)
        .where(Employee.store_id == current_user.store_id)
        .order_by(Availability.weekday)
    ).all()
    _ = client_ip
    return success(data=[_payload(r) for r in rows], message="Availability")
