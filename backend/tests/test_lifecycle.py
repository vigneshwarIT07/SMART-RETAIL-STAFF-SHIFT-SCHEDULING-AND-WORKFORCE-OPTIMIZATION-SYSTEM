"""Shift lifecycle, notifications and email-disabled honesty."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import Employee
from app.models.enums import NotificationType, ShiftStatus
from app.schemas.scheduling import ShiftCreate
from app.services import (
    assignment_service,
    email_service,
    notification_service,
    shift_service,
)


def _parse_hhmm(value):
    from datetime import time as _time

    hour, minute = value.split(":")
    return _time(int(hour), int(minute))


def _draft_shift(db, store, manager, start="09:00", end="17:00"):
    payload = ShiftCreate(
        shift_date=date.today() + timedelta(days=2),
        start_time=_parse_hhmm(start),
        end_time=_parse_hhmm(end),
        role_required="cashier",
        required_employees=1,
        publish=False,
    )
    return shift_service.create_shift(db, store=store, manager=manager, payload=payload)


def test_publish_then_cancel_releases_assignments(db, store, manager, employee_user):
    shift = _draft_shift(db, store, manager)
    assert shift.status == ShiftStatus.DRAFT
    published = shift_service.publish_shifts(
        db, store_id=store.id, manager=manager, shift_ids=[shift.id]
    )
    assert len(published) == 1
    assert shift.status == ShiftStatus.PUBLISHED
    emp = db.get(Employee, employee_user.id)
    link = assignment_service.assign_employee(db, shift, emp, assigned_by=manager)
    assert link.is_active
    shift_service.cancel_shift(db, shift=shift, manager=manager, reason="stocktake")
    assert shift.status == ShiftStatus.CANCELLED
    assert not link.is_active


def test_notification_dedupe_and_read_flow(db, store, manager):
    first = notification_service.create_notification(
        db,
        user_id=manager.id,
        notification_type=NotificationType.ASSIGNMENT,
        title="Rota updated",
        body="The weekly rota changed.",
        dedupe_key="rota:week42",
    )
    retry = notification_service.create_notification(
        db,
        user_id=manager.id,
        notification_type=NotificationType.ASSIGNMENT,
        title="Rota updated",
        body="The weekly rota changed.",
        dedupe_key="rota:week42",
    )
    assert retry.id == first.id  # retried request creates no duplicate
    assert notification_service.unread_count(db, user_id=manager.id).unread >= 1
    notification_service.mark_read(db, user_id=manager.id, notification_id=first.id)
    assert notification_service.unread_count(db, user_id=manager.id).unread == 0


def test_email_renders_and_reports_disabled(db, store, manager):
    subject, body = email_service.render_assignment_email(
        employee_name="Alice",
        shift_date="2026-10-12",
        start_time="09:00",
        end_time="17:00",
        store_name="Demo Store",
    )
    assert "2026-10-12" in subject and "Alice" in body
    # No SMTP in the test environment: delivery must say disabled, never sent.
    outcome = email_service.send_email(to_email="alice@example.com", subject=subject, body=body)
    assert outcome["status"] == "disabled"
    note = notification_service.create_notification(
        db,
        user_id=manager.id,
        notification_type=NotificationType.GENERAL,
        title="Hello",
        body="World",
    )
    result = email_service.deliver_notification(db, note, to_email="manager@example.com")
    assert result["status"] == "disabled"
    assert note.email_status == "disabled"
    # Already-sent rows are never re-sent on retry.
    note.email_status = "sent"
    skipped = email_service.deliver_notification(db, note, to_email="manager@example.com")
    assert skipped.get("duplicate_skipped") is True


def test_api_notifications_roundtrip(client, manager_headers):
    listed = client.get("/api/notifications", headers=manager_headers)
    assert listed.status_code == 200, listed.text
    unread = client.get("/api/notifications/unread-count", headers=manager_headers)
    assert unread.status_code == 200
    assert "unread" in unread.json()["data"]
    read_all = client.post("/api/notifications/read-all", headers=manager_headers)
    assert read_all.status_code == 200
