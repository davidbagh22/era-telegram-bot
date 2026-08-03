from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import Event, EventRegistration, User
from app.services.activity_service import EventScope, list_events
from app.services.event_registration_service import mark_not_coming
from app.services.event_service import available_places, register_for_event

router = APIRouter(prefix="/events", tags=["events"])


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    event_date: str
    event_time: str
    location: str
    format: str
    points_for_visit: int
    project_id: int | None
    available_places: str
    registration_status: str | None


async def _to_event_out(
    session: AsyncSession, event: Event, registration: EventRegistration | None
) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        location=event.location,
        format=event.format,
        points_for_visit=event.points_for_visit,
        project_id=event.project_id,
        available_places=await available_places(session, event),
        registration_status=registration.status if registration else None,
    )


async def _get_registration(
    session: AsyncSession, event_id: int, user_id: int
) -> EventRegistration | None:
    return await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id, EventRegistration.user_id == user_id
        )
    )


@router.get("", response_model=list[EventOut])
async def read_events(
    scope: EventScope = Query("all"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    rows = await list_events(session, user, scope)
    return [await _to_event_out(session, event, registration) for event, registration in rows]


@router.get("/{event_id}", response_model=EventOut)
async def read_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    return await _to_event_out(session, event, registration)


@router.post("/{event_id}/register", response_model=EventOut)
async def register_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration, error = await register_for_event(session, event, user.id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return await _to_event_out(session, event, registration)


@router.post("/{event_id}/cancel", response_model=EventOut)
async def cancel_event_registration(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    if registration is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    if not mark_not_coming(registration, event):
        raise HTTPException(status_code=409, detail="cannot_change_plans")
    return await _to_event_out(session, event, registration)
