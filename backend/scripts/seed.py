"""Idempotent development seed script.

Creates one demo store, a manager account, several employees, two weeks of
shifts with assignments, availability, attendance, leave and a swap request.

Idempotency: every piece is created only when it does not already exist, so
re-running the script never duplicates rows.

Safety: refuses to run when ``ENVIRONMENT=production``. Demo credentials are
for local development only and are clearly labelled as such — never use them
in production.

Usage (from ``backend/``)::

    $env:DATABASE_URL = "postgresql+psycopg://postgres:DevLocal#2024pg@localhost:5432/retail_scheduling"
    py scripts/seed.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AvailabilityType,
    Employee,
    LeaveType,
    Shift,
    Store,
    User,
    UserRole,
)
from app.schemas.employee import EmployeeCreate  # noqa: E402
from app.schemas.scheduling import ShiftCreate  # noqa: E402
from app.services import (  # noqa: E402
    assignment_service,
    attendance_service,
    availability_service,
    employee_service,
    leave_service,
    shift_service,
    swap_service,
)

STORE_CODE = "DEMO-001"
# Development-only demo credentials. Never valid outside a local database.
MANAGER_EMAIL = "manager@example.com"
MANAGER_PASSWORD = os.environ.get("SEED_MANAGER_PASSWORD", "Manager123!")
EMPLOYEE_PASSWORD = os.environ.get("SEED_EMPLOYEE_PASSWORD", "Employee123!")

EMPLOYEES = [
    ("alice@example.com", "Alice Carter", "EMP-1001", "senior", ["cashier", "floor"]),
    ("ben@example.com", "Ben Okafor", "EMP-1002", "mid", ["cashier", "stockroom"]),
    ("cara@example.com", "Cara Mendes", "EMP-1003", "junior", ["floor"]),
    ("dev@example.com", "Dev Patel", "EMP-1004", "mid", ["stockroom", "floor"]),
    ("ella@example.com", "Ella Novak", "EMP-1005", "junior", ["cashier"]),
    ("farid@example.com", "Farid Hassan", "EMP-1006", "senior", ["floor", "stockroom"]),
]

SKILL_LEVELS = {"junior": "JUNIOR", "mid": "MID", "senior": "SENIOR"}


def main() -> None:
    """Seed the development database idempotently."""
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to seed: ENVIRONMENT=production.")
    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.code == STORE_CODE))
        if store is None:
            store = Store(
                name="Maple Street Retail",
                code=STORE_CODE,
                address="12 Maple Street",
                phone="555-0100",
                timezone="UTC",
                is_active=True,
            )
            db.add(store)
            db.commit()
            db.refresh(store)
            print(f"created store {store.code}")
        else:
            print(f"store {store.code} already exists — reusing")

        manager = db.scalar(select(User).where(User.email == MANAGER_EMAIL))
        if manager is None:
            manager = User(
                email=MANAGER_EMAIL,
                hashed_password=hash_password(MANAGER_PASSWORD),
                full_name="Demo Store Manager",
                role=UserRole.MANAGER,
                store_id=store.id,
                is_active=True,
            )
            db.add(manager)
            db.commit()
            print("created manager manager@example.com / Manager123! (DEV ONLY)")
        else:
            print("manager already exists — reusing")

        employees: list[Employee] = []
        for email, name, number, level, skills in EMPLOYEES:
            existing = db.scalar(select(User).where(User.email == email))
            if existing is not None:
                employee = db.get(Employee, existing.id)
                assert employee is not None
                employees.append(employee)
                continue
            from app.models import SkillLevel

            payload = EmployeeCreate(
                email=email,
                full_name=name,
                password=EMPLOYEE_PASSWORD,
                employee_number=number,
                skill_level=SkillLevel[SKILL_LEVELS[level]],
                skills=skills,
                contract_weekly_hours=40,
            )
            _, employee = employee_service.create_employee(
                db, store_id=store.id, payload=payload, created_by=manager
            )
            db.commit()
            employees.append(employee)
            print(f"created employee {name} ({number})")

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        shift_ids: list[str] = []
        for week_offset in (-1, 0):
            week_start = monday + timedelta(days=7 * week_offset)
            for day in range(6):  # Monday..Saturday
                shift_date = week_start + timedelta(days=day)
                for start, end, role, skill in (
                    (time(9, 0), time(13, 0), "cashier", "cashier"),
                    (time(13, 0), time(17, 0), "floor", "floor"),
                ):
                    payload = ShiftCreate(
                        shift_date=shift_date,
                        start_time=start,
                        end_time=end,
                        role_required=role,
                        required_skill=skill,
                        required_employees=2,
                        notes=None,
                        publish=True,
                    )
                    try:
                        shift = shift_service.create_shift(
                            db, store=store, manager=manager, payload=payload
                        )
                        db.commit()
                        shift_ids.append(shift.id)
                    except Exception as exc:  # duplicate slot on re-seed
                        db.rollback()
                        existing = db.scalar(
                            select(Shift).where(
                                Shift.store_id == store.id,
                                Shift.shift_date == shift_date,
                                Shift.start_time == start,
                            )
                        )
                        if existing is None:
                            raise exc
                        shift_ids.append(existing.id)
        print(f"shifts ready: {len(shift_ids)}")

        shifts = [db.get(Shift, sid) for sid in shift_ids]
        shifts = [s for s in shifts if s is not None]
        for index, shift in enumerate(shifts):
            for pick in (index % len(employees), (index + 2) % len(employees)):
                employee = employees[pick]
                try:
                    assignment_service.assign_employee(
                        db,
                        shift=shift,
                        employee=employee,
                        assigned_by=manager,
                        force=True,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
        print("assignments ready")

        for employee in employees[:3]:
            from app.schemas.operations import AvailabilityCreate

            try:
                availability_service.create_availability(
                    db,
                    employee=employee,
                    user=manager,
                    payload=AvailabilityCreate(
                        weekday=6,
                        start_time=time(0, 0),
                        end_time=time(23, 59),
                        availability_type=AvailabilityType.UNAVAILABLE,
                        note="Sundays off",
                    ),
                )
                db.commit()
            except Exception:
                db.rollback()
        print("availability ready")

        past = [s for s in shifts if s.shift_date < today]
        for shift in past[:6]:
            assignments = assignment_service.list_assignments_for_shift(
                db, shift_id=shift.id
            )
            for assignment in assignments[:1]:
                employee = db.get(Employee, assignment.employee_id)
                if employee is None:
                    continue
                try:
                    start_dt = datetime.combine(shift.shift_date, shift.start_time)
                    attendance_service.clock_in(
                        db,
                        shift=shift,
                        employee=employee,
                        recorded_by=manager,
                        at=start_dt + timedelta(minutes=3),
                    )
                    db.commit()
                    attendance_service.clock_out(
                        db,
                        shift=shift,
                        employee=employee,
                        recorded_by=manager,
                        at=datetime.combine(shift.shift_date, shift.end_time),
                    )
                    db.commit()
                except Exception:
                    db.rollback()
        print("attendance ready")

        emp0, emp1 = employees[0], employees[1]
        try:
            leave_service.file_request(
                db,
                employee=emp0,
                start_date=today + timedelta(days=14),
                end_date=today + timedelta(days=15),
                leave_type=LeaveType.ANNUAL,
                reason="Family trip",
            )
            db.commit()
            print("leave request ready")
        except Exception:
            db.rollback()

        emp_shifts_a = db.scalars(
            select(Shift)
            .join(
                assignment_service.ShiftAssignment,
                assignment_service.ShiftAssignment.shift_id == Shift.id,
            )
            .where(
                assignment_service.ShiftAssignment.employee_id == emp0.id,
                Shift.shift_date >= today,
            )
        ).all()
        emp_shifts_b = db.scalars(
            select(Shift)
            .join(
                assignment_service.ShiftAssignment,
                assignment_service.ShiftAssignment.shift_id == Shift.id,
            )
            .where(
                assignment_service.ShiftAssignment.employee_id == emp1.id,
                Shift.shift_date >= today,
            )
        ).all()
        if emp_shifts_a and emp_shifts_b:
            try:
                swap_service.create_request(
                    db,
                    requester=emp0,
                    target_employee_id=emp1.id,
                    requester_shift_id=emp_shifts_a[0].id,
                    target_shift_id=emp_shifts_b[0].id,
                    reason="Doctor appointment",
                )
                db.commit()
                print("swap request ready")
            except Exception:
                db.rollback()

        print("seed complete (idempotent — safe to re-run)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
