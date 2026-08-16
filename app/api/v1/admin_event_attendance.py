from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services import event_attendance_service
from app.services.authorization_service import can_manage_events

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


async def require_event_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
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
    notified_count: int = 0


def _out(state: event_attendance_service.LifecycleState) -> AdminEventAttendanceOut:
    runtime = state.session
    return AdminEventAttendanceOut(
        event_id=state.event.id,
        status=str(state.event.status),
        started_at=runtime.started_at.isoformat() if runtime and runtime.started_at else None,
        completed_at=runtime.completed_at.isoformat() if runtime and runtime.completed_at else None,
        attendance_code=runtime.attendance_code if runtime else None,
        can_start=state.can_start,
        can_complete=state.can_complete,
        confirmation_open=state.confirmation_open,
        notified_count=state.notified_count,
    )


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
