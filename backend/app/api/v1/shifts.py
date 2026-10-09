"""Shift and assignment routes (manager scheduling workflow)."""

from __future__ import annotations

from datetime import date

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
from app.models import Employee, Shift, ShiftAssignment, User
from app.models.enums import ShiftStatus
from app.schemas.scheduling import (
    AssignmentCreate,
    AssignmentValidationResult,
    ShiftBulkCreate,
    ShiftCreate,
    ShiftResponse,
    ShiftUpdate,
)
from app.services import assignment_service, shift_service
from app.services.scheduling_service import coverage_status

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _shift_payload(db: Session, shift: Shift) -> dict:
    active = assignment_service.active_assignment_count(db, shift.id)
    rows = assignment_service.list_assignments_for_shift(db, shift.id)
    assignments = []
    for row in rows:
        emp = db.get(Employee, row.employee_id)
        user = db.get(User, row.employee_id)
        assignments.append(
            {
                "id": row.id,
                "shift_id": row.shift_id,
                "employee_id": row.employee_id,
                "employee_name": user.full_name if user else None,
                "employee_number": emp.employee_number if emp else None,
                "status": (
                    row.status.value
                    if hasattr(row.status, "value")
                    else str(row.status)
                ),
                "assigned_at": row.assigned_at,
                "is_auto_assigned": row.is_auto_assigned,
                "notes": row.notes,
            }
        )
    data = {
        "id": shift.id,
        "store_id": shift.store_id,
        "shift_date": shift.shift_date,
        "start_time": shift.start_time,
        "end_time": shift.end_time,
        "role_required": shift.role_required,
        "required_skill": shift.required_skill,
        "required_employees": shift.required_employees,
        "status": (
            shift.status.value if hasattr(shift.status, "value") else str(shift.status)
        ),
        "notes": shift.notes,
        "created_by": shift.created_by,
        "published_at": shift.published_at,
        "created_at": shift.created_at,
        "updated_at": shift.updated_at,
        "duration_hours": shift.duration_hours,
        "is_overnight": shift.is_overnight(),
        "assigned_count": active,
        "coverage_status": coverage_status(shift, active).value,
        "assignments": assignments,
    }
    return ShiftResponse.model_validate(data).model_dump(mode="json")


