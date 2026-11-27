from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.v1.admin_event_operations import require_event_manager
from app.database.models import User
from app.services import event_registration_service

router = APIRouter(prefix="/admin/events", tags=["admin-event-operations"])


class RecentRegistrationOut(BaseModel):
    registration_id: int
    event_id: int
    event_title: str
    participant_id: int
    participant_name: str
    status: str
    registered_at: str | None


@router.get("/recent-registrations", response_model=list[RecentRegistrationOut])
async def read_recent_registrations(
    limit: int = Query(default=5, ge=1, le=20),
    _manager: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> list[RecentRegistrationOut]:
    """Read-only: who signed up last, newest first, so the admin does not
    have to search chats."""
    return [
        RecentRegistrationOut(
            registration_id=item.registration_id,
            event_id=item.event_id,
            event_title=item.event_title,
            participant_id=item.participant_id,
            participant_name=item.participant_name,
            status=item.status,
            registered_at=item.registered_at.isoformat() if item.registered_at else None,
        )
        for item in await event_registration_service.recent_registrations(session, limit)
    ]
