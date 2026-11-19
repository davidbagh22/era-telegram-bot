"""Team directory projects include actual memberships, not only authorship."""
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_session
from app.api.v1.leisure import require_reader
from app.api.v1.projects import ProjectSummaryOut, _to_summary
from app.database.models import Project, ProjectMember, User
from app.services.project_workspace_service import ACTIVE_MEMBER_STATUSES, OPEN_PROJECT_STATUSES
from app.utils.constants import ProjectStatus

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[ProjectSummaryOut])
async def list_teams(scope: Literal["mine", "open"] = "mine",
                     user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session),
                     limit: int = Query(default=50, ge=1, le=50)):
    require_reader(user)
    stmt = select(Project)
    if scope == "mine":
        memberships = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id, ProjectMember.status.in_(ACTIVE_MEMBER_STATUSES))
        stmt = stmt.where(or_(Project.author_id == user.id, Project.id.in_(memberships)),
                          Project.status != ProjectStatus.CANCELLED)
    else:
        stmt = stmt.where(Project.status.in_(OPEN_PROJECT_STATUSES))
    projects = await session.scalars(stmt.order_by(Project.updated_at.desc()).limit(limit))
    return [_to_summary(project) for project in projects.all()]
