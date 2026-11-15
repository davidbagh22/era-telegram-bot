from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.database.event_experience import EventExperience
from app.database.models import Event
from app.utils.constants import EventStatus

router = APIRouter(prefix="/event-posters", tags=["event-posters"])

# Match the authenticated event-poster route's browser-safe image formats.
# Do not reflect legacy poster metadata such as text/html or image/svg+xml.
_SAFE_POSTER_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif", "image/heic", "image/heif"}
)


@router.get("/{event_id}")
async def read_public_event_poster(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Hide moderation-only posters while preserving historical public links."""
    event = await session.get(Event, event_id)
    if event is None or event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        raise HTTPException(status_code=404, detail="event_poster_not_found")

    experience = await session.get(EventExperience, event_id)
    if experience is None or not experience.poster_bytes:
        raise HTTPException(status_code=404, detail="event_poster_not_found")

    # Keep missing MIME metadata compatible with historical JPEG posters.
    poster_mime = (experience.poster_content_type or "image/jpeg").split(";", 1)[0].strip().lower()
    if poster_mime not in _SAFE_POSTER_MIME_TYPES:
        raise HTTPException(status_code=404, detail="event_poster_not_found")

    return Response(
        content=experience.poster_bytes,
        media_type=poster_mime,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
