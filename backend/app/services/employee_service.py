"""Employee directory: provisioning, listing, updates and deactivation.

Managers provision employee accounts (linked ``users`` + ``employees`` rows
created together).  Employees can read their own profile but cannot change
role, store, status or history through this module.
"""

from __future__ import annotations

import secrets
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import AuditAction, Employee, User, UserRole
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

from . import audit_service


def _generate_employee_number(db: Session) -> str:
    """Generate a unique ``EMP-XXXX`` number with a random suffix."""
    for _ in range(20):
        candidate = f"EMP-{secrets.randbelow(9000) + 1000}"
        exists = db.scalar(
            select(Employee).where(Employee.employee_number == candidate)
        )
        if exists is None:
            return candidate
    raise ConflictError("Could not generate a unique employee number")


def employee_payload(user: User, employee: Employee) -> dict:
    """Flattened API representation (user fields + employee fields)."""
    return {
        "id": employee.id,
        "employee_number": employee.employee_number,
        "store_id": employee.store_id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": employee.phone,
        "address": employee.address,
        "date_of_birth": employee.date_of_birth,
        "hire_date": employee.hire_date,
        "skill_level": employee.skill_level,
        "skills": employee.skills or [],
        "contract_weekly_hours": employee.contract_weekly_hours,
        "hourly_rate": employee.hourly_rate,
        "is_keyholder": employee.is_keyholder,
        "status": employee.status,
        "is_active": employee.is_active,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }


def create_employee(
    db: Session,
    *,
    store_id: str,
    payload: EmployeeCreate,
    created_by: User,
    ip: str | None = None,
) -> tuple[User, Employee]:
    """Provision a login + employee record together (manager only)."""
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise ConflictError("An account with this email already exists")
    number = payload.employee_number or _generate_employee_number(db)
    if payload.employee_number:
        clash = db.scalar(
            select(Employee).where(Employee.employee_number == payload.employee_number)
        )
        if clash is not None:
            raise ConflictError("This employee number is already in use")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.EMPLOYEE,
        store_id=store_id,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("An account with this email already exists") from exc
    employee = Employee(
        id=user.id,
        employee_number=number,
        store_id=store_id,
        phone=payload.phone,
        address=payload.address,
        date_of_birth=payload.date_of_birth,
        hire_date=payload.hire_date or date.today(),
        skill_level=payload.skill_level,
        skills=list(payload.skills or []),
        contract_weekly_hours=payload.contract_weekly_hours,
        hourly_rate=payload.hourly_rate,
        is_keyholder=payload.is_keyholder,
    )
    db.add(employee)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Employee record conflicts with an existing one") from exc
    audit_service.log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="employee",
        entity_id=employee.id,
        user_id=created_by.id,
        store_id=store_id,
        details={"employee_number": number, "email": user.email},
        ip_address=ip,
    )
    db.flush()
    return user, employee


def get_employee(
    db: Session, *, store_id: str, employee_id: str
) -> tuple[User, Employee]:
    """Fetch one employee of this store or raise 404 (never 403)."""
    employee = db.scalar(
        select(Employee).where(
            Employee.id == employee_id, Employee.store_id == store_id
        )
    )
    if employee is None:
        raise NotFoundError("Employee not found")
    user = db.get(User, employee.id)
    if user is None:  # pragma: no cover - corrupt data guard
        raise NotFoundError("Employee not found")
    return user, employee


def list_employees(
    db: Session,
    *,
    store_id: str,
    search: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[tuple[User, Employee]], int]:
    """Paginated directory listing with name/number search and status filter."""
    stmt = (
        select(User, Employee)
        .join(Employee, Employee.id == User.id)
        .where(Employee.store_id == store_id, User.role == UserRole.EMPLOYEE)
    )
    count_stmt = (
        select(func.count())
        .select_from(User)
        .join(Employee, Employee.id == User.id)
        .where(Employee.store_id == store_id, User.role == UserRole.EMPLOYEE)
    )
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(User.full_name).like(like)
            | func.lower(Employee.employee_number).like(like)
            | func.lower(User.email).like(like)
        )
        count_stmt = count_stmt.where(
            func.lower(User.full_name).like(like)
            | func.lower(Employee.employee_number).like(like)
            | func.lower(User.email).like(like)
        )
    if status:
        stmt = stmt.where(Employee.status == status)
        count_stmt = count_stmt.where(Employee.status == status)
    total = int(db.scalar(count_stmt) or 0)
    rows = db.execute(stmt.order_by(User.full_name).offset(offset).limit(limit)).all()
    return [(row[0], row[1]) for row in rows], total


def update_employee(
    db: Session,
    *,
    user: User,
    employee: Employee,
    payload: EmployeeUpdate,
    updated_by: User,
    ip: str | None = None,
) -> tuple[User, Employee]:
    """Apply a partial update; role/store/status changes are manager-only."""
    from app.models.enums import EmployeeStatus

    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "email" in data and data["email"]:
        clash = db.scalar(
            select(User).where(User.email == data["email"].lower(), User.id != user.id)
        )
        if clash is not None:
            raise ConflictError("Another account already uses this email")
        user.email = data["email"].lower()
    for field in (
        "phone",
        "address",
        "hire_date",
        "skill_level",
        "skills",
        "contract_weekly_hours",
        "hourly_rate",
        "is_keyholder",
    ):
        if field in data:
            setattr(employee, field, data[field])
    if "status" in data and data["status"] is not None:
        if updated_by.role != UserRole.MANAGER:
            from app.core.errors import ForbiddenError

            raise ForbiddenError("Only managers can change employment status")
        employee.status = (
            data["status"]
            if isinstance(data["status"], EmployeeStatus)
            else EmployeeStatus(data["status"])
        )
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=employee.id,
        user_id=updated_by.id,
        store_id=employee.store_id,
        details={"updated_fields": sorted(data.keys())},
        ip_address=ip,
    )
    db.flush()
    return user, employee


def deactivate_employee(
    db: Session,
    *,
    user: User,
    employee: Employee,
    deactivated_by: User,
    ip: str | None = None,
) -> tuple[User, Employee]:
    """Deactivate both the login and the employee record together."""
    from app.models.enums import EmployeeStatus

    employee.status = EmployeeStatus.INACTIVE
    user.is_active = False
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=employee.id,
        user_id=deactivated_by.id,
        store_id=employee.store_id,
        details={"action": "deactivate"},
        ip_address=ip,
    )
    db.flush()
    return user, employee
