from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Project, User
from app.services.project_workspace_service import can_review_projects

router = APIRouter(prefix="/admin/projects", tags=["admin-project-detail"])


class AdminProjectDetailOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    author_name: str
    submitted_at: str | None
    admin_comment: str | None
    form_data: dict[str, object]
    generated_document: str | None


@router.get("/{project_id}/detail", response_model=AdminProjectDetailOut)
async def read_admin_project_detail(
    project_id: int,
    reviewer: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AdminProjectDetailOut:
    if not await can_review_projects(session, reviewer, settings):
        raise HTTPException(status_code=403, detail="reviewer_access_required")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    author = await session.get(User, project.author_id)
    author_name = (
        f"{author.first_name} {author.last_name or ''}".strip()
        if author is not None
        else f"Участник #{project.author_id}"
    )
    return AdminProjectDetailOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        author_name=author_name,
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
        form_data=dict(project.form_data or {}),
        generated_document=project.generated_document,
    )
