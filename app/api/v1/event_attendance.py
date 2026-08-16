from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.rate_limit import enforce_rate_limit
from app.database.models import User
from app.services import event_attendance_service
from app.services.referral_service import award_first_event_referral

router = APIRouter(prefix="/events", tags=["events"])


class EventAttendanceStateOut(BaseModel):
    event_id: int
    event_status: str
    eligible: bool
    confirmation_open: bool
    confirmed: bool
    points_for_visit: int
    points_awarded: bool


class EventAttendanceCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class EventAttendanceConfirmationOut(EventAttendanceStateOut):
    awarded_now: int
    already_confirmed: bool


def _state_out(state: event_attendance_service.ParticipantAttendanceState) -> EventAttendanceStateOut:
    return EventAttendanceStateOut(
        event_id=state.event.id,
        event_status=str(state.event.status),
        eligible=state.eligible,
        confirmation_open=state.confirmation_open,
        confirmed=state.confirmed,
        points_for_visit=max(0, int(state.event.points_for_visit or 0)),
        points_awarded=state.points_awarded,
    )


@router.get("/{event_id}/attendance", response_model=EventAttendanceStateOut)
async def read_event_attendance_state(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventAttendanceStateOut:
    try:
        state = await event_attendance_service.participant_state(session, event_id, user.id)
    except ValueError as exc:
        if str(exc) == "event_not_found":
            raise HTTPException(status_code=404, detail="event_not_found") from exc
        raise
    return _state_out(state)


@router.post("/{event_id}/attendance/confirm", response_model=EventAttendanceConfirmationOut)
async def confirm_event_attendance(
    event_id: int,
    payload: EventAttendanceCodeIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventAttendanceConfirmationOut:
    await enforce_rate_limit(
        request,
        key_prefix=f"event_attendance:{event_id}:{user.id}",
        limit=8,
        window_seconds=60,
    )
    try:
        result = await event_attendance_service.confirm_attendance(
            session,
            event_id,
            user.id,
            payload.code,
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "event_not_found" else 422 if code == "invalid_attendance_code" else 409
        raise HTTPException(status_code=status, detail=code) from exc

    # The attendance code is the authoritative proof. Referral points are
    # derived only after that confirmation and can be granted only once.
    await award_first_event_referral(
        session,
        invitee_user_id=user.id,
        event_id=event_id,
    )

    state = _state_out(result.state)
    return EventAttendanceConfirmationOut(
        **state.model_dump(),
        awarded_now=result.points_awarded,
        already_confirmed=result.already_confirmed,
    )
