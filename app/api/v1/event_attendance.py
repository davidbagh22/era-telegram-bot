from __future__ import annotations

from datetime import date

from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import AttendanceProof, Event, EventRegistration, User
from app.services import event_attendance_service
from app.services.notification_service import notify_admins
from app.services.referral_service import award_first_event_referral
from app.utils.constants import ApplicationStatus, RegistrationStatus

router = APIRouter(prefix="/events", tags=["events"])

_PROOF_TYPES = {"image/jpeg", "image/png", "image/webp"}
_PROOF_MAX_BYTES = 5 * 1024 * 1024


class EventAttendanceStateOut(BaseModel):
    event_id: int
    event_status: str
    eligible: bool
    confirmation_open: bool
    confirmation_closed: bool = False
    confirmed: bool
    points_for_visit: int
    points_awarded: bool
    proof_status: str | None = None
    can_submit_proof: bool = False


class EventAttendanceCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class EventAttendanceConfirmationOut(EventAttendanceStateOut):
    awarded_now: int
    already_confirmed: bool


async def _proof_for(session: AsyncSession, event_id: int, user_id: int) -> AttendanceProof | None:
    return await session.scalar(
        select(AttendanceProof).where(
            AttendanceProof.event_id == event_id,
            AttendanceProof.user_id == user_id,
        )
    )


def _state_out(
    state: event_attendance_service.ParticipantAttendanceState,
    *,
    proof: AttendanceProof | None = None,
) -> EventAttendanceStateOut:
    registered = state.eligible
    can_submit = (
        registered
        and not state.confirmed
        and (proof is None or proof.status in {"pending", "rejected"})
        and state.event.event_date <= date.today()
    )
    return EventAttendanceStateOut(
        event_id=state.event.id,
        event_status=str(state.event.status),
        eligible=state.eligible,
        confirmation_open=state.confirmation_open,
        confirmation_closed=state.confirmation_closed,
        confirmed=state.confirmed,
        points_for_visit=max(0, int(state.event.points_for_visit or 0)),
        points_awarded=state.points_awarded,
        proof_status=proof.status if proof else None,
        can_submit_proof=can_submit,
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
    proof = await _proof_for(session, event_id, user.id)
    return _state_out(state, proof=proof)


@router.post("/{event_id}/attendance/proof", response_model=EventAttendanceStateOut)
async def submit_attendance_proof(
    event_id: int,
    request: Request,
    upload: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot = Depends(get_bot),
) -> EventAttendanceStateOut:
    """Mini App photo proof → same AttendanceProof queue as bot selfie."""
    await enforce_rate_limit(
        request,
        key_prefix=f"event_proof:{event_id}:{user.id}",
        limit=6,
        window_seconds=60,
    )
    if user.application_status != ApplicationStatus.APPROVED or user.is_blocked:
        raise HTTPException(status_code=403, detail="forbidden")
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
            EventRegistration.status.in_(
                (
                    RegistrationStatus.REGISTERED,
                    RegistrationStatus.WILL_COME,
                    RegistrationStatus.ATTENDED,
                )
            ),
        )
    )
    if registration is None:
        raise HTTPException(status_code=409, detail="not_registered")
    if event.event_date > date.today():
        raise HTTPException(status_code=409, detail="event_not_started")
    if upload.content_type not in _PROOF_TYPES:
        raise HTTPException(status_code=415, detail="proof_must_be_image")
    content = await upload.read(_PROOF_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="empty_proof_file")
    if len(content) > _PROOF_MAX_BYTES:
        raise HTTPException(status_code=413, detail="proof_too_large")
    try:
        sent = await bot.send_photo(
            user.telegram_id,
            BufferedInputFile(content, filename=upload.filename or "attendance.jpg"),
            caption=f"📷 Подтверждение участия: {event.title[:100]}",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="proof_storage_unavailable") from exc
    photo = sent.photo[-1] if sent.photo else None
    if photo is None:
        raise HTTPException(status_code=502, detail="proof_storage_unavailable")
    proof = await _proof_for(session, event_id, user.id)
    if proof is None:
        proof = AttendanceProof(event_id=event_id, user_id=user.id, photo_file_id=photo.file_id)
        session.add(proof)
    else:
        proof.photo_file_id = photo.file_id
        proof.status = "pending"
        proof.admin_comment = None
    await session.flush()
    await notify_admins(
        bot,
        settings,
        f"Новое фото-подтверждение #{proof.id} (Mini App). Откройте панель администратора.",
    )
    state = await event_attendance_service.participant_state(session, event_id, user.id)
    return _state_out(state, proof=proof)


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

    proof = await _proof_for(session, event_id, user.id)
    state = _state_out(result.state, proof=proof)
    return EventAttendanceConfirmationOut(
        **state.model_dump(),
        awarded_now=result.points_awarded,
        already_confirmed=result.already_confirmed,
    )
