"""Authentication routes: login, session, password change, manager bootstrap."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_manager
from app.core.errors import ConflictError, UnauthorizedError, success
from app.core.rate_limit import client_ip, get_limiter
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import AuditAction, User, UserRole
from app.models.user import Store
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    ManagerCreateRequest,
    UserResponse,
)
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(user: User) -> dict:
    employee = user.employee
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "store_id": user.store_id,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "employee": (
            {
                "id": employee.id,
                "employee_number": employee.employee_number,
                "full_name": user.full_name,
                "skill_level": (
                    employee.skill_level.value
                    if hasattr(employee.skill_level, "value")
                    else str(employee.skill_level)
                ),
            }
            if employee is not None
            else None
        ),
    }


@router.post("/login")
def login(
    payload: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    """Authenticate with email + password and receive a bearer token."""
    limiter = get_limiter(
        "login",
        settings.rate_limit_enabled,
        settings.rate_limit_login_attempts,
        settings.rate_limit_window_seconds,
    )
    key = client_ip(request)
    if not limiter.check(key):
        from app.core.errors import AppError

        raise AppError(
            f"Too many login attempts. Try again in {limiter.retry_after(key)}s.",
            status_code=429,
        )
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated")
    user.touch_login()
    audit_service.log_action(
        db,
        action=AuditAction.LOGIN,
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        store_id=user.store_id,
        ip_address=key,
    )
    token = create_access_token(
        subject=user.id,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        store_id=user.store_id,
    )
    return success(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": _user_payload(user),
        },
        message="Login successful",
    )


@router.get("/me", response_model=None)
def read_session(current_user: User = Depends(get_current_user)) -> dict:
    """Return the current session user."""
    return success(
        data=UserResponse.model_validate(_user_payload(current_user)).model_dump(
            mode="json"
        ),
        message="Session user",
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Change the caller's own password after verifying the current one."""
    user = db.get(User, current_user.id)
    if user is None or not verify_password(
        payload.current_password, user.hashed_password
    ):
        raise UnauthorizedError("Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        store_id=user.store_id,
        details={"field": "password"},
    )
    return success(message="Password changed")


@router.post("/managers")
def create_manager(
    payload: ManagerCreateRequest,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Provision a manager account (manager-only secure bootstrap path).

    There is no public self-registration for managers: a signed-in manager
    creates the account, scoped to a store they manage unless they are
    explicitly creating for another store they also administer.
    """
    store_id = payload.store_id or manager.store_id
    if store_id is None:
        raise ConflictError("A store must be specified for the new manager")
    store = db.scalar(select(Store).where(Store.id == store_id))
    if store is None:
        raise ConflictError("Store not found")
    if manager.store_id and store_id != manager.store_id:
        # Managers may only bootstrap managers for their own store.
        raise ConflictError("You can only create managers for your own store")
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise ConflictError("An account with this email already exists")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.MANAGER,
        store_id=store_id,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("An account with this email already exists") from exc
    audit_service.log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="user",
        entity_id=user.id,
        user_id=manager.id,
        store_id=store_id,
        details={"role": "manager", "email": user.email},
        ip_address=client_ip(request),
    )
    return success(
        data={
            "user": UserResponse.model_validate(_user_payload(user)).model_dump(
                mode="json"
            ),
            "message": "Manager account created. Share the password securely; it is not returned by this API.",
        },
        message="Manager created",
        status_code=201,
    )


@router.post("/logout")
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record a logout event (tokens are stateless; the client discards them)."""
    audit_service.log_action(
        db,
        action=AuditAction.LOGOUT,
        entity_type="user",
        entity_id=current_user.id,
        user_id=current_user.id,
        store_id=current_user.store_id,
        ip_address=client_ip(request),
    )
    _ = datetime.now(UTC)
    return success(message="Logged out")
