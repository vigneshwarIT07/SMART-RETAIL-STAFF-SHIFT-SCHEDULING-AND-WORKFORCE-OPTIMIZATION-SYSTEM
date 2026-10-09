"""Scheduling routes: calendar, coverage, reports, auto-schedule proposals."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_managed_store_id, require_manager
from app.core.errors import success
from app.db.session import get_db
from app.models import User
from app.schemas.scheduling import ApplyGenerationRequest, GenerationRequest
from app.services import auto_schedule_service, scheduling_service

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


@router.get("/calendar")
def read_calendar(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return day buckets with shifts + assignments for a date range."""
    weeks = scheduling_service.calendar_weeks(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(
        data=jsonable_encoder(
            {"start_date": start_date, "end_date": end_date, "days": weeks}
        ),
        message="Calendar",
    )


@router.get("/coverage")
def read_coverage(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return per-shift coverage rows plus a summary."""
    rows = scheduling_service.week_coverage(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    summary = scheduling_service.coverage_summary(rows)
    return success(
        data=jsonable_encoder(
            {
                "start_date": start_date,
                "end_date": end_date,
                "rows": rows,
                "summary": summary,
            }
        ),
        message="Coverage",
    )


@router.get("/report")
def read_report(
    start_date: date = Query(),
    end_date: date = Query(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Working-hours + fairness + conflict scheduling report."""
    hours = scheduling_service.weekly_hours_report(
        db, store_id=current_user.store_id, week_start=start_date
    )
    fairness = scheduling_service.fairness_report(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    conflicts = scheduling_service.conflict_list(
        db, store_id=current_user.store_id, start_date=start_date, end_date=end_date
    )
    return success(
        data=jsonable_encoder(
            {
                "start_date": start_date,
                "end_date": end_date,
                "weekly_hours": hours,
                "fairness": fairness,
                "conflicts": conflicts,
            }
        ),
        message="Scheduling report",
    )


@router.post("/generate")
def generate_proposal(
    payload: GenerationRequest,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Build a deterministic scheduling proposal (NOT applied until confirmed)."""
    result = auto_schedule_service.generate_proposal(
        db,
        store_id=get_managed_store_id(manager),
        start_date=payload.start_date,
        end_date=payload.end_date,
        employee_ids=payload.employee_ids,
    )
    return success(data=jsonable_encoder(result), message="Proposal generated")


@router.post("/apply")
def apply_proposal(
    payload: ApplyGenerationRequest,
    request: Request,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> dict:
    """Apply a manager-confirmed proposal (revalidates every entry first)."""
    _ = request
    result = auto_schedule_service.apply_proposal(
        db,
        store_id=get_managed_store_id(manager),
        proposals=[p.model_dump(mode="json") for p in payload.proposals],
        approved_by=manager,
        publish=payload.publish,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return success(data=jsonable_encoder(result), message="Proposal applied")
