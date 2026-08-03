from __future__ import annotations

from io import BytesIO

from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Project, User
from app.services import project_workflow_service
from app.services.notification_service import safe_send, safe_send_document
from app.services.project_builder import PROJECT_QUESTIONS
from app.services.project_workflow_service import ProjectScope

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectQuestionOut(BaseModel):
    key: str
    block: str
    title: str
    prompt: str


# proposed_date/proposed_time are typed Project columns the Bot wizard
# parses specially (see app/handlers/participant/projects.py::project_answer);
# project_workflow_service.update_answers only stores plain strings, so
# these two stay Bot-only for now rather than silently not working right.
_EDITABLE_QUESTIONS = [q for q in PROJECT_QUESTIONS if q.input_type == "text"]


class ProjectSummaryOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    updated_at: str
    submitted_at: str | None
    admin_comment: str | None


class ProjectDetailOut(ProjectSummaryOut):
    form_data: dict[str, str]
    can_edit: bool
    can_submit: bool
    can_delete: bool


class CreateProjectIn(BaseModel):
    idea: str = ""


class UpdateAnswersIn(BaseModel):
    answers: dict[str, str]


def _to_summary(project: Project) -> ProjectSummaryOut:
    return ProjectSummaryOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        updated_at=project.updated_at.isoformat(),
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
    )


def _to_detail(project: Project) -> ProjectDetailOut:
    summary = _to_summary(project)
    return ProjectDetailOut(
        **summary.model_dump(),
        form_data=project.form_data or {},
        can_edit=project_workflow_service.can_edit(project),
        can_submit=project_workflow_service.can_submit_for_review(project),
        can_delete=project_workflow_service.can_delete(project),
    )


def _visible_to(project: Project, user: User) -> bool:
    return project.author_id == user.id or project.status in project_workflow_service.OPEN_STATUSES


@router.get("", response_model=list[ProjectSummaryOut])
async def read_projects(
    scope: ProjectScope = Query("mine"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectSummaryOut]:
    projects = await project_workflow_service.list_projects_for_user(session, user, scope)
    return [_to_summary(project) for project in projects]


@router.get("/questions", response_model=list[ProjectQuestionOut])
async def read_project_questions() -> list[ProjectQuestionOut]:
    return [
        ProjectQuestionOut(key=q.key, block=q.block, title=q.title, prompt=q.prompt)
        for q in _EDITABLE_QUESTIONS
    ]


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def read_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or not _visible_to(project, user):
        raise HTTPException(status_code=404, detail="project_not_found")
    return _to_detail(project)


@router.post("", response_model=ProjectDetailOut)
async def create_project(
    payload: CreateProjectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await project_workflow_service.create_draft(session, user, payload.idea)
    return _to_detail(project)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def update_project(
    project_id: int,
    payload: UpdateAnswersIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_edit(project):
        raise HTTPException(status_code=409, detail="project_not_editable")
    project_workflow_service.update_answers(project, payload.answers)
    return _to_detail(project)


@router.post("/{project_id}/submit", response_model=ProjectDetailOut)
async def submit_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_submit_for_review(project):
        raise HTTPException(status_code=409, detail="project_not_submittable")
    document = await project_workflow_service.submit_for_review(session, project, user)
    if bot is not None:
        await _notify_reviewers(bot, settings, project, user, document)
    return _to_detail(project)


@router.post("/{project_id}/cancel", response_model=ProjectDetailOut)
async def cancel_project(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProjectDetailOut:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="project_not_found")
    if not project_workflow_service.can_delete(project):
        raise HTTPException(status_code=409, detail="project_not_cancellable")
    await project_workflow_service.cancel_project(session, project, user)
    return _to_detail(project)


async def _notify_reviewers(
    bot: Bot, settings: Settings, project: Project, user: User, document: str
) -> None:
    """Same notification bot/mobile users get from the in-bot submit flow
    (app/handlers/participant/projects_block5.py::project_submit_full) — the
    Mini App and Bot share one process, so this reuses the same Bot
    instance instead of a second, silent submission path."""
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    summary = (
        f"💡 Новый проект на рассмотрении\n\n{project.title}\n"
        f"Автор: {user.first_name} {user.last_name or ''} ({telegram})\n\n"
        "Полный файл проекта прикреплён ниже."
    )
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    for chat_id in recipients:
        await safe_send(bot, chat_id, summary)
        await safe_send_document(
            bot,
            chat_id,
            BufferedInputFile(
                BytesIO(document.encode("utf-8")).getvalue(),
                filename=f"ERA_project_{project.id}.txt",
            ),
            caption=f"Полный проект #{project.id}",
        )
