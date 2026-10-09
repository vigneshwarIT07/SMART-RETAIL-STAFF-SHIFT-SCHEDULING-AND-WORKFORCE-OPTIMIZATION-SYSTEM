"""Leave request lifecycle: filing, conflict flagging and decisions.

Conflict semantics: when an employee files leave that overlaps already
scheduled shifts, the request is kept but flagged (``has_conflict``) with
the clashing shift dates in ``conflict_details``.  A flagged request can
still be approved — approval is the manager's *explicit resolution* of the
conflict.  Approving leave cancels the overlapping active assignments so
the roster never shows someone as scheduled while on leave.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssignmentStatus,
    AuditAction,
    Employee,
    LeaveRequest,
    LeaveStatus,
    Shift,
    ShiftAssignment,
    ShiftStatus,
    User,
)

from . import audit_service, notification_service


def overlapping_shifts(
    db: Session, employee_id: str, start_date: date, end_date: date
) -> list[Shift]:
    """Active scheduled shifts of an employee inside a leave window."""
    stmt = (
        select(Shift)
        .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.status.notin_(
                [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
            ),
            Shift.status != ShiftStatus.CANCELLED,
            Shift.shift_date >= start_date,
            Shift.shift_date <= end_date,
        )
        .order_by(Shift.shift_date)
    )
    return list(db.scalars(stmt).all())


def file_request(
    db: Session,
    *,
    employee: Employee,
    start_date: date,
    end_date: date,
    leave_type,
    reason: Optional[str] = None,
) -> LeaveRequest:
    """File a leave request, flagging conflicts with scheduled shifts."""
    from app.core.errors import ConflictError

    if end_date < start_date:
        raise ConflictError("Leave end date cannot be before the start date.")
    clashes = overlapping_shifts(db, employee.id, start_date, end_date)
    details = (
        json.dumps({"overlapping_shifts": [s.id for s in clashes]})
        if clashes
        else None
    )
    request = LeaveRequest(
        employee_id=employee.id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status=LeaveStatus.PENDING,
        has_conflict=bool(clashes),
        conflict_details=details,
    )
    db.add(request)
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="leave_request",
        entity_id=request.id,
        user_id=employee.id,
        store_id=employee.store_id,
        details={"start": start_date.isoformat(), "end": end_date.isoformat()},
    )
    notification_service.notify_store_managers(
        db,
        store_id=employee.store_id,
        notification_type="LEAVE_REQUEST",
        title="New leave request",
        body=(
            f"{employee.employee_number} requested leave "
            f"{start_date.isoformat()} to {end_date.isoformat()}."
        ),
        link_url="/leave",
    )
    db.flush()
    return request


def decide_request(
    db: Session,
    *,
    request: LeaveRequest,
    reviewer: User,
    decision: str,
    review_note: Optional[str] = None,
) -> LeaveRequest:
    """Approve or reject a pending request (explicit conflict resolution).

    Approval cancels overlapping active assignments so the roster stays
    consistent; the cancelled assignment ids are stored in the review note
    context for the audit trail.
    """
    from app.core.errors import ConflictError

    if request.status != LeaveStatus.PENDING:
        raise ConflictError(f"Request is already {request.status.value}.")
    if decision not in ("approved", "rejected"):
        raise ConflictError("Decision must be 'approved' or 'rejected'.")

    if decision == "approved":
        request.status = LeaveStatus.APPROVED
        clashes = overlapping_shifts(
            db, request.employee_id, request.start_date, request.end_date
        )
        cancelled: list[str] = []
        for shift in clashes:
            links = db.scalars(
                select(ShiftAssignment).where(
                    ShiftAssignment.shift_id == shift.id,
                    ShiftAssignment.employee_id == request.employee_id,
                    ShiftAssignment.status.notin_(
                        [AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW]
                    ),
                )
            ).all()
            for link in links:
                link.status = AssignmentStatus.CANCELLED
                link.cancelled_reason = f"Approved leave {request.id}"
                cancelled.append(link.id)
        if cancelled:
            prior = json.loads(request.conflict_details or "{}")
            prior["cancelled_assignments"] = cancelled
            request.conflict_details = json.dumps(prior)
    else:
        request.status = LeaveStatus.REJECTED

    request.reviewed_by = reviewer.id
    from datetime import datetime, timezone

    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = review_note
    db.flush()

    audit_service.log_action(
        db,
        action=AuditAction.APPROVAL if decision == "approved" else AuditAction.REJECTION,
        entity_type="leave_request",
        entity_id=request.id,
        user_id=reviewer.id,
        store_id=reviewer.store_id,
        details={"decision": decision, "had_conflict": request.has_conflict},
    )
    # Notify the employee's user account.
    from sqlalchemy import select as _select

    from app.models.user import User as _User

    employee_user = db.scalar(
        _select(_User).where(_User.id == request.employee_id)
    )
    if employee_user is not None:
        notification_service.create_notification(
            db,
            user_id=employee_user.id,
            notification_type="LEAVE_DECISION",
            title=f"Leave {decision}",
            body=(
                f"Your leave {request.start_date.isoformat()} to "
                f"{request.end_date.isoformat()} was {decision}."
            ),
            link_url="/leave",
            dedupe_key=f"leave-{request.id}-{decision}",
        )
    db.flush()
    return request


def cancel_request(
    db: Session, *, request: LeaveRequest, cancelled_by: User
) -> LeaveRequest:
    """Withdraw a pending request (employee) or void one (manager)."""
    from app.core.errors import ConflictError

    if request.status not in (LeaveStatus.PENDING, LeaveStatus.APPROVED):
        raise ConflictError(f"Cannot cancel a {request.status.value} request.")
    request.status = LeaveStatus.CANCELLED
    db.flush()
    audit_service.log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="leave_request",
        entity_id=request.id,
        user_id=cancelled_by.id,
        store_id=cancelled_by.store_id,
        details={"cancelled": True},
    )
    db.flush()
    return request


def list_requests(
    db: Session,
    *,
    store_id: str,
    employee_id: Optional[str] = None,
    status: Optional[LeaveStatus] = None,
) -> Sequence[LeaveRequest]:
    """List leave requests of a store, optionally filtered."""
    stmt = (
        select(LeaveRequest)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(Employee.store_id == store_id)
        .order_by(LeaveRequest.start_date.desc())
    )
    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    return db.scalars(stmt).all()


def get_request(db: Session, *, store_id: str, request_id: str) -> LeaveRequest:
    """Fetch one request of this store or raise a 404 (never a 403)."""
    from app.core.errors import NotFoundError

    request = db.scalar(
        select(LeaveRequest)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(LeaveRequest.id == request_id, Employee.store_id == store_id)
    )
    if request is None:
        raise NotFoundError("Leave request not found")
    return request
