"""Report routes: dashboard metrics, working hours, fairness, exports.

Every figure is computed from live database rows. CSV exports stream a real
``text/csv`` response so managers can open the data in a spreadsheet.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_manager
from app.core.errors import success
from app.db.session import get_db
from app.models import User
from app.services import report_service, scheduling_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard")
def read_dashboard(
    today: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Eight database-derived metrics for the manager dashboard."""
    metrics = report_service.dashboard_metrics(
        db, store_id=current_user.store_id, today=today or date.today()
    )
    return success(data=jsonable_encoder(metrics), message="Dashboard metrics")


@router.get("/summary")
def read_summary(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Compact store summary for the reporting period."""
    summary = report_service.store_summary(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(data=jsonable_encoder(summary), message="Store summary")


@router.get("/working-hours")
def read_working_hours(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Scheduled vs actually-worked hours per employee."""
    rows = report_service.working_hours_report(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(data=jsonable_encoder(rows), message="Working hours report")


@router.get("/weekly-hours")
def read_weekly_hours(
    week_start: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Weekly scheduled hours per employee with overtime flags."""
    rows = scheduling_service.weekly_hours_report(
        db, store_id=current_user.store_id, week_start=week_start
    )
    return success(data=jsonable_encoder(rows), message="Weekly hours report")


@router.get("/fairness")
def read_fairness(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Shift-count spread per employee for the period."""
    rows = scheduling_service.fairness_report(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(data=jsonable_encoder(rows), message="Fairness report")


@router.get("/conflicts")
def read_conflicts(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Assignments that violate a rule, each needing explicit resolution."""
    rows = scheduling_service.conflict_list(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(data=jsonable_encoder(rows), message="Scheduling conflicts")


@router.get("/leave")
def read_leave_breakdown(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Approved leave days grouped by employee and leave type."""
    rows = report_service.leave_breakdown(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(data=jsonable_encoder(rows), message="Leave breakdown")


@router.get("/export/{kind}")
def export_report(
    kind: str,
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> Response:
    """Download a report as a real CSV file.

    ``kind`` is one of ``working-hours``, ``weekly-hours``, ``fairness``,
    ``coverage``, ``leave`` or ``attendance``.
    """
    store_id = current_user.store_id
    if kind == "working-hours":
        rows = report_service.working_hours_report(
            db, store_id=store_id, start_date=start_date, end_date=end_date
        )
    elif kind == "weekly-hours":
        rows = scheduling_service.weekly_hours_report(
            db, store_id=store_id, week_start=start_date
        )
    elif kind == "fairness":
        rows = scheduling_service.fairness_report(
            db, store_id=store_id, start_date=start_date, end_date=end_date
        )
    elif kind == "coverage":
        rows = scheduling_service.week_coverage(
            db, store_id=store_id, start_date=start_date, end_date=end_date
        )
    elif kind == "leave":
        rows = report_service.leave_breakdown(
            db, store_id=store_id, start_date=start_date, end_date=end_date
        )
    elif kind == "attendance":
        from app.services import attendance_service

        rows = [
            {
                "id": record.id,
                "attendance_date": record.attendance_date,
                "employee_id": record.employee_id,
                "shift_id": record.shift_id,
                "clock_in": record.clock_in,
                "clock_out": record.clock_out,
                "status": record.status,
                "worked_minutes": record.worked_minutes,
                "late_minutes": record.late_minutes,
            }
            for record in attendance_service.list_records(
                db, store_id=store_id, start=start_date, end=end_date
            )
        ]
    else:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Unknown export kind '{kind}'.")
    payload = report_service.build_export(kind, rows)
    return Response(
        content=payload["csv_text"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{payload["filename"]}"'},
    )
