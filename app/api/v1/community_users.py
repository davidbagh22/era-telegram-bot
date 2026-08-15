from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.utils.constants import ApplicationStatus, ROLE_LABELS, STATUS_LABELS

router = APIRouter(prefix="/users", tags=["community-users"])


class CommunityUserOut(BaseModel):
    id: int
    name: str
    role: str
    role_label: str
    participation_status: str
    participation_label: str
    departments: list[str]


@router.get("/{user_id}", response_model=CommunityUserOut)
async def read_community_user(
    user_id: int,
    _viewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CommunityUserOut:
    user = await session.get(User, user_id)
    if (
        user is None
        or user.is_archived
        or user.is_blocked
        or user.application_status != ApplicationStatus.APPROVED
    ):
        raise HTTPException(status_code=404, detail="user_not_found")
    departments = [
        item.department.name
        for item in user.departments or []
        if getattr(item, "department", None) is not None
    ]
    return CommunityUserOut(
        id=user.id,
        name=f"{user.first_name} {user.last_name or ''}".strip(),
        role=str(user.role),
        role_label=ROLE_LABELS.get(user.role, str(user.role)),
        participation_status=str(user.participation_status),
        participation_label=STATUS_LABELS.get(user.participation_status, str(user.participation_status)),
        departments=departments,
    )
