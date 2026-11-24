from __future__ import annotations

from io import BytesIO

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import AttendanceProof, Event, User
from app.services import attendance_proof_service, event_attendance_service
from app.services.authorization_service import can_manage_events

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


async def require_event_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if user.is_blocked or user.is_archived or not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


class AdminEventAttendanceOut(BaseModel):
    event_id: int
    status: str
    started_at: str | None
    completed_at: str | None
    attendance_code: str | None
    can_start: bool
    can_complete: bool
    confirmation_open: bool
    confirmation_closed_at: str | None = None
    notified_count: int = 0


class AttendanceProofOut(BaseModel):
    id: int
    event_id: int
    event_title: str
    user_id: int
    user_name: str
    status: str
    created_at: str | None
    photo_url: str


class ProofDecisionIn(BaseModel):
    comment: str = Field(default="", max_length=500)


def _out(state: event_attendance_service.LifecycleState) -> AdminEventAttendanceOut:
    runtime = state.session
    return AdminEventAttendanceOut(
        event_id=state.event.id,
        status=str(state.event.status),
        started_at=runtime.started_at.isoformat() if runtime and runtime.started_at else None,
        completed_at=runtime.completed_at.isoformat() if runtime and runtime.completed_at else None,
        # The code may be prepared when the event starts, but it is deliberately
        # not exposed to any client until the event is explicitly completed.
        attendance_code=(
            runtime.attendance_code
            if runtime and runtime.completed_at and runtime.attendance_code
            else None
        ),
        can_start=state.can_start,
        can_complete=state.can_complete,
        confirmation_open=state.confirmation_open,
        confirmation_closed_at=(
            runtime.confirmation_closed_at.isoformat()
            if runtime and runtime.confirmation_closed_at
            else None
        ),
        notified_count=state.notified_count,
    )


def _proof_name(user: User | None) -> str:
    if user is None:
        return "Участник"
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник"


def _serialize_proof(proof: AttendanceProof, event: Event | None, owner: User | None) -> AttendanceProofOut:
    return AttendanceProofOut(
        id=proof.id,
        event_id=proof.event_id,
        event_title=(event.title if event else f"Мероприятие #{proof.event_id}"),
        user_id=proof.user_id,
        user_name=_proof_name(owner),
        status=proof.status,
        created_at=proof.created_at.isoformat() if proof.created_at else None,
        photo_url=f"/api/v1/admin/events/attendance-proofs/{proof.id}/photo",
    )


# Static attendance-proof routes must be registered before /{event_id}/...
@router.get("/attendance-proofs/pending", response_model=list[AttendanceProofOut])
async def list_pending_attendance_proofs(
    _manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> list[AttendanceProofOut]:
    proofs = await attendance_proof_service.list_pending_proofs(session)
    result: list[AttendanceProofOut] = []
    for proof in proofs:
        event = await session.get(Event, proof.event_id)
        owner = await session.get(User, proof.user_id)
        result.append(_serialize_proof(proof, event, owner))
    return result


@router.get("/attendance-proofs/{proof_id}/photo")
async def read_attendance_proof_photo(
    proof_id: int,
    _manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> Response:
    proof = await session.get(AttendanceProof, proof_id)
    if proof is None or not proof.photo_file_id:
        raise HTTPException(status_code=404, detail="proof_not_found")
    try:
        telegram_file = await bot.get_file(proof.photo_file_id)
        if not telegram_file.file_path:
            raise RuntimeError("missing_file_path")
        buffer = BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buffer)
        content = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="proof_photo_unavailable") from exc
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


@router.post("/attendance-proofs/{proof_id}/approve", response_model=AttendanceProofOut)
async def approve_attendance_proof_endpoint(
    proof_id: int,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> AttendanceProofOut:
    proof = await session.get(AttendanceProof, proof_id)
    if proof is None:
        raise HTTPException(status_code=404, detail="proof_not_found")
    try:
        result = await attendance_proof_service.approve_proof(session, proof, reviewer=manager, bot=bot)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = await session.get(Event, result.proof.event_id)
    owner = await session.get(User, result.proof.user_id)
    return _serialize_proof(result.proof, event, owner)


@router.post("/attendance-proofs/{proof_id}/reject", response_model=AttendanceProofOut)
async def reject_attendance_proof_endpoint(
    proof_id: int,
    payload: ProofDecisionIn,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> AttendanceProofOut:
    proof = await session.get(AttendanceProof, proof_id)
    if proof is None:
        raise HTTPException(status_code=404, detail="proof_not_found")
    try:
        updated = await attendance_proof_service.reject_proof(
            session, proof, reviewer=manager, comment=payload.comment, bot=bot
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    event = await session.get(Event, updated.event_id)
    owner = await session.get(User, updated.user_id)
    return _serialize_proof(updated, event, owner)


@router.get("/{event_id}/attendance-state", response_model=AdminEventAttendanceOut)
async def read_admin_event_attendance_state(
    event_id: int,
    _manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> AdminEventAttendanceOut:
    try:
        return _out(await event_attendance_service.lifecycle_state(session, event_id))
    except ValueError as exc:
        if str(exc) == "event_not_found":
            raise HTTPException(status_code=404, detail="event_not_found") from exc
        raise


@router.post("/{event_id}/start", response_model=AdminEventAttendanceOut)
async def start_admin_event(
    event_id: int,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> AdminEventAttendanceOut:
    try:
        state = await event_attendance_service.start_event(
            session,
            event_id,
            actor_user_id=manager.id,
            bot=bot,
            miniapp_url=settings.effective_miniapp_url,
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "event_not_found" else 409
        raise HTTPException(status_code=status, detail=code) from exc
    return _out(state)


@router.post("/{event_id}/complete", response_model=AdminEventAttendanceOut)
async def complete_admin_event(
    event_id: int,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> AdminEventAttendanceOut:
    try:
        state = await event_attendance_service.complete_event(
            session,
            event_id,
            actor_user_id=manager.id,
            bot=bot,
            miniapp_url=settings.effective_miniapp_url,
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "event_not_found" else 409
        raise HTTPException(status_code=status, detail=code) from exc
    return _out(state)


@router.post("/{event_id}/attendance/close", response_model=AdminEventAttendanceOut)
async def close_admin_event_confirmation(
    event_id: int,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> AdminEventAttendanceOut:
    try:
        state = await event_attendance_service.close_confirmation(
            session, event_id, actor_user_id=manager.id
        )
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "event_not_found" else 409
        raise HTTPException(status_code=status, detail=code) from exc
    return _out(state)


@router.get("/{event_id}/attendance-qr")
async def read_admin_event_attendance_qr(
    event_id: int,
    manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    try:
        _link, image = await event_attendance_service.confirmation_qr(
            session, event_id, settings=settings, telegram_id=manager.telegram_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "event_not_found" else 409, detail=str(exc)) from exc
    return Response(content=image, media_type="image/png", headers={"Cache-Control": "no-store"})
