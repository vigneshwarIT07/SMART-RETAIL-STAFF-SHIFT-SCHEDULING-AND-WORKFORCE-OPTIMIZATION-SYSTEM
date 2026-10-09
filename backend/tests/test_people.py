"""Availability windows and employee provisioning (service + API level)."""

from __future__ import annotations

from datetime import time

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models import Employee
from app.schemas.employee import EmployeeCreate
from app.schemas.operations import AvailabilityCreate
from app.services import availability_service, employee_service


def _emp(db, user):
    emp = db.get(Employee, user.id)
    assert emp is not None
    return emp


def test_availability_crud_and_duplicate_rejected(db, store, manager, employee_user):
    emp = _emp(db, employee_user)
    payload = AvailabilityCreate(weekday=0, start_time=time(9, 0), end_time=time(17, 0))
    row = availability_service.create_availability(
        db, employee=emp, user=employee_user, payload=payload
    )
    assert row.id is not None
    rows = availability_service.list_availability(db, employee=emp, user=employee_user)
    assert len(rows) == 1
    # Same weekday + start time is a duplicate slot (savepoint keeps the first row).
    with pytest.raises(ConflictError), db.begin_nested():
        availability_service.create_availability(
            db, employee=emp, user=employee_user, payload=payload
        )
    availability_service.delete_availability(db, row=row, employee=emp, user=employee_user)
    assert availability_service.list_availability(db, employee=emp, user=employee_user) == []


def test_availability_cross_employee_forbidden(db, store, manager, employee_user, employee2_user):
    emp2 = _emp(db, employee2_user)
    payload = AvailabilityCreate(weekday=2, start_time=time(9, 0), end_time=time(12, 0))
    # A plain employee cannot manage another employee's rows.
    with pytest.raises(NotFoundError):
        availability_service.create_availability(
            db, employee=emp2, user=employee_user, payload=payload
        )
    db.rollback()
    # A manager of the same store can.
    row = availability_service.create_availability(db, employee=emp2, user=manager, payload=payload)
    assert row.employee_id == emp2.id


def test_employee_provisioning_and_deactivation(db, store, manager):
    payload = EmployeeCreate(
        email="newhire@example.com", full_name="New Hire", password="Password123!"
    )
    user, emp = employee_service.create_employee(
        db, store_id=store.id, payload=payload, created_by=manager
    )
    assert emp.employee_number.startswith("EMP-")
    assert user.is_active and emp.is_active
    # Duplicate email is rejected without touching the provisioned rows.
    with pytest.raises(ConflictError), db.begin_nested():
        employee_service.create_employee(db, store_id=store.id, payload=payload, created_by=manager)
    user, emp = employee_service.deactivate_employee(
        db, user=user, employee=emp, deactivated_by=manager
    )
    assert not user.is_active and not emp.is_active
    db.flush()
    assert db.get(Employee, emp.id).status.value == "inactive"


def test_api_employee_create_and_deactivate(client, manager_headers):
    created = client.post(
        "/api/employees",
        headers=manager_headers,
        json={
            "email": "apihire@example.com",
            "full_name": "API Hire",
            "password": "Password123!",
        },
    )
    assert created.status_code == 201, created.text
    emp_id = created.json()["data"]["id"]
    deactivated = client.post(f"/api/employees/{emp_id}/deactivate", headers=manager_headers)
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["data"]["status"] == "inactive"
