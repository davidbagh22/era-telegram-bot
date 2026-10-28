from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.database.event_experience import EventExperience
from app.database.models import Event
from app.services.event_poster_security import normalized_event_poster_mime
from app.services.event_service import PUBLIC_EVENT_STATUSES

router = APIRouter(prefix="/event-posters", tags=["event-posters"])


@router.get("/{event_id}")
async def read_public_event_poster(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Serve only published, non-executable event posters without authentication.

    This legacy public URL must not bypass the authenticated Mini App's
    moderation and MIME checks. Drafts and non-public historical statuses
    cannot be served here because there is no reliable publication history.
    """
    event = await session.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    experience = await session.get(EventExperience, event_id)
    if experience is None or not experience.poster_bytes:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    poster_mime = normalized_event_poster_mime(experience.poster_content_type)
    if poster_mime is None:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    return Response(
        content=experience.poster_bytes,
        media_type=poster_mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
