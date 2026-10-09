"""Availability CRUD service.

An availability row declares when an employee can (or cannot) work. Rows are
owned by a single employee; managers may manage rows for anyone in their
store, employees only their own.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Availability, Employee, User
from app.models.enums import UserRole
from app.schemas.operations import AvailabilityCreate, AvailabilityUpdate
from app.services import audit_service
from app.models.enums import AuditAction


def _scope_check(employee: Employee, user: User) -> None:
    if employee.store_id != user.store_id:
        raise NotFoundError("Employee not found")
    if user.role != UserRole.MANAGER and employee.id != user.id:
        raise NotFoundError("Employee not found")


def list_availability(
    db: Session, *, employee: Employee, user: User
) -> list[Availability]:
    """Return all availability rows for an employee (newest weekday first)."""
    _scope_check(employee, user)
    return list(
        db.scalars(
            select(Availability)
            .where(Availability.employee_id == employee.id)
            .order_by(Availability.weekday, Availability.start_time)
        ).all()
    )


def create_availability(
    db: Session,
    *,
    employee: Employee,
    user: User,
    payload: AvailabilityCreate,
) -> Availability:
    """Create one availability row for an employee."""
    _scope_check(employee, user)
    row = Availability(
        employee_id=employee.id,
        weekday=payload.weekday,
        start_time=payload.start_time,
        end_time=payload.end_time,
        availability_type=payload.availability_type,
        note=payload.note,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "An availability entry already exists for that weekday and start time"
        ) from exc
    audit_service.log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="availability",
        entity_id=row.id,
        user_id=user.id,
        store_id=employee.store_id,
        details={"employee_id": employee.id, "weekday": payload.weekday},
    )
    return row


def get_row(db: Session, *, row_id: str) -> Availability:
    """Fetch an availability row or raise 404."""
    row = db.get(Availability, row_id)
    if row is None:
        raise NotFoundError("Availability entry not found")
    return row


def update_availability(
    db: Session,
    *,
    row: Availability,
    employee: Employee,
    user: User,
    payload: AvailabilityUpdate,
) -> Availability:
    """Patch an availability row."""
    _scope_check(employee, user)
    if row.employee_id != employee.id:
        raise NotFoundError("Availability entry not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="availability",
        entity_id=row.id,
        user_id=user.id,
        store_id=employee.store_id,
    )
    return row


def delete_availability(
    db: Session, *, row: Availability, employee: Employee, user: User
) -> None:
    """Delete an availability row."""
    _scope_check(employee, user)
    if row.employee_id != employee.id:
        raise NotFoundError("Availability entry not found")
    audit_service.log_action(
        db,
        action=AuditAction.DELETE,
        entity_type="availability",
        entity_id=row.id,
        user_id=user.id,
        store_id=employee.store_id,
    )
    db.delete(row)
    db.flush()
