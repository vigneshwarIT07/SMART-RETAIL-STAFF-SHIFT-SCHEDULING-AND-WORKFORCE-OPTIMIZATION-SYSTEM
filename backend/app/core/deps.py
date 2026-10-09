"""Shared FastAPI dependencies: authentication, roles and store scoping.

Authorization is enforced here, on the server, using only values derived from
the signed token. Nothing the browser sends - role, employee id, store id, or
worked hours - is ever trusted.

The acting employee is resolved by matching ``employees.id`` against the
authenticated ``users.id``, which is safe because the two tables share a
primary key.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.employee import Employee
from app.models.enums import EmployeeStatus, UserRole
from app.models.user import Store, User

# auto_error=False lets us raise our own errors so the JSON envelope stays
# identical for a missing header, a bad token, and an expired token.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the ``Authorization`` header.

    Args:
        request: The incoming request (used for audit context).
        credentials: Parsed bearer credentials.
        db: Request-scoped database session.

    Returns:
        The authenticated ``User`` row.

    Raises:
        UnauthorizedError: when the header is missing, the token is invalid or
            expired, or the account has been deactivated.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication credentials were not provided")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            "Your session has expired. Please sign in again."
        ) from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid authentication token")

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("The account linked to this token no longer exists")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated")

    request.state.user_id = user.id
    return user


def require_manager(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the caller is a manager.

    Args:
        current_user: The authenticated user.

    Returns:
        The same user when the check passes.

    Raises:
        ForbiddenError: when the caller holds the employee role.
    """
    if current_user.role != UserRole.MANAGER:
        raise ForbiddenError("This action requires a manager account")
    return current_user


def require_employee(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the caller is an employee (not a manager).

    Args:
        current_user: The authenticated user.

    Returns:
        The same user when the check passes.

    Raises:
        ForbiddenError: when the caller holds the manager role.
    """
    if current_user.role != UserRole.EMPLOYEE:
        raise ForbiddenError("This action requires an employee account")
    return current_user


def get_current_store(current_user: User = Depends(get_current_user)) -> Store:
    """Return the store the caller is scoped to.

    Args:
        current_user: The authenticated user.

    Returns:
        The caller's ``Store`` row.

    Raises:
        ForbiddenError: when the account is not attached to a store.
    """
    store = current_user.store
    if store is None:
        raise ForbiddenError("This account is not attached to a store")
    return store


def get_current_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee:
    """Return the ``Employee`` row linked to the authenticated user.

    Args:
        current_user: The authenticated user.
        db: Request-scoped database session.

    Returns:
        The caller's employee record.

    Raises:
        ForbiddenError: when no employee record exists for the account.
    """
    employee = db.get(Employee, current_user.id)
    if employee is None:
        raise ForbiddenError("No employee record is linked to this account")
    return employee


def get_optional_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee | None:
    """Return the caller's employee record, or ``None`` for managers."""
    return db.get(Employee, current_user.id)


def enforce_store_scope(record_store_id: str, current_user: User) -> None:
    """Block cross-store access.

    Object-level authorization: a manager may only ever see or change records
    belonging to the store encoded in their token.

    Args:
        record_store_id: The store the target record belongs to.
        current_user: The authenticated user.

    Raises:
        NotFoundError: when the record belongs to another store. A 404 is used
            rather than a 403 so the API does not confirm the existence of
            records the caller may not see.
    """
    if record_store_id != current_user.store_id:
        raise NotFoundError("Resource not found")


def assert_employee_visible(employee: Employee, current_user: User) -> None:
    """Check that a caller may act on the given employee.

    Managers may act on anyone in their own store; an employee may only act on
    their own record.

    Args:
        employee: The employee record being acted upon.
        current_user: The authenticated user.

    Raises:
        NotFoundError: when the employee belongs to another store.
        ForbiddenError: when an employee targets somebody else's record.
    """
    enforce_store_scope(employee.store_id, current_user)
    if current_user.role != UserRole.MANAGER and employee.id != current_user.id:
        raise ForbiddenError("You can only access your own records")


def get_managed_store_id(current_user: User) -> str:
    """Return the store id used to scope every manager query.

    Args:
        current_user: The authenticated user.

    Returns:
        The store id from the token-backed user row.

    Raises:
        ForbiddenError: when the account has no store attached.
    """
    if not current_user.store_id:
        raise ForbiddenError("This account is not attached to a store")
    return current_user.store_id


def paginate(page: int, page_size: int) -> tuple[int, int]:
    """Normalise pagination parameters against the configured limits.

    Args:
        page: Requested 1-based page number.
        page_size: Requested page size.

    Returns:
        A ``(offset, limit)`` pair.
    """
    safe_page = max(1, page)
    safe_size = max(1, min(page_size, settings.max_page_size))
    return (safe_page - 1) * safe_size, safe_size


def active_employee_query(store_id: str):
    """Build a query selecting active employees for a store.

    Args:
        store_id: The store to scope to.

    Returns:
        A SQLAlchemy ``Select`` statement.
    """
    return select(Employee).where(
        Employee.store_id == store_id,
        Employee.status == EmployeeStatus.ACTIVE,
    )
