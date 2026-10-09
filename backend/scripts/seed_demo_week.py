"""Demo-week seeder: fills the CURRENT week with lively rota data.

Creates published shifts for Monday–Sunday of this week, deliberately leaving
some unassigned/understaffed, piling one employee past the overtime threshold,
and adding clock-in/out records plus missing clock-outs — so every dashboard
tile, the coverage list, weekly-hours flags and the attendance review queue
have live database rows behind them.

Idempotency: demo shifts carry the ``[demo-week]`` note tag; if any exist for
the current week the script exits without writing anything.

Safety: refuses to run when ``ENVIRONMENT=production``. Development data only.

Usage (from ``backend/``)::

    $env:DATABASE_URL = "postgresql+psycopg://postgres:DevLocal#2024pg@localhost:5432/retail_scheduling"
    py scripts/seed_demo_week.py
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.errors import ConflictError, NotFoundError  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AssignmentStatus,
    Attendance,
    AttendanceStatus,
    AvailabilityType,
    Employee,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    NotificationType,
    Shift,
    ShiftAssignment,
    ShiftSwapRequest,
    Store,
    User,
)  # noqa: E402
from app.schemas.operations import AvailabilityCreate  # noqa: E402
from app.schemas.scheduling import ShiftCreate  # noqa: E402
from app.services import (  # noqa: E402
    assignment_service,
    availability_service,
    leave_service,
    notification_service,
    shift_service,
    swap_service,
)  # noqa: E402

TAG = "[demo-week]"
STORE_CODE = "DEMO-001"
OVERTIME_STAFFER = "alice@example.com"
ROTATION = [
    "ben@example.com",
    "cara@example.com",
    "dev@example.com",
    "ella@example.com",
    "farid@example.com",
]


def main() -> int:
    settings = get_settings()
    if settings.environment.lower() == "production":
        print("REFUSED: seed_demo_week.py never runs in production.")
        return 1

    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.code == STORE_CODE))
        if store is None:
            print("Run scripts/seed.py first: no DEMO-001 store found.")
            return 1
        manager = db.scalar(select(User).where(User.email == "manager@example.com"))
        if manager is None:
            print("Run scripts/seed.py first: no manager account found.")
            return 1
        staff = {u.email: (u, db.get(Employee, u.id)) for u in db.scalars(select(User)).all()}

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        existing = db.scalar(
            select(Shift).where(
                Shift.store_id == store.id,
                Shift.shift_date >= week_start,
                Shift.shift_date <= week_end,
                Shift.notes.like(f"{TAG}%"),
            )
        )
        created_shifts: list[Shift] = []
        if existing is not None:
            print("Demo week shifts already exist — refreshing side data only.")
            created_shifts = list(
                db.scalars(
                    select(Shift).where(
                        Shift.store_id == store.id,
                        Shift.shift_date >= week_start,
                        Shift.shift_date <= week_end,
                        Shift.notes.like(f"{TAG}%"),
                    )
                ).all()
            )

        def add_shift(day, start, end, role, required, note=""):
            # Pre-check the slot: create_shift rolls back the whole session
            # on duplicates, which must not wipe the rest of the seeding run.
            dup = db.scalar(
                select(Shift).where(
                    Shift.store_id == store.id,
                    Shift.shift_date == day,
                    Shift.start_time == start,
                )
            )
            if dup is not None:
                return None
            try:
                with db.begin_nested():
                    shift = shift_service.create_shift(
                        db,
                        store=store,
                        manager=manager,
                        payload=ShiftCreate(
                            shift_date=day,
                            start_time=start,
                            end_time=end,
                            role_required=role,
                            required_employees=required,
                            notes=f"{TAG} {note}".strip(),
                            publish=True,
                        ),
                    )
            except (ConflictError, NotFoundError, IntegrityError):
                return None
            created_shifts.append(shift)
            return shift

        def assign(shift, email):
            if shift is None:
                return
            user, emp = staff[email]
            if emp is None:
                return
            already = db.scalar(
                select(ShiftAssignment).where(
                    ShiftAssignment.shift_id == shift.id,
                    ShiftAssignment.employee_id == emp.id,
                )
            )
            if already is not None:
                return
            try:
                with db.begin_nested():
                    assignment_service.assign_employee(
                        db, shift, emp, assigned_by=manager, force=True
                    )
            except (ConflictError, NotFoundError, IntegrityError) as exc:
                print(f"  skip assignment {email} on {shift.shift_date}: {exc}")

        # -- Monday..Friday mornings go to the overtime staffer (5 x 8h = 40h).
        # Times deliberately avoid the seed.py slots (09:00, 13:00).
        # Everyone else is capped at ~16 demo hours so only the staffer
        # trips the overtime flag; leftover evening slots stay understaffed.
        demo_load: dict[str, float] = {}
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            morning = add_shift(day, time(7, 30), time(15, 30), "cashier", 1, "morning till cover")
            evening = add_shift(day, time(15, 30), time(23, 30), "floor", 2, "evening floor cover")
            if evening is None:
                continue
            if day == today:
                # Deliberately ragged: morning unassigned, evening short-staffed.
                if evening is not None:
                    evening.required_employees = 2
                    db.flush()
                for slot in (evening,):
                    cover = sorted(ROTATION, key=lambda e: (demo_load.get(e, 0.0), e))[0]
                    if demo_load.get(cover, 0.0) + 8.0 <= 16.0:
                        assign(slot, cover)
                        demo_load[cover] = demo_load.get(cover, 0.0) + 8.0
                    # else: leave the slot empty, another gap for the demo.
            else:
                if offset < 5:
                    assign(morning, OVERTIME_STAFFER)
                    demo_load[OVERTIME_STAFFER] = demo_load.get(OVERTIME_STAFFER, 0.0) + 8.0
                else:
                    weekend = sorted(ROTATION, key=lambda e: (demo_load.get(e, 0.0), e))[0]
                    if demo_load.get(weekend, 0.0) + 8.0 <= 16.0:
                        assign(morning, weekend)
                        demo_load[weekend] = demo_load.get(weekend, 0.0) + 8.0
                    # else: leave the weekend morning unassigned on purpose.
                for candidate in sorted(ROTATION, key=lambda e: (demo_load.get(e, 0.0), e)):
                    # Cap everyone except the overtime staffer at ~16 demo
                    # hours so only one person trips the overtime flag.
                    if demo_load.get(candidate, 0.0) + 8.0 > 16.0:
                        continue
                    before = assignment_service.active_assignment_count(db, evening.id)
                    if before >= (evening.required_employees or 1):
                        break
                    assign(evening, candidate)
                    demo_load[candidate] = demo_load.get(candidate, 0.0) + 8.0

        # An extra midday shift today, left half empty on purpose.
        midday = add_shift(today, time(11, 0), time(15, 0), "stockroom", 2, "stockroom top-up")
        mid_cover = sorted(ROTATION, key=lambda e: (demo_load.get(e, 0.0), e))[0]
        if demo_load.get(mid_cover, 0.0) + 4.0 <= 16.0:
            assign(midday, mid_cover)
            demo_load[mid_cover] = demo_load.get(mid_cover, 0.0) + 4.0

        # -- Attendance history for days already past this week, with variety:
        # on-time, late, absent and excused records.
        now = datetime.now(UTC)
        past_count = 0
        for shift in created_shifts:
            if shift.shift_date >= today:
                continue
            links = assignment_service.list_assignments_for_shift(db, shift.id)
            for link in links:
                start = datetime.combine(shift.shift_date, shift.start_time, tzinfo=UTC)
                end = datetime.combine(shift.shift_date, shift.end_time, tzinfo=UTC)
                if shift.end_time <= shift.start_time:
                    end += timedelta(days=1)
                worked = int((end - start).total_seconds() // 60)
                exists = db.scalar(
                    select(Attendance).where(
                        Attendance.shift_id == shift.id,
                        Attendance.employee_id == link.employee_id,
                    )
                )
                if exists is not None:
                    continue
                past_count += 1
                clock_in, clock_out, status, late = start, end, AttendanceStatus.PRESENT, 0
                if past_count % 7 == 0:
                    clock_in, clock_out, status = None, None, AttendanceStatus.ABSENT
                    worked = 0
                elif past_count % 7 == 6:
                    clock_in, clock_out, status = None, None, AttendanceStatus.EXCUSED
                    worked = 0
                elif past_count % 3 == 0:
                    clock_in = start + timedelta(minutes=25)
                    status, late = AttendanceStatus.LATE, 15
                db.add(
                    Attendance(
                        shift_id=shift.id,
                        employee_id=link.employee_id,
                        attendance_date=shift.shift_date,
                        clock_in=clock_in,
                        clock_out=clock_out,
                        status=status,
                        worked_minutes=worked,
                        late_minutes=late,
                        recorded_by=manager.id,
                    )
                )
        # -- Two missing clock-outs (clocked in hours ago, never out).
        flagged = 0
        for shift in created_shifts:
            if flagged >= 2 or shift.shift_date != today:
                continue
            links = assignment_service.list_assignments_for_shift(db, shift.id)
            if not links:
                continue
            link = links[0]
            exists = db.scalar(
                select(Attendance).where(
                    Attendance.shift_id == shift.id,
                    Attendance.employee_id == link.employee_id,
                )
            )
            if exists is not None:
                continue
            db.add(
                Attendance(
                    shift_id=shift.id,
                    employee_id=link.employee_id,
                    attendance_date=today,
                    clock_in=now - timedelta(hours=5, minutes=20),
                    clock_out=None,
                    status=AttendanceStatus.INCOMPLETE,
                    recorded_by=manager.id,
                )
            )
            flagged += 1

        # -- Leave variety: an approved request next week (no clash with this
        # week's demo shifts), a rejected one this week; seed's pending stays.
        next_monday = week_start + timedelta(days=7)

        def file_leave(email, start, end, kind, reason):
            user, emp = staff[email]
            if emp is None:
                return None
            dup = db.scalar(
                select(LeaveRequest).where(
                    LeaveRequest.employee_id == emp.id,
                    LeaveRequest.start_date == start,
                    LeaveRequest.end_date == end,
                )
            )
            if dup is not None:
                return dup
            try:
                with db.begin_nested():
                    return leave_service.file_request(
                        db,
                        employee=emp,
                        start_date=start,
                        end_date=end,
                        leave_type=kind,
                        reason=reason,
                    )
            except (ConflictError, NotFoundError, IntegrityError) as exc:
                print(f"  skip leave {email}: {exc}")
                return None

        def decide_leave(req, verdict, note):
            if req is None or req.status != LeaveStatus.PENDING:
                return
            try:
                with db.begin_nested():
                    leave_service.decide_request(
                        db, request=req, reviewer=manager, decision=verdict, review_note=note
                    )
            except (ConflictError, NotFoundError, IntegrityError) as exc:
                print(f"  skip leave decision: {exc}")

        approved_leave = file_leave(
            "alice@example.com",
            next_monday,
            next_monday + timedelta(days=2),
            LeaveType.ANNUAL,
            "Demo: family trip next week",
        )
        decide_leave(approved_leave, "approved", "Demo approval — enjoy the trip")
        rejected_leave = file_leave(
            "dev@example.com",
            week_start + timedelta(days=3),
            week_start + timedelta(days=4),
            LeaveType.SICK,
            "Demo: cover needed, declined",
        )
        decide_leave(rejected_leave, "rejected", "Demo rejection — rota too tight")

        # -- Swap variety: approve one double-swap between demo shifts, reject
        # another. Anything ineligible is left pending for the manager queue.
        tagged_ids = [s.id for s in created_shifts]
        cand = (
            db.scalars(
                select(ShiftAssignment)
                .where(
                    ShiftAssignment.shift_id.in_(tagged_ids),
                    ShiftAssignment.status == AssignmentStatus.ASSIGNED,
                )
                .order_by(ShiftAssignment.employee_id)
            ).all()
            if tagged_ids
            else []
        )
        first_link: dict[str, ShiftAssignment] = {}
        for link in cand:
            first_link.setdefault(link.employee_id, link)
        owners = list(first_link)
        pairs = []
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = first_link[owners[i]], first_link[owners[j]]
                if a.shift_id != b.shift_id:
                    pairs.append((owners[i], a, owners[j], b))

        def file_swap(e1, a, e2, b):
            dup = db.scalar(
                select(ShiftSwapRequest).where(
                    ShiftSwapRequest.requester_id == e1,
                    ShiftSwapRequest.requester_shift_id == a.shift_id,
                    ShiftSwapRequest.target_shift_id == b.shift_id,
                )
            )
            if dup is not None:
                return dup
            requester = db.get(Employee, e1)
            if requester is None:
                return None
            try:
                with db.begin_nested():
                    return swap_service.create_request(
                        db,
                        requester=requester,
                        target_employee_id=e2,
                        requester_shift_id=a.shift_id,
                        target_shift_id=b.shift_id,
                        reason="Demo: swap evenings with a teammate",
                    )
            except (ConflictError, NotFoundError, IntegrityError) as exc:
                print(f"  skip demo swap: {exc}")
                return None

        def decide_swap(swap, verdict, note):
            if swap is None or swap.status.value != "pending":
                return False
            try:
                with db.begin_nested():
                    swap_service.decide_request(
                        db, swap=swap, reviewer=manager, decision=verdict, review_note=note
                    )
            except (ConflictError, NotFoundError, IntegrityError) as exc:
                print(f"  demo swap stays pending: {exc}")
                return False
            return True

        if pairs:
            e1, a, e2, b = pairs[0]
            decide_swap(file_swap(e1, a, e2, b), "approved", "Demo approval")
        if len(pairs) > 1:
            e1, a, e2, b = pairs[1]
            decide_swap(file_swap(e1, a, e2, b), "rejected", "Demo rejection")

        # -- Availability windows so the Availability page has content.
        for index, email in enumerate(["alice@example.com", *ROTATION]):
            user, emp = staff[email]
            if emp is None:
                continue
            windows = [
                (
                    index % 7,
                    time(8, 0),
                    time(20, 0),
                    AvailabilityType.AVAILABLE,
                    "Demo: generally available",
                ),
                (
                    (index + 3) % 7,
                    time(8, 0),
                    time(20, 0),
                    AvailabilityType.UNAVAILABLE,
                    "Demo: regular day off",
                ),
            ]
            for weekday, start_t, end_t, kind, note in windows:
                try:
                    with db.begin_nested():
                        availability_service.create_availability(
                            db,
                            employee=emp,
                            user=user,
                            payload=AvailabilityCreate(
                                weekday=weekday,
                                start_time=start_t,
                                end_time=end_t,
                                availability_type=kind,
                                note=note,
                            ),
                        )
                except (ConflictError, NotFoundError, IntegrityError):
                    continue

        # -- Notifications: dedupe keys make re-runs return existing rows.
        alice_user, _ = staff["alice@example.com"]
        for user_id, kind, title, body, key in [
            (
                manager.id,
                NotificationType.LEAVE_REQUEST,
                "Leave request filed",
                "Demo: Alice requested annual leave for next week.",
                "demo:leave-filed",
            ),
            (
                manager.id,
                NotificationType.SWAP_REQUEST,
                "Swap request filed",
                "Demo: an evening swap needs review.",
                "demo:swap-filed",
            ),
            (
                alice_user.id,
                NotificationType.SCHEDULE_PUBLISHED,
                "Schedule published",
                "Demo: this week's rota is published.",
                "demo:sched-published",
            ),
            (
                alice_user.id,
                NotificationType.LEAVE_DECISION,
                "Leave approved",
                "Demo: your annual leave was approved.",
                "demo:leave-approved",
            ),
        ]:
            notification_service.create_notification(
                db,
                user_id=user_id,
                notification_type=kind,
                title=title,
                body=body,
                dedupe_key=key,
            )

        db.commit()
        print(
            f"Demo week seeded: {len(created_shifts)} shifts for "
            f"{week_start}..{week_end}, overtime pile on {OVERTIME_STAFFER}, "
            f"{flagged} missing clock-out(s)."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
