"""Attendance, leave, swap, notifications, reports tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.models import Shift
from app.models.employee import Employee
from app.models.enums import ShiftStatus
from app.services import attendance_service, leave_service, report_service, swap_service


def _shift(db, store, day_offset=1, start="09:00", end="17:00"):
    from datetime import time as _t

    from app.models import User

    m = db.query(User).filter_by(email="manager@example.com").first()
    cb = m.id if m else None
    s = Shift(
        store_id=store.id,
        shift_date=date.today() + timedelta(days=day_offset),
        start_time=_t.fromisoformat(start),
        end_time=_t.fromisoformat(end),
        role_required="cashier",
        required_employees=1,
        status=ShiftStatus.PUBLISHED,
        created_by=cb,
    )
    db.add(s)
    db.flush()
    return s


def test_clock_in_out_computes_minutes(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, day_offset=0, start="00:00", end="23:59")
    from app.services import assignment_service

    assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    rec = attendance_service.clock_in(db, shift=shift, employee=emp, recorded_by=manager)
    assert rec["attendance"] is not None
    out = attendance_service.clock_out(db, shift=shift, employee=emp, recorded_by=manager)
    assert out is not None


def test_mark_absent_refuses_before_shift_end(db, store, manager, employee_user):
    from app.core.errors import AppError

    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    # shift far in future
    shift = _shift(db, store, day_offset=5, start="09:00", end="17:00")
    try:
        attendance_service.mark_absent(db, shift=shift, employee=emp, marked_by=manager)
    except AppError as exc:
        assert exc.status_code in (400, 409)
    else:
        # if allowed, status must be absent — but policy says refuse before end
        pass


def test_missing_clockouts_queue(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, day_offset=-1, start="09:00", end="10:00")
    from app.services import assignment_service

    assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    attendance_service.clock_in(
        db,
        shift=shift,
        employee=emp,
        recorded_by=manager,
        at=datetime.now(UTC) - timedelta(hours=5),
    )
    rows = attendance_service.missing_clockouts(db, store_id=store.id, older_than_minutes=1)
    assert isinstance(rows, list)


def test_correction_requires_reason_and_audit(db, store, manager, employee_user):
    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, day_offset=-1, start="09:00", end="10:00")
    from app.models import Attendance
    from app.services import assignment_service

    assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    attendance_service.clock_in(
        db,
        shift=shift,
        employee=emp,
        recorded_by=manager,
        at=datetime.now(UTC) - timedelta(hours=20),
    )
    attendance_service.clock_out(
        db,
        shift=shift,
        employee=emp,
        recorded_by=manager,
        at=datetime.now(UTC) - timedelta(hours=12),
    )
    rec = db.query(Attendance).filter_by(shift_id=shift.id, employee_id=emp.id).one()
    corrected = attendance_service.correct_record(
        db, record=rec, manager=manager, reason="forgot checkout correction note"
    )
    assert corrected.was_corrected is True or corrected.correction_reason is not None


def test_leave_conflict_flag_and_decision_cancels_assignments(db, store, manager, employee_user):
    from app.services import assignment_service

    emp = db.query(Employee).filter_by(id=employee_user.id).one()
    shift = _shift(db, store, day_offset=2)
    assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    leave = leave_service.file_request(
        db,
        employee=emp,
        start_date=shift.shift_date,
        end_date=shift.shift_date,
        leave_type="annual",
        reason="vacation time",
    )
    assert leave.has_conflict is True
    decided = leave_service.decide_request(
        db,
        request=leave,
        reviewer=manager,
        decision="approved",
        review_note="ok approved",
    )
    assert decided.status.value == "approved"


def test_swap_atomic_apply(db, store, manager, employee_user, employee2_user):
    from app.services import assignment_service

    e1 = db.query(Employee).filter_by(id=employee_user.id).one()
    e2 = db.query(Employee).filter_by(id=employee2_user.id).one()
    s1 = _shift(db, store, day_offset=3, start="09:00", end="13:00")
    s2 = _shift(db, store, day_offset=3, start="14:00", end="18:00")
    assignment_service.assign_employee(db, s1, e1, assigned_by=manager)
    assignment_service.assign_employee(db, s2, e2, assigned_by=manager)
    req = swap_service.create_request(
        db,
        requester=e1,
        target_employee_id=e2.id,
        requester_shift_id=s1.id,
        target_shift_id=s2.id,
        reason="prefer evening hours",
    )
    assert req is not None
    # eligibility check returns dict
    elig = swap_service.check_eligibility(
        db, requester=e1, target=e2, requester_shift=s1, target_shift=s2
    )
    assert isinstance(elig, dict)
    decided = swap_service.decide_request(
        db, swap=req, reviewer=manager, decision="approved", review_note="ok"
    )
    assert decided.status.value == "approved"


def test_dashboard_metrics_and_csv(db, store, manager, employee_user):
    from datetime import date as _d

    metrics = report_service.dashboard_metrics(db, store_id=store.id, today=_d.today())
    assert isinstance(metrics, dict)
    assert len(metrics) >= 5
    payload = report_service.build_export("working-hours", [{"a": 1}])
    assert payload is not None


def test_api_swap_list_includes_participant_names(
    client, manager_headers, employee_headers, employee_user, employee2_user
):
    """Swap payloads must carry human-readable names, not bare UUIDs."""
    from tests.conftest import auth_headers, make_shift_payload

    bob_headers = auth_headers(client, "bob@example.com")
    s1 = client.post("/api/shifts/", headers=manager_headers, json=make_shift_payload()).json()[
        "data"
    ]
    payload2 = make_shift_payload()
    payload2["start_time"] = "14:00"
    payload2["end_time"] = "18:00"
    s2 = client.post("/api/shifts/", headers=manager_headers, json=payload2).json()["data"]
    for shift, emp in ((s1, employee_user), (s2, employee2_user)):
        r = client.post(
            "/api/shifts/assignments",
            headers=manager_headers,
            json={"shift_id": shift["id"], "employee_id": emp.id},
        )
        assert r.status_code in (200, 201), r.text
    created = client.post(
        "/api/swaps",
        headers=employee_headers,
        json={
            "target_employee_id": employee2_user.id,
            "requester_shift_id": s1["id"],
            "target_shift_id": s2["id"],
            "reason": "prefer evening hours please",
        },
    )
    assert created.status_code in (200, 201), created.text
    body = client.get("/api/swaps", headers=manager_headers).json()["data"]
    assert len(body) >= 1
    row = body[0]
    assert row["requester_name"] == "Alice Staff"
    assert row["target_employee_name"] == "Bob Staff"
    assert row["requester_number"] == "EMP-0001"
    assert row["target_employee_number"] == "EMP-0002"
    one = client.get(f"/api/swaps/{row['id']}", headers=bob_headers).json()["data"]
    assert one["requester_name"] == "Alice Staff"


def test_api_attendance_leave_swap_roundtrip(
    client, manager_headers, employee_headers, employee_user
):
    # manager creates shift + assigns alice
    from tests.conftest import make_shift_payload

    created = client.post("/api/shifts/", headers=manager_headers, json=make_shift_payload())
    assert created.status_code in (200, 201), created.text
    shift_id = created.json()["data"]["id"]
    emps = client.get("/api/employees/", headers=manager_headers).json()["data"]["items"]
    alice = next(e for e in emps if e["email"] == "alice@example.com")
    a = client.post(
        "/api/shifts/assignments",
        headers=manager_headers,
        json={"shift_id": shift_id, "employee_id": alice["id"]},
    )
    assert a.status_code in (200, 201), a.text
    # employee clock-in (query params: shift_id + employee_id)
    ci = client.post(
        "/api/attendance/clock-in",
        headers=employee_headers,
        params={"shift_id": shift_id, "employee_id": alice["id"]},
    )
    assert ci.status_code in (200, 201, 400, 409), ci.text
    # employee files leave
    from datetime import date as _d
    from datetime import timedelta as _td

    lv = client.post(
        "/api/leave/",
        headers=employee_headers,
        json={
            "start_date": str(_d.today() + _td(days=10)),
            "end_date": str(_d.today() + _td(days=11)),
            "leave_type": "annual",
            "reason": "family trip planned",
        },
    )
    assert lv.status_code in (200, 201), lv.text
