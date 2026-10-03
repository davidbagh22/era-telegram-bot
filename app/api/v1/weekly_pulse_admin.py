from __future__ import annotations

from datetime import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.v1.admin_executive_export import require_admin
from app.database.leadership_models import WeeklyPulseSchedule
from app.database.models import User
from app.services.weekly_pulse_cycle_service import (
    WeeklyPulseConfigurationError,
    get_schedule,
    update_schedule,
)

router = APIRouter(prefix="/admin/leadership/weekly-pulse", tags=["admin-weekly-pulse"])


class WeeklyPulseScheduleIn(BaseModel):
    enabled: bool = True
    open_weekday: int = Field(ge=0, le=6)
    open_time: time
    deadline_hours: int = Field(ge=1, le=168)
    first_reminder_hours: int = Field(ge=0, le=168)
    final_reminder_hours: int = Field(ge=1, le=168)
    report_weekday: int = Field(ge=0, le=6)
    timezone: str = Field(min_length=1, max_length=64)


class WeeklyPulseScheduleOut(WeeklyPulseScheduleIn):
    id: int


def _as_out(schedule: WeeklyPulseSchedule) -> WeeklyPulseScheduleOut:
    return WeeklyPulseScheduleOut(
        id=schedule.id,
        enabled=schedule.enabled,
        open_weekday=schedule.open_weekday,
        open_time=schedule.open_time,
        deadline_hours=schedule.deadline_hours,
        first_reminder_hours=schedule.first_reminder_hours,
        final_reminder_hours=schedule.final_reminder_hours,
        report_weekday=schedule.report_weekday,
        timezone=schedule.timezone,
    )


@router.get("/schedule", response_model=WeeklyPulseScheduleOut)
async def read_weekly_pulse_schedule(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WeeklyPulseScheduleOut:
    schedule = await get_schedule(session)
    await session.commit()
    return _as_out(schedule)


@router.put("/schedule", response_model=WeeklyPulseScheduleOut)
async def save_weekly_pulse_schedule(
    payload: WeeklyPulseScheduleIn,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WeeklyPulseScheduleOut:
    try:
        schedule = await update_schedule(
            session,
            enabled=payload.enabled,
            open_weekday=payload.open_weekday,
            open_time=payload.open_time,
            deadline_hours=payload.deadline_hours,
            first_reminder_hours=payload.first_reminder_hours,
            final_reminder_hours=payload.final_reminder_hours,
            report_weekday=payload.report_weekday,
            timezone_name=payload.timezone,
        )
    except WeeklyPulseConfigurationError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _as_out(schedule)
