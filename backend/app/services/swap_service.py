"""Shift swap lifecycle: requests, eligibility checks and atomic approval.

A swap exchanges the assignees of two shifts: the requester's shift goes to
the target employee and the target's shift goes to the requester.  Approval
re-validates *both* halves with :func:`assignment_service.validate_assignment`
immediately before writing, and applies the exchange inside a single
transaction — either both assignments move or neither does.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssignmentStatus,
    AuditAction,
    Employee,
    Shift,
    ShiftAssignment,
    ShiftStatus,
    ShiftSwapRequest,
    SwapStatus,
    User,
)

from . import assignment_service, audit_service, notification_service


def _active_link(db: Session, shift_id: str, employee_id: str):
    return db.scalar(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift_id,
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.status.notin_([AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]),
        )
    )


def check_eligibility(
    db: Session,
    *,
    requester: Employee,
    target: Employee,
    requester_shift: Shift,
    target_shift: Shift,
) -> dict:
    """Dry-run both halves of a swap; returns blocking issues per side."""
    requester_result = assignment_service.validate_assignment(db, target_shift, requester)
    target_result = assignment_service.validate_assignment(db, requester_shift, target)
    blocking = [
        issue
        for issue in (requester_result["violations"] + target_result["violations"])
        if issue["blocking"]
    ]
    return {
        "eligible": not blocking,
        "requester_side": requester_result,
        "target_side": target_result,
    }


def create_request(
    db: Session,
    *,
    requester: Employee,
    target_employee_id: str,
    requester_shift_id: str,
    target_shift_id: str,
    reason: str | None = None,
) -> ShiftSwapRequest:
    """File a swap request after verifying ownership and running eligibility."""
    from app.core.errors import ConflictError, NotFoundError

    if requester_shift_id == target_shift_id:
        raise ConflictError("Cannot swap a shift with itself.")

    requester_shift = db.scalar(
        select(Shift).where(Shift.id == requester_shift_id, Shift.store_id == requester.store_id)
    )
    target_shift = db.scalar(
        select(Shift).where(Shift.id == target_shift_id, Shift.store_id == requester.store_id)
    )
    if requester_shift is None or target_shift is None:
        raise NotFoundError("One of the shifts was not found in this store.")
    if requester_shift.status == ShiftStatus.CANCELLED:
        raise ConflictError("The requester's shift is cancelled.")
    if target_shift.status == ShiftStatus.CANCELLED:
        raise ConflictError("The target shift is cancelled.")

    target = db.scalar(
        select(Employee).where(
            Employee.id == target_employee_id,
            Employee.store_id == requester.store_id,
        )
    )
    if target is None:
        raise NotFoundError("Target employee not found in this store.")
    if target.id == requester.id:
        raise ConflictError("Cannot swap a shift with yourself.")

    if _active_link(db, requester_shift.id, requester.id) is None:
        raise ConflictError("You are not assigned to the offered shift.")
    if _active_link(db, target_shift.id, target.id) is None:
        raise ConflictError("The target employee is not on the requested shift.")

    eligibility = check_eligibility(
        db,
        requester=requester,
        target=target,
        requester_shift=requester_shift,
        target_shift=target_shift,
    )
    swap = ShiftSwapRequest(
        requester_id=requester.id,
        target_employee_id=target.id,
        requester_shift_id=requester_shift.id,
        target_shift_id=target_shift.id,
        reason=reason,
        status=SwapStatus.PENDING,
        has_conflict=not eligibility["eligible"],
        conflict_details=(
            json.dumps(
                {
                    "requester_side": eligibility["requester_side"],
                    "target_side": eligibility["target_side"],
                },
                default=str,
            )
            if not eligibility["eligible"]
            else None
        ),
        eligibility={"eligible": eligibility["eligible"]},
    )
    db.add(swap)
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="shift_swap_request",
        entity_id=swap.id,
        user_id=requester.id,
        store_id=requester.store_id,
        details={"target": target.id},
    )
    # Notify the target employee's user account.
    from app.models.user import User as _User

    target_user = db.scalar(_select_user(_User, target.id))
    if target_user is not None:
        notification_service.create_notification(
            db,
            user_id=target_user.id,
            notification_type="SWAP_REQUEST",
            title="New swap request",
            body=(
                f"{requester.employee_number} wants to swap "
                f"{requester_shift.shift_date.isoformat()} for your "
                f"{target_shift.shift_date.isoformat()} shift."
            ),
            link_url="/swaps",
        )
    db.flush()
    return swap


def _select_user(model, user_id: str):
    return select(model).where(model.id == user_id)


def decide_request(
    db: Session,
    *,
    swap: ShiftSwapRequest,
    reviewer: User,
    decision: str,
    review_note: str | None = None,
) -> ShiftSwapRequest:
    """Approve (atomic exchange) or reject a pending swap request.

    Approval re-validates both halves first; any blocking violation aborts
    the whole decision with a rollback.  The exchange itself — cancelling
    the two old links and creating the two new ones — happens in one
    transaction.
    """
    from app.core.errors import ConflictError

    if swap.status != SwapStatus.PENDING:
        raise ConflictError(f"Swap request is already {swap.status.value}.")
    if decision not in ("approved", "rejected"):
        raise ConflictError("Decision must be 'approved' or 'rejected'.")

    if decision == "rejected":
        swap.status = SwapStatus.REJECTED
        swap.reviewed_by = reviewer.id
        swap.reviewed_at = datetime.now(UTC)
        swap.review_note = review_note
        db.flush()
        audit_service.log_action(
            db,
            action=AuditAction.REJECTION,
            entity_type="shift_swap_request",
            entity_id=swap.id,
            user_id=reviewer.id,
            store_id=reviewer.store_id,
            details={},
        )
        _notify_parties(db, swap, decision)
        db.flush()
        return swap

    # Approval path — everything below must succeed together.
    try:
        requester = db.scalar(select(Employee).where(Employee.id == swap.requester_id))
        target = db.scalar(select(Employee).where(Employee.id == swap.target_employee_id))
        requester_shift = db.scalar(select(Shift).where(Shift.id == swap.requester_shift_id))
        target_shift = db.scalar(select(Shift).where(Shift.id == swap.target_shift_id))
        if requester is None or target is None:
            raise ConflictError("One of the employees no longer exists.")
        if requester_shift is None or target_shift is None:
            raise ConflictError("One of the shifts no longer exists.")

        old_requester_link = _active_link(db, requester_shift.id, requester.id)
        old_target_link = _active_link(db, target_shift.id, target.id)
        if old_requester_link is None or old_target_link is None:
            raise ConflictError(
                "Assignments changed since the request was filed; " "re-file the swap."
            )

        # Fresh re-validation of both halves.
        eligibility = check_eligibility(
            db,
            requester=requester,
            target=target,
            requester_shift=requester_shift,
            target_shift=target_shift,
        )
        if not eligibility["eligible"]:
            swap.has_conflict = True
            swap.conflict_details = json.dumps(
                {
                    "requester_side": eligibility["requester_side"],
                    "target_side": eligibility["target_side"],
                },
                default=str,
            )
            raise ConflictError(
                "Swap no longer passes validation; details recorded on the request."
            )

        # Atomic exchange. Old links are cancelled; the new links reuse a
        # historical row when one exists, because (shift, employee) carries
        # a plain unique constraint that a blind INSERT would violate.
        old_requester_link.status = AssignmentStatus.CANCELLED
        old_requester_link.cancelled_reason = f"Swap {swap.id} approved"
        old_target_link.status = AssignmentStatus.CANCELLED
        old_target_link.cancelled_reason = f"Swap {swap.id} approved"

        def _place(shift_id: str, employee_id: str) -> None:
            existing = db.scalar(
                select(ShiftAssignment).where(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.employee_id == employee_id,
                )
            )
            note = f"Swap {swap.id} approved"
            if existing is not None:
                existing.status = AssignmentStatus.ASSIGNED
                existing.assigned_by = reviewer.id
                existing.assigned_at = datetime.now(UTC)
                existing.cancelled_at = None
                existing.cancelled_reason = None
                existing.notes = note
                existing.is_auto_assigned = False
                return
            db.add(
                ShiftAssignment(
                    shift_id=shift_id,
                    employee_id=employee_id,
                    status=AssignmentStatus.ASSIGNED,
                    assigned_by=reviewer.id,
                    notes=note,
                )
            )

        _place(target_shift.id, requester.id)
        _place(requester_shift.id, target.id)
        swap.status = SwapStatus.APPROVED
        swap.has_conflict = False
        swap.reviewed_by = reviewer.id
        swap.reviewed_at = datetime.now(UTC)
        swap.review_note = review_note
        db.flush()
    except Exception:
        db.rollback()
        raise

    audit_service.log_action(
        db,
        action=AuditAction.APPROVAL,
        entity_type="shift_swap_request",
        entity_id=swap.id,
        user_id=reviewer.id,
        store_id=reviewer.store_id,
        details={
            "requester": swap.requester_id,
            "target": swap.target_employee_id,
        },
    )
    _notify_parties(db, swap, decision)
    db.flush()
    return swap


def _notify_parties(db: Session, swap: ShiftSwapRequest, decision: str) -> None:
    """Notify both swap parties of the decision."""
    from app.models.user import User as _User

    for user_id in (swap.requester_id, swap.target_employee_id):
        user = db.scalar(_select_user(_User, user_id))
        if user is None:
            continue
        notification_service.create_notification(
            db,
            user_id=user.id,
            notification_type="SWAP_DECISION",
            title=f"Swap {decision}",
            body=f"Your shift swap request was {decision}.",
            link_url="/swaps",
            dedupe_key=f"swap-{swap.id}-{decision}-{user_id}",
        )


def cancel_request(db: Session, *, swap: ShiftSwapRequest, cancelled_by: User) -> ShiftSwapRequest:
    """Withdraw a pending swap request (requester or manager)."""
    from app.core.errors import ConflictError

    if swap.status != SwapStatus.PENDING:
        raise ConflictError(f"Cannot cancel a {swap.status.value} request.")
    swap.status = SwapStatus.CANCELLED
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="shift_swap_request",
        entity_id=swap.id,
        user_id=cancelled_by.id,
        store_id=cancelled_by.store_id,
        details={"cancelled": True},
    )
    db.flush()
    return swap


def list_requests(
    db: Session,
    *,
    store_id: str,
    employee_id: str | None = None,
    status: SwapStatus | None = None,
) -> Sequence[ShiftSwapRequest]:
    """List swap requests touching a store, optionally filtered."""
    stmt = (
        select(ShiftSwapRequest)
        .join(Employee, Employee.id == ShiftSwapRequest.requester_id)
        .where(Employee.store_id == store_id)
        .order_by(ShiftSwapRequest.created_at.desc())
    )
    if employee_id is not None:
        stmt = stmt.where(
            (ShiftSwapRequest.requester_id == employee_id)
            | (ShiftSwapRequest.target_employee_id == employee_id)
        )
    if status is not None:
        stmt = stmt.where(ShiftSwapRequest.status == status)
    return db.scalars(stmt).all()


def get_request(db: Session, *, store_id: str, request_id: str) -> ShiftSwapRequest:
    """Fetch one swap request of this store or raise a 404 (never a 403)."""
    from app.core.errors import NotFoundError

    swap = db.scalar(
        select(ShiftSwapRequest)
        .join(Employee, Employee.id == ShiftSwapRequest.requester_id)
        .where(ShiftSwapRequest.id == request_id, Employee.store_id == store_id)
    )
    if swap is None:
        raise NotFoundError("Swap request not found")
    return swap
