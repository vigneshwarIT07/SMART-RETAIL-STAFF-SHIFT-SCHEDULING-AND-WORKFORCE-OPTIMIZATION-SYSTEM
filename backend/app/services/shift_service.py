"""Shift lifecycle: creation, edits, publishing and cancellation.

All shift timestamps entered by managers are wall-clock times in the
store's own timezone. :func:`shift_interval` converts a shift into an
unambiguous UTC interval; an ``end_time`` that is earlier than (or equal
to, which is rejected) ``start_time`` means the shift runs overnight into
the next calendar day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.employee import Employee
from app.models.enums import AuditAction, ShiftStatus
from app.models.shift import Shift, ShiftAssignment
from app.models.user import Store, User
from app.schemas.scheduling import ShiftBulkCreate, ShiftCreate, ShiftUpdate
from app.services.audit_service import log_action


def store_timezone(store: Store) -> ZoneInfo:
    """IANA timezone of a store, falling back to UTC on bad data."""

    try:
        return ZoneInfo(store.timezone or "UTC")
    except Exception:  # noqa: BLE001 - bad data must never crash scheduling
        return ZoneInfo("UTC")


def shift_interval(store: Store, shift: Shift) -> tuple[datetime, datetime]:
    """Return the ``(start_utc, end_utc)`` interval of a shift.

    The shift's date and times are interpreted in the store's timezone.
    Overnight shifts (``end_time <= start_time``) end on the following day.
    """

    tz = store_timezone(store)
    start_local = datetime.combine(shift.shift_date, shift.start_time, tzinfo=tz)
    end_day = shift.shift_date
    if shift.end_time <= shift.start_time:
        from datetime import timedelta

        end_day = shift.shift_date + timedelta(days=1)
    end_local = datetime.combine(end_day, shift.end_time, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def utcnow() -> datetime:
    """Current timezone-aware UTC time."""

    return datetime.now(UTC)


def get_shift(db: Session, *, store_id: str, shift_id: str) -> Shift:
    """Fetch one shift of this store or raise a 404 (never a 403)."""

    shift = db.scalar(
        select(Shift).where(Shift.id == shift_id, Shift.store_id == store_id)
    )
    if shift is None:
        raise NotFoundError("Shift not found")
    return shift


def list_shifts(
    db: Session,
    *,
    store_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: ShiftStatus | None = None,
    role: str | None = None,
) -> list[Shift]:
    """Shifts of one store inside an optional date window, oldest first."""

    stmt = select(Shift).where(Shift.store_id == store_id)
    if start_date is not None:
        stmt = stmt.where(Shift.shift_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Shift.shift_date <= end_date)
    if status is not None:
        stmt = stmt.where(Shift.status == status)
    if role:
        stmt = stmt.where(Shift.role_required == role)
    return list(db.scalars(stmt.order_by(Shift.shift_date, Shift.start_time)).all())


def create_shift(
    db: Session,
    *,
    store: Store,
    manager: User,
    payload: ShiftCreate,
    ip: str | None = None,
) -> Shift:
    """Create one shift slot; duplicate slots are rejected with a 409."""

    shift = Shift(
        store_id=store.id,
        shift_date=payload.shift_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        role_required=payload.role_required,
        required_skill=payload.required_skill,
        required_employees=payload.required_employees,
        notes=payload.notes,
        status=ShiftStatus.PUBLISHED if payload.publish else ShiftStatus.DRAFT,
        published_at=utcnow() if payload.publish else None,
        created_by=manager.id,
    )
    db.add(shift)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An identical shift slot already exists for this store and date."
        ) from exc
    log_action(
        db,
        action=AuditAction.CREATE,
        entity_type="shift",
        entity_id=shift.id,
        user_id=manager.id,
        store_id=store.id,
        details={"shift_date": str(payload.shift_date), "publish": payload.publish},
        ip_address=ip,
    )
    return shift


def bulk_create_shifts(
    db: Session,
    *,
    store: Store,
    manager: User,
    payload: ShiftBulkCreate,
    ip: str | None = None,
) -> list[Shift]:
    """Create the same slot on several explicit dates, skipping duplicates."""

    created: list[Shift] = []
    for day in sorted(set(payload.days)):
        candidate = ShiftCreate(
            shift_date=day,
            start_time=payload.start_time,
            end_time=payload.end_time,
            role_required=payload.role_required,
            required_skill=payload.required_skill,
            required_employees=payload.required_employees,
            notes=payload.notes,
            publish=payload.publish,
        )
        try:
            created.append(
                create_shift(db, store=store, manager=manager, payload=candidate, ip=ip)
            )
        except ConflictError:
            continue
    return created


def update_shift(
    db: Session,
    *,
    shift: Shift,
    manager: User,
    payload: ShiftUpdate,
    ip: str | None = None,
) -> Shift:
    """Edit a shift; cancelled shifts are immutable."""

    if shift.status == ShiftStatus.CANCELLED:
        raise ConflictError("Cancelled shifts cannot be edited.")
    changes: dict[str, str] = {}
    if payload.start_time is not None:
        shift.start_time = payload.start_time
        changes["start_time"] = str(payload.start_time)
    if payload.end_time is not None:
        shift.end_time = payload.end_time
        changes["end_time"] = str(payload.end_time)
    if shift.start_time == shift.end_time:
        raise ConflictError("start_time and end_time must differ")
    for field in ("role_required", "required_skill", "required_employees", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(shift, field, value)
            changes[field] = str(value)
    if payload.status is not None:
        shift.status = payload.status
        changes["status"] = payload.status.value
        if payload.status == ShiftStatus.PUBLISHED and shift.published_at is None:
            shift.published_at = utcnow()
    db.flush()
    log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="shift",
        entity_id=shift.id,
        user_id=manager.id,
        store_id=shift.store_id,
        details=changes,
        ip_address=ip,
    )
    return shift


def cancel_shift(
    db: Session, *, shift: Shift, manager: User, reason: str, ip: str | None = None
) -> Shift:
    """Cancel a shift. Assignments stay on record but become inactive."""

    from app.models.enums import AssignmentStatus

    shift.status = ShiftStatus.CANCELLED
    # Query fresh rows: the in-memory shift.assignments collection may be
    # stale (already loaded as empty) when assign + cancel share a session.
    links = db.scalars(
        select(ShiftAssignment).where(ShiftAssignment.shift_id == shift.id)
    ).all()
    for assignment in links:
        if assignment.status not in (
            AssignmentStatus.CANCELLED,
            AssignmentStatus.NO_SHOW,
        ):
            assignment.status = AssignmentStatus.CANCELLED
            assignment.cancelled_at = utcnow()
            assignment.cancelled_reason = f"Shift cancelled: {reason}"
    db.flush()
    log_action(
        db,
        action=AuditAction.UPDATE,
        entity_type="shift",
        entity_id=shift.id,
        user_id=manager.id,
        store_id=shift.store_id,
        details={"status": "cancelled", "reason": reason},
        ip_address=ip,
    )
    return shift


def publish_shifts(
    db: Session,
    *,
    store_id: str,
    manager: User,
    shift_ids: list[str],
    ip: str | None = None,
) -> list[Shift]:
    """Publish draft shifts so employees can see them."""

    shifts = db.scalars(
        select(Shift).where(Shift.store_id == store_id, Shift.id.in_(shift_ids))
    ).all()
    published: list[Shift] = []
    for shift in shifts:
        if shift.status == ShiftStatus.DRAFT:
            shift.status = ShiftStatus.PUBLISHED
            shift.published_at = utcnow()
            published.append(shift)
    db.flush()
    if published:
        log_action(
            db,
            action=AuditAction.PUBLISH,
            entity_type="shift",
            entity_id=None,
            user_id=manager.id,
            store_id=store_id,
            details={"published_shift_ids": [s.id for s in published]},
            ip_address=ip,
        )
    return published


def delete_shift(
    db: Session, *, shift: Shift, manager: User, ip: str | None = None
) -> None:
    """Delete a draft shift that has no active assignments."""

    from app.models.enums import AssignmentStatus

    if shift.status != ShiftStatus.DRAFT:
        raise ConflictError(
            "Only draft shifts can be deleted; cancel the shift instead."
        )
    # Count from a fresh query for the same staleness reason as cancel_shift.
    active = (
        db.scalar(
            select(func.count())
            .select_from(ShiftAssignment)
            .where(
                ShiftAssignment.shift_id == shift.id,
                ShiftAssignment.status.notin_(
                    (AssignmentStatus.CANCELLED, AssignmentStatus.NO_SHOW)
                ),
            )
        )
        or 0
    )
    if active > 0:
        raise ConflictError("Cannot delete a shift that has assigned employees.")
    log_action(
        db,
        action=AuditAction.DELETE,
        entity_type="shift",
        entity_id=shift.id,
        user_id=manager.id,
        store_id=shift.store_id,
        details={"shift_date": str(shift.shift_date)},
        ip_address=ip,
    )
    db.delete(shift)
    db.flush()


def employee_display_name(
    db: Session, employee_id: str
) -> tuple[str | None, str | None]:
    """Return ``(full_name, employee_number)`` for response enrichment."""

    row = db.scalars(select(Employee).where(Employee.id == employee_id)).first()
    if row is None:
        return None, None
    user = db.scalars(select(User).where(User.id == employee_id)).first()
    return (user.full_name if user else None, row.employee_number)
