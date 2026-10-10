"""Shift-swap routes: eligibility check, request, review, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_manager
from app.core.errors import NotFoundError, success
from app.db.session import get_db
from app.models import Employee, Shift, ShiftSwapRequest, User
from app.models.enums import SwapStatus
from app.schemas.operations import SwapCreate, SwapDecision
from app.services import shift_service, swap_service

router = APIRouter(prefix="/swaps", tags=["swaps"])


def _person_display(db: Session, employee_id: str) -> tuple[str | None, str | None]:
    """Return (full_name, employee_number) for an employee id, tolerating gaps."""
    user = db.get(User, employee_id)
    employee = db.get(Employee, employee_id)
    name = user.full_name if user is not None else None
    number = employee.employee_number if employee is not None else None
    return name, number


def _swap_payload(db: Session, swap: ShiftSwapRequest) -> dict:
    """Serialise a swap request with human-readable participant names.

    The swaps table only stores participant ids; without enrichment the UI
    falls back to showing raw UUID prefixes. Names come from the linked
    user rows (employees share their primary key with ``users.id``).
    """
    requester_name, requester_number = _person_display(db, swap.requester_id)
    target_name, target_number = _person_display(db, swap.target_employee_id)
    return {
        "id": swap.id,
        "requester_id": swap.requester_id,
        "requester_name": requester_name,
        "requester_number": requester_number,
        "target_employee_id": swap.target_employee_id,
        "target_employee_name": target_name,
        "target_employee_number": target_number,
        "requester_shift_id": swap.requester_shift_id,
        "target_shift_id": swap.target_shift_id,
        "reason": swap.reason,
        "status": (swap.status.value if hasattr(swap.status, "value") else str(swap.status)),
        "has_conflict": swap.has_conflict,
        "conflict_details": swap.conflict_details,
        "eligibility": swap.eligibility,
        "reviewed_by": swap.reviewed_by,
        "reviewed_at": swap.reviewed_at,
        "review_note": swap.review_note,
        "created_at": swap.created_at,
        "updated_at": swap.updated_at,
    }


def _resolve_swap(db: Session, swap_id: str, user: User) -> ShiftSwapRequest:
    swap = db.get(ShiftSwapRequest, swap_id)
    if swap is None:
        raise NotFoundError("Swap request not found")
    requester = db.get(Employee, swap.requester_id)
    if requester is None or requester.store_id != user.store_id:
        raise NotFoundError("Swap request not found")
    if user.role.value != "manager" and swap.requester_id != user.id:
        target = db.get(Employee, swap.target_employee_id)
        if target is None or target.id != user.id:
            raise NotFoundError("Swap request not found")
    return swap


@router.get("")
def list_swaps(
    employee_id: str | None = Query(default=None),
    status: SwapStatus | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """List swap requests involving the caller (or the store, for managers)."""
    scope_employee = employee_id
    if current_user.role.value != "manager":
        scope_employee = current_user.id
    rows = swap_service.list_requests(
        db,
        store_id=current_user.store_id,
        employee_id=scope_employee,
        status=status,
    )
    return success(
        data=jsonable_encoder([_swap_payload(db, row) for row in rows]),
        message="Swap requests",
    )


@router.post("/check-eligibility")
def check_eligibility(
    requester_shift_id: str,
    target_shift_id: str,
    target_employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Preview whether two shifts can be swapped, with reasons."""
    requester = db.get(Employee, current_user.id)
    if requester is None:
        raise NotFoundError("No employee record is linked to this account")
    target = db.get(Employee, target_employee_id)
    if target is None:
        raise NotFoundError("Employee not found")
    requester_shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=requester_shift_id
    )
    target_shift = shift_service.get_shift(
        db, store_id=current_user.store_id, shift_id=target_shift_id
    )
    result = swap_service.check_eligibility(
        db,
        requester=requester,
        target=target,
        requester_shift=requester_shift,
        target_shift=target_shift,
    )
    return success(data=jsonable_encoder(result), message="Eligibility result")


@router.post("", status_code=201)
def create_swap(
    payload: SwapCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Request a shift swap with another employee."""
    _ = request
    requester = db.get(Employee, current_user.id)
    if requester is None:
        raise NotFoundError("No employee record is linked to this account")
    req_shift: Shift | None = None
    tgt_shift: Shift | None = None
    _ = req_shift, tgt_shift
    swap = swap_service.create_request(
        db,
        requester=requester,
        target_employee_id=payload.target_employee_id,
        requester_shift_id=payload.requester_shift_id,
        target_shift_id=payload.target_shift_id,
        reason=payload.reason,
    )
    return success(
        data=jsonable_encoder(_swap_payload(db, swap)),
        message="Swap requested",
        status_code=201,
    )


@router.get("/{swap_id}")
def read_swap(
    swap_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return one swap request."""
    swap = _resolve_swap(db, swap_id, current_user)
    return success(data=jsonable_encoder(_swap_payload(db, swap)), message="Swap request")


@router.post("/{swap_id}/decide")
def decide_swap(
    swap_id: str,
    payload: SwapDecision,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Approve (atomic double-swap) or reject a swap request."""
    _ = request
    swap = _resolve_swap(db, swap_id, manager)
    swap = swap_service.decide_request(
        db,
        swap=swap,
        reviewer=manager,
        decision=payload.decision,
        review_note=payload.review_note,
    )
    return success(
        data=jsonable_encoder(_swap_payload(db, swap)),
        message=f"Swap {payload.decision}",
    )


@router.post("/{swap_id}/cancel")
def cancel_swap(
    swap_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cancel a pending swap request (involved party or manager)."""
    swap = _resolve_swap(db, swap_id, current_user)
    swap = swap_service.cancel_request(db, swap=swap, cancelled_by=current_user)
    return success(
        data=jsonable_encoder(_swap_payload(db, swap)),
        message="Swap request cancelled",
    )