@router.get("")
def list_shifts(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status: ShiftStatus | None = Query(default=None),
    role: str | None = Query(default=None, max_length=80),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List shifts in the caller's store with optional filters."""
    shifts = shift_service.list_shifts(
        db,
        store_id=current_user.store_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        role=role,
    )
    if current_user.role.value != "manager":
        # Employees only ever see published (or later) shifts, never drafts.
        shifts = [s for s in shifts if s.status != ShiftStatus.DRAFT]
    return success(data=[_shift_payload(db, s) for s in shifts], message="Shifts")


@router.post("", status_code=201)
def create_shift(
    payload: ShiftCreate,
    request: Request,
    store: str | None = None,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Create a shift in the manager's store."""
    from app.models.user import Store

    _ = store
    store_row = db.get(Store, get_managed_store_id(manager))
    if store_row is None:
        raise NotFoundError("Store not found")
    shift = shift_service.create_shift(
        db,
        store=store_row,
        manager=manager,
        payload=payload,
        ip=client_ip(request),
    )
    return success(
        data=_shift_payload(db, shift), message="Shift created", status_code=201
    )


@router.post("/bulk", status_code=201)
def bulk_create_shifts(
    payload: ShiftBulkCreate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Create many shifts at once; exact duplicates are skipped."""
    from app.models.user import Store

    store_row = db.get(Store, get_managed_store_id(manager))
    if store_row is None:
        raise NotFoundError("Store not found")
    created = shift_service.bulk_create_shifts(
        db,
        store=store_row,
        manager=manager,
        payload=payload,
        ip=client_ip(request),
    )
    return success(
        data={
            "created": [_shift_payload(db, s) for s in created],
            "count": len(created),
        },
        message=f"{len(created)} shift(s) created",
        status_code=201,
    )


@router.get("/{shift_id}")
def read_shift(
    shift_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return one shift with its assignments."""
    shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=shift_id
    )
    return success(data=_shift_payload(db, shift), message="Shift")


@router.patch("/{shift_id}")
def update_shift(
    shift_id: str,
    payload: ShiftUpdate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Update a shift (cancelled shifts are immutable)."""
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=shift_id
    )
    shift = shift_service.update_shift(
        db, shift=shift, manager=manager, payload=payload, ip=client_ip(request)
    )
    return success(data=_shift_payload(db, shift), message="Shift updated")


@router.post("/{shift_id}/cancel")
def cancel_shift(
    shift_id: str,
    request: Request,
    reason: str = Query(min_length=3, max_length=500),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel a shift and release its active assignments."""
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=shift_id
    )
    shift = shift_service.cancel_shift(
        db, shift=shift, manager=manager, reason=reason, ip=client_ip(request)
    )
    return success(data=_shift_payload(db, shift), message="Shift cancelled")


@router.delete("/{shift_id}")
def delete_shift(
    shift_id: str,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Delete a draft shift that has no active assignments."""
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=shift_id
    )
    shift_service.delete_shift(db, shift=shift, manager=manager, ip=client_ip(request))
    return success(message="Shift deleted")


@router.post("/publish")
def publish_shifts(
    request: Request,
    shift_ids: list[str],
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Publish draft shifts so employees can see them."""
    published = shift_service.publish_shifts(
        db,
        store_id=get_managed_store_id(manager),
        manager=manager,
        shift_ids=shift_ids,
        ip=client_ip(request),
    )
    return success(
        data=[_shift_payload(db, s) for s in published],
        message=f"{len(published)} shift(s) published",
    )


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


@router.get("/{shift_id}/assignments")
def list_shift_assignments(
    shift_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List assignments for one shift."""
    shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=shift_id
    )
    return success(data=_shift_payload(db, shift)["assignments"], message="Assignments")


@router.post("/assignments/validate")
def validate_assignment(
    payload: AssignmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Preview assignment validation (blocking violations + warnings)."""
    shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=payload.shift_id
    )
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, current_user)
    result = assignment_service.validate_assignment(
        db, shift, employee, force=payload.force
    )
    body = AssignmentValidationResult(
        valid=result["valid"],
        violations=result["violations"],
        warnings=result["warnings"],
    )
    return success(data=body.model_dump(mode="json"), message="Validation result")


@router.post("/assignments", status_code=201)
def assign_employee(
    payload: AssignmentCreate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Assign an employee to a shift (validates the 10 assignment rules)."""
    _ = request
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=payload.shift_id
    )
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, manager)
    assignment = assignment_service.assign_employee(
        db,
        shift,
        employee,
        assigned_by=manager,
        notes=payload.notes,
        force=payload.force,
    )
    return success(
        data={
            "id": assignment.id,
            "shift_id": assignment.shift_id,
            "employee_id": assignment.employee_id,
            "status": (
                assignment.status.value
                if hasattr(assignment.status, "value")
                else str(assignment.status)
            ),
            "assigned_at": (
                assignment.assigned_at.isoformat() if assignment.assigned_at else None
            ),
            "is_auto_assigned": assignment.is_auto_assigned,
        },
        message="Employee assigned",
        status_code=201,
    )


@router.delete("/assignments/{assignment_id}")
def unassign_employee(
    assignment_id: str,
    request: Request,
    reason: str | None = Query(default=None, max_length=500),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Remove an assignment (manager only)."""
    _ = request
    assignment = db.get(ShiftAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Assignment not found")
    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=assignment.shift_id
    )
    _ = shift
    assignment = assignment_service.unassign_employee(
        db, assignment, removed_by=manager, reason=reason
    )
    return success(message="Assignment removed")


@router.post("/assignments/{assignment_id}/confirm")
def confirm_assignment(
    assignment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Let the assigned employee confirm their shift."""
    assignment = db.get(ShiftAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Assignment not found")
    if (
        current_user.role.value != "manager"
        and assignment.employee_id != current_user.id
    ):
        raise NotFoundError("Assignment not found")
    assignment = assignment_service.confirm_assignment(db, assignment)
    return success(message="Assignment confirmed")


@router.get("/{shift_id}/eligible")
def eligible_employees(
    shift_id: str,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Rank active store employees by eligibility for one shift."""
    from sqlalchemy import select

    from app.models.enums import EmployeeStatus

    shift = shift_service.get_shift(
        db, store_id=get_managed_store_id(manager), shift_id=shift_id
    )
    candidates = list(
        db.scalars(
            select(Employee).where(
                Employee.store_id == shift.store_id,
                Employee.status == EmployeeStatus.ACTIVE,
            )
        ).all()
    )
    ranked = assignment_service.find_eligible_employees(db, shift, candidates)
    return success(data=ranked, message="Eligible employees")
