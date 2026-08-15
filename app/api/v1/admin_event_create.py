from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Event, User
from app.services.audit_service import audit
from app.services.authorization_service import can_manage_events
from app.utils.constants import EventStatus

router = APIRouter(prefix="/admin/events", tags=["admin-event-create"])


async def require_event_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


class AdminEventCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)
    event_date: date
    event_time: time
    location: str = Field(min_length=2, max_length=255)
    format: str = Field(min_length=2, max_length=100)
    participant_limit: int | None = Field(default=None, ge=1, le=5000)
    points_for_visit: int = Field(default=5, ge=0, le=200)
    needs_volunteers: bool = False
    additional_info: str | None = Field(default=None, max_length=5000)
    publish: bool = False


class AdminEventCreateOut(BaseModel):
    id: int
    title: str
    status: str
    event_date: str
    event_time: str
    location: str


@router.post("/create", response_model=AdminEventCreateOut)
async def create_event_from_admin(
    payload: AdminEventCreateIn,
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> AdminEventCreateOut:
    status = EventStatus.REGISTRATION_OPEN if payload.publish else EventStatus.DRAFT
    event = Event(
        title=payload.title.strip(),
        description=payload.description.strip(),
        event_date=payload.event_date,
        event_time=payload.event_time,
        location=payload.location.strip(),
        format=payload.format.strip(),
        participant_limit=payload.participant_limit,
        points_for_visit=payload.points_for_visit,
        needs_volunteers=payload.needs_volunteers,
        additional_info=payload.additional_info.strip() if payload.additional_info else None,
        status=status,
        created_by=admin.id,
        approved_by=admin.id if payload.publish else None,
    )
    session.add(event)
    await session.flush()
    await audit(
        session,
        actor_id=admin.id,
        action="event.created_from_admin",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": str(status), "published": payload.publish},
    )
    await session.commit()
    return AdminEventCreateOut(
        id=event.id,
        title=event.title,
        status=event.status,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        location=event.location,
    )
