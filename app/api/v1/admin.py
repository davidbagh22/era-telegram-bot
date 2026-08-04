from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Event, Project, User
from app.keyboards.participant import main_menu
from app.services import event_moderation_service, project_workflow_service
from app.services.admin_dashboard_service import dashboard_metrics, has_dashboard_access
from app.services.application_review_service import (
    approve_application,
    reject_application,
    request_more_info,
)
from app.services.authorization_service import can_manage_events
from app.services.chat_access_service import sync_user_chat_access
from app.services.notification_service import safe_send
from app.services.project_workspace_service import can_review_projects
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_dashboard_access(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class DashboardOut(BaseModel):
    metrics: dict[str, int]
    attention_total: int


@router.get("/dashboard", response_model=DashboardOut)
async def read_dashboard(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    metrics = await dashboard_metrics(session)
    return DashboardOut(metrics=metrics.values, attention_total=metrics.attention_total)


class ApplicationOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    city: str | None
    occupation: str | None
    motivation: str | None
    application_status: str
    created_at: str


def _to_application_out(user: User) -> ApplicationOut:
    return ApplicationOut(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        city=user.city,
        occupation=user.occupation,
        motivation=user.motivation,
        application_status=user.application_status,
        created_at=user.created_at.isoformat(),
    )


@router.get("/applications", response_model=list[ApplicationOut])
async def read_applications(
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> list[ApplicationOut]:
    rows = await session.scalars(
        select(User)
        .where(
            User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
            User.is_archived.is_(False),
        )
        .order_by(User.created_at)
    )
    return [_to_application_out(u) for u in rows.all()]


class CommentIn(BaseModel):
    comment: str = ""


@router.post("/applications/{user_id}/approve", response_model=ApplicationOut)
async def approve_user_application(
    user_id: int,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> ApplicationOut:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await approve_application(session, target, actor_id=admin.id)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        # Mirrors app/handlers/admin/panel.py::approve_user exactly, so a
        # Mini App approval looks identical to the Bot one to the user.
        await safe_send(
            bot,
            target.telegram_id,
            texts.APPLICATION_APPROVED,
            main_menu(settings.era_channel_url, miniapp_url=settings.effective_miniapp_url),
        )
        await safe_send(
            bot, target.telegram_id, "Перед стартом — короткие правила сообщества\n\n" + texts.CHAT_RULES
        )
        await sync_user_chat_access(bot, settings, session, target)
    return _to_application_out(target)


@router.post("/applications/{user_id}/reject", response_model=ApplicationOut)
async def reject_user_application(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await reject_application(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(
            bot,
            target.telegram_id,
            f"{texts.APPLICATION_REJECTED}\n\nКомментарий: {payload.comment}",
        )
    return _to_application_out(target)


@router.post("/applications/{user_id}/request-info", response_model=ApplicationOut)
async def request_more_info_endpoint(
    user_id: int,
    payload: CommentIn,
    admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> ApplicationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    result = await request_more_info(session, target, actor_id=admin.id, comment=payload.comment)
    if not result.changed:
        raise HTTPException(status_code=409, detail=result.code)
    if bot is not None:
        await safe_send(bot, target.telegram_id, texts.APPLICATION_NEEDS_INFO.format(comment=payload.comment))
    return _to_application_out(target)


class ProjectModerationOut(BaseModel):
    id: int
    title: str
    short_description: str
    status: str
    author_id: int
    submitted_at: str | None
    admin_comment: str | None


def _to_moderation_out(project: Project) -> ProjectModerationOut:
    return ProjectModerationOut(
        id=project.id,
        title=project.title,
        short_description=project.short_description,
        status=project.status,
        author_id=project.author_id,
        submitted_at=project.submitted_at.isoformat() if project.submitted_at else None,
        admin_comment=project.admin_comment,
    )


async def require_project_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not await can_review_projects(session, user, settings):
        raise HTTPException(status_code=403, detail="reviewer_access_required")
    return user


@router.get("/projects", response_model=list[ProjectModerationOut])
async def read_projects_for_review(
    _reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectModerationOut]:
    projects = await project_workflow_service.list_projects_for_review(session)
    return [_to_moderation_out(project) for project in projects]


class ProjectDecisionIn(BaseModel):
    action: str
    comment: str


@router.post("/projects/{project_id}/decide", response_model=ProjectModerationOut)
async def decide_project_endpoint(
    project_id: int,
    payload: ProjectDecisionIn,
    reviewer: User = Depends(require_project_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> ProjectModerationOut:
    if not payload.comment.strip():
        raise HTTPException(status_code=422, detail="comment_required")
    if payload.action not in project_workflow_service.PROJECT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    result = await project_workflow_service.decide_project(
        session, project, action=payload.action, comment=payload.comment, actor=reviewer
    )
    if bot is not None:
        author = await session.get(User, project.author_id)
        if author is not None:
            await safe_send(
                bot,
                author.telegram_id,
                f"💡 {result.notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{payload.comment}",
            )
    return _to_moderation_out(project)


class EventModerationOut(BaseModel):
    id: int
    title: str
    description: str
    event_date: str
    event_time: str
    location: str
    status: str


def _to_event_moderation_out(event: Event) -> EventModerationOut:
    return EventModerationOut(
        id=event.id,
        title=event.title,
        description=event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(),
        location=event.location,
        status=event.status,
    )


async def require_event_reviewer(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


@router.get("/events", response_model=list[EventModerationOut])
async def read_events_for_review(
    _reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
) -> list[EventModerationOut]:
    events = await event_moderation_service.list_events_for_review(session)
    return [_to_event_moderation_out(event) for event in events]


class EventDecisionIn(BaseModel):
    action: str
    comment: str = ""


@router.post("/events/{event_id}/decide", response_model=EventModerationOut)
async def decide_event_endpoint(
    event_id: int,
    payload: EventDecisionIn,
    reviewer: User = Depends(require_event_reviewer),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> EventModerationOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if payload.action not in event_moderation_service.EVENT_DECISION_ACTIONS:
        raise HTTPException(status_code=422, detail="invalid_action")
    try:
        result = await event_moderation_service.decide_event(
            session, event, action=payload.action, comment=payload.comment, actor=reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bot is not None and result.owner is not None:
        await safe_send(bot, result.owner.telegram_id, result.notice)
    return _to_event_moderation_out(event)
