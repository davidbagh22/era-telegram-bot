from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
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
    directions: list[str] = []


class CommunityUserListOut(BaseModel):
    items: list[CommunityUserOut]
    total: int
    limit: int
    offset: int


def _require_approved(viewer: User) -> None:
    if viewer.application_status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=403, detail="approved_membership_required")


def _to_community_user(user: User) -> CommunityUserOut:
    departments = [
        item.department.name
        for item in user.departments or []
        if getattr(item, "department", None) is not None
    ]
    directions = [
        item.direction.name
        for item in user.directions or []
        if getattr(item, "direction", None) is not None
    ]
    return CommunityUserOut(
        id=user.id,
        name=f"{user.first_name} {user.last_name or ''}".strip(),
        role=str(user.role),
        role_label=ROLE_LABELS.get(user.role, str(user.role)),
        participation_status=str(user.participation_status),
        participation_label=STATUS_LABELS.get(user.participation_status, str(user.participation_status)),
        departments=departments,
        directions=directions,
    )


def _public_member_filters():
    return (
        User.is_archived.is_(False),
        User.is_blocked.is_(False),
        User.application_status == ApplicationStatus.APPROVED,
    )


@router.get("", response_model=CommunityUserListOut)
async def list_community_users(
    q: str | None = Query(default=None, max_length=80),
    department: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    viewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CommunityUserListOut:
    """Read-only participant directory. Public fields only — no contacts/forms."""
    _require_approved(viewer)

    filters = list(_public_member_filters())
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                User.first_name.ilike(needle),
                User.last_name.ilike(needle),
            )
        )

    stmt = select(User).where(*filters).order_by(User.first_name.asc(), User.id.asc())
    result = await session.execute(stmt)
    users = list(result.scalars().unique().all())

    if department and department.strip():
        wanted = department.strip().casefold()
        users = [
            user
            for user in users
            if any(
                getattr(item, "department", None) is not None
                and item.department.name.casefold() == wanted
                for item in user.departments or []
            )
        ]

    total = len(users)
    page = users[offset : offset + limit]
    return CommunityUserListOut(
        items=[_to_community_user(user) for user in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=CommunityUserOut)
async def read_community_user(
    user_id: int,
    viewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CommunityUserOut:
    _require_approved(viewer)
    user = await session.get(User, user_id)
    if (
        user is None
        or user.is_archived
        or user.is_blocked
        or user.application_status != ApplicationStatus.APPROVED
    ):
        raise HTTPException(status_code=404, detail="user_not_found")
    return _to_community_user(user)
