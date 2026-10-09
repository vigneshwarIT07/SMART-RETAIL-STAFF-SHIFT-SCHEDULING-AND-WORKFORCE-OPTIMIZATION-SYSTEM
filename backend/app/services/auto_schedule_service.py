"""Deterministic automatic scheduling proposals.

Greedy, fully explainable algorithm: shifts are handled most-constrained
first (fewest eligible candidates), and candidates are ranked by fewest
scheduled hours, then skill match, then rest fit.  The same inputs always
produce the same proposal — there is no randomness and no external AI
service involved.

Proposals are *never* applied automatically.  :func:`apply_proposal`
requires an explicit manager call (the confirmation step in the UI) and
re-validates every assignment inside one transaction.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AssignmentStatus,
    AuditAction,
    Employee,
    Shift,
    ShiftAssignment,
    ShiftStatus,
    User,
)

from . import assignment_service, audit_service, scheduling_service, shift_service


def _active_employees(db: Session, store_id: str) -> list[Employee]:
    return list(
        db.scalars(
            select(Employee).where(
                Employee.store_id == store_id, Employee.status == "ACTIVE"
            )
        ).all()
    )


def _open_shifts(
    db: Session, *, store_id: str, start_date: date, end_date: date
) -> list[Shift]:
    return list(
        db.scalars(
            select(Shift)
            .where(
                Shift.store_id == store_id,
                Shift.shift_date >= start_date,
                Shift.shift_date <= end_date,
                Shift.status != ShiftStatus.CANCELLED,
            )
            .order_by(Shift.shift_date, Shift.start_time)
        ).all()
    )


def _open_slots(db: Session, shift: Shift) -> int:
    needed = shift.required_employees or 1
    have = assignment_service.active_assignment_count(db, shift.id)
    return max(0, needed - have)


def generate_proposal(
    db: Session,
    *,
    store_id: str,
    start_date: date,
    end_date: date,
    employee_ids: Optional[Sequence[str]] = None,
    max_weekly_hours: Optional[int] = None,
) -> dict:
    """Build a scheduling proposal for the window without writing anything.

    Returns ``{"proposals", "unfillable", "summary"}``.  Each proposal entry
    carries the employee, the shift and a human-readable ``reasons`` list so
    the UI can explain every suggestion.  ``unfillable`` lists shifts (or
    remaining slots) for which no eligible candidate exists, with reasons.
    """
    cap = max_weekly_hours if max_weekly_hours is not None else settings.max_weekly_hours
    employees = _active_employees(db, store_id)
    if employee_ids is not None:
        wanted = set(employee_ids)
        employees = [emp for emp in employees if emp.id in wanted]

    shifts = [s for s in _open_shifts(db, store_id=store_id, start_date=start_date, end_date=end_date) if _open_slots(db, s) > 0]

    # Virtual week-hours ledger so proposals within one run respect the cap.
    week_hours: dict[tuple[str, date], Decimal] = {}

    def ledger_hours(employee_id: str, day: date) -> Decimal:
        week_start = day - timedelta(days=day.weekday())
        key = (employee_id, week_start)
        if key not in week_hours:
            week_hours[key] = assignment_service.weekly_hours(db, employee_id, week_start)
        return week_hours[key]

    # Most-constrained shift first: fewest *valid* candidates.
    scored: list[tuple[int, Shift, list[dict]]] = []
    for shift in shifts:
        ranked = assignment_service.find_eligible_employees(db, shift, employees)
        valid = [row for row in ranked if row["valid"]]
        scored.append((len(valid), shift, ranked))
    scored.sort(key=lambda item: (item[0], item[1].shift_date, item[1].start_time))

    proposals: list[dict] = []
    unfillable: list[dict] = []
    # Track virtual assignments inside this run to avoid double-booking.
    virtual: dict[str, list[Shift]] = {emp.id: [] for emp in employees}

    for _valid_count, shift, ranked in scored:
        slots = _open_slots(db, shift)
        filled = 0
        for row in ranked:
            if filled >= slots:
                break
            employee: Employee = row["employee"]
            if not row["valid"]:
                continue
            # Ledger cap check (weekly-hours is advisory, but the generator
            # treats the cap as a hard limit to keep proposals safe).
            if ledger_hours(employee.id, shift.shift_date) + Decimal(str(shift.duration_hours)) > cap:
                continue
            # Virtual overlap check against proposals made in this run.
            new_start, new_end = _virtual_interval(db, shift)
            clash = False
            for other in virtual[employee.id]:
                other_start, other_end = _virtual_interval(db, other)
                if new_start < other_end and other_start < new_end:
                    clash = True
                    break
            if clash:
                continue
            reasons = _explain(db, shift, employee, row)
            proposals.append(
                {
                    "shift_id": shift.id,
                    "shift_date": shift.shift_date,
                    "employee_id": employee.id,
                    "employee_name": scheduling_service._display_name(db, employee),
                    "reasons": reasons,
                }
            )
            week_start = shift.shift_date - timedelta(days=shift.shift_date.weekday())
            key = (employee.id, week_start)
            week_hours[key] = ledger_hours(employee.id, shift.shift_date) + Decimal(
                str(shift.duration_hours)
            )
            virtual[employee.id].append(shift)
            filled += 1
        remaining = slots - filled
        if remaining > 0:
            unfillable.append(
                {
                    "shift_id": shift.id,
                    "shift_date": shift.shift_date,
                    "role_required": shift.role_required,
                    "remaining_slots": remaining,
                    "reason": _unfillable_reason(ranked),
                }
            )

    summary = {
        "shifts_considered": len(shifts),
        "proposals": len(proposals),
        "unfillable_shifts": len(unfillable),
    }
    return {"proposals": proposals, "unfillable": unfillable, "summary": summary}


def _virtual_interval(db: Session, shift: Shift) -> tuple:
    """UTC interval helper that reuses the assignment service loader."""
    return assignment_service._interval(db, shift)


def _explain(db: Session, shift: Shift, employee: Employee, row: dict) -> list[str]:
    """Human-readable reasons for one proposed assignment."""
    reasons: list[str] = []
    week_start = shift.shift_date - timedelta(days=shift.shift_date.weekday())
    hours = assignment_service.weekly_hours(db, employee.id, week_start)
    reasons.append(f"Lowest scheduled load this week ({hours:.1f}h).")
    if shift.required_skill and employee.has_skill(shift.required_skill):
        reasons.append(f"Has required skill '{shift.required_skill}'.")
    elif not shift.required_skill:
        reasons.append("No specific skill required for this shift.")
    if not row["warnings"]:
        reasons.append("No conflicts: available, rested and within limits.")
    else:
        for warning in row["warnings"][:2]:
            reasons.append(f"Note: {warning['message']}")
    return reasons


def _unfillable_reason(ranked: list[dict]) -> str:
    """Explain why a shift could not be filled."""
    if not ranked:
        return "No active employees in this store."
    blocking_codes = [v["code"] for row in ranked for v in row["violations"]]
    if not blocking_codes:
        return "All candidates exceed the weekly-hours cap."
    most_common = max(set(blocking_codes), key=blocking_codes.count)
    explanations = {
        "overlap": "All candidates already work overlapping shifts.",
        "on-leave": "All candidates are on approved leave.",
        "employee-inactive": "No active candidates available.",
        "wrong-store": "No candidates belong to this store.",
        "shift-closed": "Shift is closed to assignments.",
        "unavailable": "All candidates marked themselves unavailable.",
    }
    return explanations.get(most_common, f"Blocked by '{most_common}' for all candidates.")


def apply_proposal(
    db: Session,
    *,
    store_id: str,
    proposals: Sequence[dict],
    approved_by: User,
    publish: bool = False,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """Apply manager-confirmed proposals atomically.

    Every proposal is re-validated immediately before writing; if any entry
    fails, the whole batch is rolled back and an error is raised.  Nothing
    is committed here — the caller (via ``get_db``) owns the commit.
    """
    from app.core.errors import ConflictError

    applied: list[dict] = []
    shift_ids: list[str] = []
    try:
        for entry in proposals:
            shift_id = entry["shift_id"]
            employee_id = entry["employee_id"]
            shift = shift_service.get_shift(db, store_id=store_id, shift_id=shift_id)
            employee = db.scalar(
                select(Employee).where(
                    Employee.id == employee_id, Employee.store_id == store_id
                )
            )
            if employee is None:
                raise ConflictError(f"Employee {employee_id} not found in this store.")
            assignment = assignment_service.assign_employee(
                db,
                shift,
                employee,
                approved_by,
                notes="Auto-scheduling proposal (manager confirmed)",
                force=False,
                is_auto_assigned=True,
            )
            applied.append(
                {
                    "assignment_id": assignment.id,
                    "shift_id": shift.id,
                    "employee_id": employee.id,
                }
            )
            shift_ids.append(shift.id)
        published_count = 0
        if publish and shift_ids:
            published = shift_service.publish_shifts(
                db, store_id=store_id, manager=approved_by, shift_ids=shift_ids
            )
            published_count = len(published)
    except Exception:
        db.rollback()
        raise

    audit_service.log_action(
        db,
        action=AuditAction.APPROVAL,
        entity_type="scheduling_proposal",
        entity_id=None,
        user_id=approved_by.id,
        store_id=store_id,
        details={"applied": len(applied), "publish": publish},
    )
    db.flush()
    return {"applied": applied, "published": publish, "published_count": published_count}
