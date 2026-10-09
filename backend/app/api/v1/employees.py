"""Employee directory routes (manager-provisioned accounts only).

There is no public self-registration: managers create employee accounts from
this screen, which creates the linked ``users`` + ``employees`` rows together.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_employee,
    get_current_user,
    get_managed_store_id,
    paginate,
    require_manager,
)
from app.core.errors import success
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models import Employee, User
from app.schemas.common import PageMeta, PaginatedResponse
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services import employee_service

router = APIRouter(prefix="/employees", tags=["employees"])


def _payload(user: User, employee: Employee) -> dict:
    return EmployeeResponse.model_validate(
        employee_service.employee_payload(user, employee)
    ).model_dump(mode="json")


@router.get("")
def list_employees(
    search: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """List employees in the manager's store with search + pagination."""
    store_id = get_managed_store_id(manager)
    offset, limit = paginate(page, page_size)
    rows, total = employee_service.list_employees(
        db, store_id=store_id, search=search, status=status, offset=offset, limit=limit
    )
    items = [_payload(u, e) for u, e in rows]
    pages = max(1, -(-total // limit))
    body = PaginatedResponse[EmployeeResponse](
        items=[EmployeeResponse(**i) for i in items],
        meta=PageMeta(page=page, page_size=limit, total=total, pages=pages),
    )
    return success(data=body.model_dump(mode="json"), message="Employees")


@router.post("", status_code=201)
def create_employee(
    payload: EmployeeCreate,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Create an employee account (linked user + employee rows)."""
    store_id = get_managed_store_id(manager)
    user, employee = employee_service.create_employee(
        db, store_id=store_id, payload=payload, created_by=manager,
        ip=client_ip(request),
    )
    return success(
        data=_payload(user, employee), message="Employee created", status_code=201
    )


@router.get("/me")
def read_own_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the caller's own employee profile."""
    employee = db.get(Employee, current_user.id)
    if employee is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("No employee record is linked to this account")
    user = db.get(User, employee.id)
    if user is None:
        from app.core.errors import NotFoundError as _NF

        raise _NF("No employee record is linked to this account")
    return success(data=_payload(user, employee), message="Employee profile")


@router.get("/{employee_id}")
def read_employee(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return one employee (managers: anyone in store; staff: self only)."""
    from app.core.deps import assert_employee_visible

    employee = db.get(Employee, employee_id)
    if employee is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, current_user)
    user = db.get(User, employee.id)
    if user is None:
        from app.core.errors import NotFoundError as _NF2

        raise _NF2("Employee not found")
    return success(data=_payload(user, employee), message="Employee profile")


@router.patch("/{employee_id}")
def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Update an employee. Only managers may change employment status."""
    from app.core.deps import assert_employee_visible

    employee = db.get(Employee, employee_id)
    if employee is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Employee not found")
    assert_employee_visible(employee, current_user)
    user = db.get(User, employee.id)
    if user is None:
        from app.core.errors import NotFoundError as _NF3

        raise _NF3("Employee not found")
    user, employee = employee_service.update_employee(
        db, user=user, employee=employee, payload=payload,
        updated_by=current_user, ip=client_ip(request),
    )
    return success(data=_payload(user, employee), message="Employee updated")


@router.post("/{employee_id}/deactivate")
def deactivate_employee(
    employee_id: str,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Deactivate an employee account (manager only)."""
    user, employee = employee_service.get_employee(
        db, store_id=get_managed_store_id(manager), employee_id=employee_id
    )
    user, employee = employee_service.deactivate_employee(
        db, user=user, employee=employee, deactivated_by=manager,
        ip=client_ip(request),
    )
    return success(data=_payload(user, employee), message="Employee deactivated")

