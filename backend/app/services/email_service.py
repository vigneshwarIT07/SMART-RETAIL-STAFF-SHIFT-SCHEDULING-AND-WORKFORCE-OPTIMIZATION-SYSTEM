"""Email generation and delivery.

Generation (``render_*``) is pure and unit-testable: it never touches the
network. Delivery (``send_email`` / ``deliver_notification``) is the only
code that opens an SMTP connection.

When no SMTP host is configured the application keeps working and honestly
reports ``\"disabled\"`` — it never pretends an email was delivered.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.notification import Notification


def render_assignment_email(
    *, employee_name: str, shift_date: str, start_time: str, end_time: str, store_name: str
) -> tuple[str, str]:
    """Render the subject and body for a shift-assignment email."""

    subject = f"New shift assigned: {shift_date} {start_time}-{end_time}"
    body = (
        f"Hi {employee_name},\n\n"
        f"You have been assigned a shift at {store_name} on {shift_date} "
        f"from {start_time} to {end_time}.\n\n"
        "Please confirm the shift in the scheduling app. "
        "Contact your manager if you cannot work this shift.\n"
    )
    return subject, body


def render_schedule_published_email(
    *, employee_name: str, week_start: str, week_end: str, shift_count: int, store_name: str
) -> tuple[str, str]:
    """Render the subject and body for a schedule-published email."""

    subject = f"Schedule published for {week_start} - {week_end}"
    body = (
        f"Hi {employee_name},\n\n"
        f"The schedule for {week_start} to {week_end} at {store_name} has been "
        f"published. You have {shift_count} shift(s) this week.\n\n"
        "Please review your shifts in the scheduling app.\n"
    )
    return subject, body


def render_leave_decision_email(
    *, employee_name: str, decision: str, start_date: str, end_date: str, review_note: str | None
) -> tuple[str, str]:
    """Render the subject and body for a leave-decision email."""

    subject = f"Leave request {decision}: {start_date} to {end_date}"
    body = (
        f"Hi {employee_name},\n\n"
        f"Your leave request from {start_date} to {end_date} was {decision}.\n"
    )
    if review_note:
        body += f"Manager note: {review_note}\n"
    return subject, body


def render_swap_decision_email(
    *, employee_name: str, decision: str, details: str, review_note: str | None
) -> tuple[str, str]:
    """Render the subject and body for a swap-decision email."""

    subject = f"Shift swap {decision}"
    body = f"Hi {employee_name},\n\nYour shift swap request ({details}) was {decision}.\n"
    if review_note:
        body += f"Manager note: {review_note}\n"
    return subject, body


def send_email(*, to_email: str, subject: str, body: str, timeout: int = 10) -> dict[str, Any]:
    """Deliver one email, or honestly report that delivery is disabled.

    Returns a mapping with at least ``status`` which is one of
    ``\"sent\"``, ``\"disabled\"`` or ``\"failed\"``. A failure also carries
    an ``error`` message. A failure here must never corrupt scheduling data;
    callers record the outcome on the notification row and continue.
    """

    settings = get_settings()
    if not settings.email_enabled:
        return {
            "status": "disabled",
            "error": "EMAIL_HOST is not configured; delivery is disabled.",
        }
    message = EmailMessage()
    message["From"] = settings.email_from or settings.email_username or "no-reply@localhost"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        if settings.email_use_tls:
            server: smtplib.SMTP = smtplib.SMTP(
                settings.email_host, settings.email_port, timeout=timeout
            )
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(
                settings.email_host, settings.email_port, timeout=timeout
            )
        with server:
            if settings.email_username:
                server.login(settings.email_username, settings.email_password or "")
            server.send_message(message)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return {"status": "failed", "error": str(exc)}
    return {"status": "sent"}


def deliver_notification(
    db: Session, notification: Notification, *, to_email: str | None
) -> dict[str, Any]:
    """Deliver the email half of a notification exactly once.

    Notifications whose ``email_status`` is already ``\"sent\"`` are skipped
    so that retried requests never send duplicates. Returns the outcome of
    :func:`send_email`.
    """

    if notification.email_status == "sent":
        return {"status": "sent", "duplicate_skipped": True}
    if not to_email:
        notification.email_status = "failed"
        notification.email_error = "recipient has no email address on file"
        db.flush()
        return {"status": "failed", "error": notification.email_error}
    outcome = send_email(
        to_email=to_email, subject=notification.title, body=notification.body or ""
    )
    notification.email_status = (
        "sent" if outcome["status"] == "sent" else outcome["status"]
    )
    notification.email_error = outcome.get("error")
    db.flush()
    return outcome
