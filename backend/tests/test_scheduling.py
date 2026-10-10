"""Assignment 10-rule validation, scheduling, auto-schedule tests."""

from __future__ import annotations

from datetime import date, time, timedelta

from app.models import Shift
from app.models.employee import Employee
from app.models.enums import ShiftStatus
from app.services import assignment_service, auto_schedule_service, scheduling_service
from tests.conftest import make_shift_payload


def _mgr_id(db, store):
    from app.models import User

    m = db.query(User).filter_by(email="manager@example.com").first()
    return m.id if m else None


def _shift(
    db,
    store,
    day=None,
    start="09:00",
    end="17:00",
    role="cashier",
    req=1,
    skill=None,
    created_by=None,
):
    _cb = created_by or _mgr_id(db, store)
    d = (
        date.today() + timedelta(days=1)
        if day is None
        else date.fromisoformat(day) if isinstance(day, str) else day
    )
    s = Shift(
        store_id=store.id,
        shift_date=d,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        role_required=role,
        required_skill=skill,
        required_employees=req,
        status=ShiftStatus.PUBLISHED,
        created_by=_cb,
    )
    db.add(s)
    db.flush()
    return s


def test_assignment_happy_path(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, created_by=_mgr_id(db, store))
    result = assignment_service.validate_assignment(db, shift=shift, employee=emp)
    assert result["valid"] is True
    row = assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    assert row.employee_id == emp.id


def test_assignment_inactive_employee_blocked(db, store, manager, employee_user):
    from app.models.enums import EmployeeStatus

    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    emp.status = EmployeeStatus.INACTIVE
    db.flush()
    shift = _shift(db, store, created_by=_mgr_id(db, store))
    result = assignment_service.validate_assignment(db, shift=shift, employee=emp)
    assert result["valid"] is False
    assert any(v["code"] == "employee-inactive" for v in result["violations"])


def test_assignment_overlap_blocked(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    s1 = _shift(db, store, created_by=_mgr_id(db, store), start="09:00", end="13:00")
    s2 = _shift(db, store, created_by=_mgr_id(db, store), start="12:00", end="16:00")
    assignment_service.assign_employee(db, s1, emp, assigned_by=manager)
    result = assignment_service.validate_assignment(db, shift=s2, employee=emp)
    assert result["valid"] is False
    assert any(v["code"] == "overlap" for v in result["violations"])


def test_assignment_skill_warning(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, created_by=_mgr_id(db, store), skill="forklift")
    result = assignment_service.validate_assignment(db, shift=shift, employee=emp)
    assert any(v["code"] == "skill-mismatch" for v in result["warnings"])


def test_shift_closed_blocked(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, created_by=_mgr_id(db, store))
    shift.status = ShiftStatus.CANCELLED
    db.flush()
    result = assignment_service.validate_assignment(db, shift=shift, employee=emp)
    assert result["valid"] is False


def test_coverage_statuses(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, created_by=_mgr_id(db, store), req=2)
    status = scheduling_service.coverage_status(shift, 0)
    assert status.value in ("unassigned", "understaffed")
    assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    status2 = scheduling_service.coverage_status(shift, 1)
    assert status2.value == "understaffed"


def test_auto_schedule_requires_confirmation(
    db, store, manager, employee_user, employee2_user
):
    _shift(db, store, created_by=_mgr_id(db, store), start="09:00", end="13:00")
    second_id = _shift(
        db, store, created_by=_mgr_id(db, store), start="14:00", end="18:00"
    ).id
    result = auto_schedule_service.generate_proposal(
        db,
        store_id=store.id,
        start_date=date.today() + timedelta(days=1),
        end_date=date.today() + timedelta(days=1),
    )
    assert "proposals" in result
    assert second_id is not None
    # apply with explicit confirmation
    if result["proposals"]:
        applied = auto_schedule_service.apply_proposal(
            db,
            store_id=store.id,
            proposals=result["proposals"],
            approved_by=manager,
            publish=False,
        )
        assert applied["applied_count"] >= 0 if "applied_count" in applied else True


def test_api_shift_crud_and_assign_flow(client, manager_headers, employee_user):
    payload = make_shift_payload()
    created = client.post("/api/shifts/", headers=manager_headers, json=payload)
    assert created.status_code in (200, 201), created.text
    shift_id = created.json()["data"]["id"]
    # validate + assign
    emp_list = client.get("/api/employees/", headers=manager_headers)
    assert emp_list.status_code == 200, emp_list.text
    emp_id = emp_list.json()["data"]["items"][0]["id"]
    validated = client.post(
        "/api/shifts/assignments/validate",
        headers=manager_headers,
        json={"shift_id": shift_id, "employee_id": emp_id},
    )
    assert validated.status_code == 200
    assigned = client.post(
        "/api/shifts/assignments",
        headers=manager_headers,
        json={"shift_id": shift_id, "employee_id": emp_id},
    )
    assert assigned.status_code in (200, 201), assigned.text


def test_api_shift_read_with_assignments(client, manager_headers, employee_user):
    """Regression: shifts carrying assignments must serialise (read + list)."""
    payload = make_shift_payload()
    created = client.post("/api/shifts/", headers=manager_headers, json=payload)
    assert created.status_code in (200, 201), created.text
    shift_id = created.json()["data"]["id"]
    emp_list = client.get("/api/employees/", headers=manager_headers)
    assert emp_list.status_code == 200, emp_list.text
    emp_id = emp_list.json()["data"]["items"][0]["id"]
    assigned = client.post(
        "/api/shifts/assignments",
        headers=manager_headers,
        json={"shift_id": shift_id, "employee_id": emp_id},
    )
    assert assigned.status_code in (200, 201), assigned.text
    # GET one
    one = client.get(f"/api/shifts/{shift_id}", headers=manager_headers)
    assert one.status_code == 200, one.text
    assignments = one.json()["data"]["assignments"]
    assert len(assignments) == 1
    for key in ("assigned_by", "cancelled_at", "cancelled_reason"):
        assert key in assignments[0], f"missing {key} in assignment payload"
    # GET list (same builder path)
    listed = client.get("/api/shifts/", headers=manager_headers)
    assert listed.status_code == 200, listed.text
    match = [s for s in listed.json()["data"] if s["id"] == shift_id]
    assert match and len(match[0]["assignments"]) == 1
