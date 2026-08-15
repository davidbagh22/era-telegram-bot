from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import EventRegistration, ProjectMember, TaskSubmission, User
from app.utils.constants import ApplicationStatus, ROLE_LABELS, STATUS_LABELS

router = APIRouter(prefix="/users", tags=["community-users"])


class CommunityUserOut(BaseModel):
    id: int
    name: str
    username: str | None
    telegram_url: str | None
    role: str
    role_label: str
    participation_status: str
    participation_label: str
    departments: list[str]
    directions: list[str]
    events_attended: int = 0
    project_memberships: int = 0
    tasks_completed: int = 0


def _departments(user: User) -> list[str]:
    return [
        item.department.name
        for item in user.departments or []
        if getattr(item, "department", None) is not None
    ]


def _directions(user: User) -> list[str]:
    return [
        item.direction.name
        for item in user.directions or []
        if getattr(item, "direction", None) is not None
    ]


def _public_user(
    user: User,
    *,
    events_attended: int = 0,
    project_memberships: int = 0,
    tasks_completed: int = 0,
) -> CommunityUserOut:
    username = (user.username or "").lstrip("@") or None
    return CommunityUserOut(
        id=user.id,
        name=f"{user.first_name} {user.last_name or ''}".strip(),
        username=username,
        telegram_url=f"https://t.me/{username}" if username else None,
        role=str(user.role),
        role_label=ROLE_LABELS.get(user.role, str(user.role)),
        participation_status=str(user.participation_status),
        participation_label=STATUS_LABELS.get(user.participation_status, str(user.participation_status)),
        departments=_departments(user),
        directions=_directions(user),
        events_attended=events_attended,
        project_memberships=project_memberships,
        tasks_completed=tasks_completed,
    )


async def _activity_maps(session: AsyncSession, user_ids: list[int]) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    if not user_ids:
        return {}, {}, {}

    event_rows = await session.execute(
        select(EventRegistration.user_id, func.count(EventRegistration.id))
        .where(EventRegistration.user_id.in_(user_ids), EventRegistration.status == "attended")
        .group_by(EventRegistration.user_id)
    )
    project_rows = await session.execute(
        select(ProjectMember.user_id, func.count(ProjectMember.id))
        .where(ProjectMember.user_id.in_(user_ids), ProjectMember.status == "approved")
        .group_by(ProjectMember.user_id)
    )
    task_rows = await session.execute(
        select(TaskSubmission.user_id, func.count(TaskSubmission.id))
        .where(TaskSubmission.user_id.in_(user_ids), TaskSubmission.status == "approved")
        .group_by(TaskSubmission.user_id)
    )
    return dict(event_rows.all()), dict(project_rows.all()), dict(task_rows.all())


@router.get("", response_model=list[CommunityUserOut])
async def list_community_users(
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None, max_length=100),
    _viewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CommunityUserOut]:
    statement = (
        select(User)
        .where(
            User.application_status == ApplicationStatus.APPROVED,
            User.is_blocked.is_(False),
            User.is_archived.is_not(True),
        )
        .order_by(User.first_name.asc(), User.last_name.asc())
        .limit(80)
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(needle),
                User.last_name.ilike(needle),
                User.username.ilike(needle),
            )
        )

    users = list((await session.scalars(statement)).all())
    if department and department.strip():
        key = department.strip().casefold()
        users = [user for user in users if any(key in name.casefold() for name in _departments(user))]

    ids = [user.id for user in users]
    event_counts, project_counts, task_counts = await _activity_maps(session, ids)
    return [
        _public_user(
            user,
            events_attended=event_counts.get(user.id, 0),
            project_memberships=project_counts.get(user.id, 0),
            tasks_completed=task_counts.get(user.id, 0),
        )
        for user in users
    ]


@router.get("/{user_id}", response_model=CommunityUserOut)
async def read_community_user(
    user_id: int,
    _viewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CommunityUserOut:
    user = await session.get(User, user_id)
    if (
        user is None
        or user.is_archived is True
        or user.is_blocked
        or user.application_status != ApplicationStatus.APPROVED
    ):
        raise HTTPException(status_code=404, detail="user_not_found")
    event_counts, project_counts, task_counts = await _activity_maps(session, [user.id])
    return _public_user(
        user,
        events_attended=event_counts.get(user.id, 0),
        project_memberships=project_counts.get(user.id, 0),
        tasks_completed=task_counts.get(user.id, 0),
    )
