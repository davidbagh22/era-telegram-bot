from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.database.event_experience import EventExperience

router = APIRouter(prefix="/event-posters", tags=["event-posters"])


@router.get("/{event_id}")
async def read_public_event_poster(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Event posters are public presentation assets; no profile data is exposed."""
    experience = await session.get(EventExperience, event_id)
    if experience is None or not experience.poster_bytes:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    return Response(
        content=experience.poster_bytes,
        media_type=experience.poster_content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=300"},
    )
