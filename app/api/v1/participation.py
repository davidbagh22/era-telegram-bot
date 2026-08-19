from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.participation_lifecycle_service import (
    CURRENT_ONBOARDING_VERSION,
    MODE_PAUSED,
    complete_onboarding,
    get_or_create_lifecycle,
    refresh_user_lifecycle,
    save_inactivity_reason,
    set_participation_mode,
)
from app.utils.constants import ApplicationStatus

router = APIRouter(prefix="/participation", tags=["participation"])


class ParticipationOut(BaseModel):
    participation_mode: str
    activity_state: str
    last_meaningful_at: str | None
    pause_until: date | None
    onboarding_version: int
    current_onboarding_version: int
    onboarding_completed_at: str | None
    needs_onboarding: bool


class ParticipationModeIn(BaseModel):
    mode: str = Field(min_length=4, max_length=16)
    pause_until: date | None = None
    pause_months: int | None = Field(default=None, ge=1, le=3)


class InactivityReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


def _approved(user: User) -> None:
    if user.application_status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=403, detail="approved_participant_required")


def _out(row) -> ParticipationOut:
    return ParticipationOut(
        participation_mode=row.participation_mode,
        activity_state=row.activity_state,
        last_meaningful_at=row.last_meaningful_at.isoformat() if row.last_meaningful_at else None,
        pause_until=row.pause_until,
        onboarding_version=row.onboarding_version,
        current_onboarding_version=CURRENT_ONBOARDING_VERSION,
        onboarding_completed_at=(
            row.onboarding_completed_at.isoformat() if row.onboarding_completed_at else None
        ),
        needs_onboarding=row.onboarding_version < CURRENT_ONBOARDING_VERSION,
    )


@router.get("/me", response_model=ParticipationOut)
async def read_my_participation(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ParticipationOut:
    _approved(user)
    row = await refresh_user_lifecycle(session, user)
    return _out(row)


@router.post("/onboarding/complete", response_model=ParticipationOut)
async def mark_onboarding_complete(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ParticipationOut:
    _approved(user)
    row = await complete_onboarding(session, user)
    return _out(row)


@router.post("/mode", response_model=ParticipationOut)
async def update_my_participation_mode(
    payload: ParticipationModeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ParticipationOut:
    _approved(user)
    mode = payload.mode.upper()
    pause_until = payload.pause_until
    if mode == MODE_PAUSED and pause_until is None and payload.pause_months is not None:
        # Product presets are one or three months. Use a bounded day-based
        # interval so the API stays deterministic without timezone ambiguity.
        pause_until = date.today() + timedelta(days=30 * payload.pause_months)
    try:
        row = await set_participation_mode(
            session,
            user,
            mode,
            pause_until=pause_until,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(row)


@router.post("/reactivation/reason", response_model=ParticipationOut)
async def update_inactivity_reason(
    payload: InactivityReasonIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ParticipationOut:
    _approved(user)
    await save_inactivity_reason(session, user, payload.reason)
    row = await get_or_create_lifecycle(session, user)
    return _out(row)
