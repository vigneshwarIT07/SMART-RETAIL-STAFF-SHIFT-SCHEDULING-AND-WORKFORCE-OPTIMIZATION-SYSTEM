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

from app.core.config import get_settings  # noqa: E402
from app.core.errors import ConflictError  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Attendance,
    AttendanceStatus,
    Employee,
    Shift,
    ShiftAssignment,
    Store,
    User,
)  # noqa: E402
from app.schemas.scheduling import ShiftCreate  # noqa: E402
from app.services import assignment_service, shift_service  # noqa: E402

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
        if existing is not None:
            print("Demo week already seeded for this week — nothing to do.")
            return 0

        created_shifts: list[Shift] = []

        def add_shift(day, start, end, role, required, note=""):
            try:
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
            except ConflictError:
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
                assignment_service.assign_employee(db, shift, emp, assigned_by=manager, force=True)
            except ConflictError as exc:
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

        # -- Attendance history for days already past this week.
        now = datetime.now(UTC)
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
                db.add(
                    Attendance(
                        shift_id=shift.id,
                        employee_id=link.employee_id,
                        attendance_date=shift.shift_date,
                        clock_in=start,
                        clock_out=end,
                        status=AttendanceStatus.PRESENT,
                        worked_minutes=worked,
                        late_minutes=0,
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
