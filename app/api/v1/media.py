from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.media_models import MediaContentItem, MediaLibraryItem, MediaRequest
from app.database.models import Task, User
from app.services import media_service

router = APIRouter(prefix="/media", tags=["media"])


class MediaTaskOut(BaseModel):
    id: int
    title: str
    description: str
    deadline: str
    points: int
    status: str


class MediaHubOut(BaseModel):
    chat_url: str
    channel_url: str
    open_tasks: list[MediaTaskOut]
    my_tasks: list[MediaTaskOut]
    can_manage: bool


class LibraryItemOut(BaseModel):
    id: int
    kind: str
    title: str
    description: str | None
    url: str


class IdeaIn(BaseModel):
    text: str = Field(min_length=10, max_length=3000)


class ContentOut(BaseModel):
    id: int
    source_kind: str
    source_type: str | None
    source_id: int | None
    week: int | None
    theme: str | None
    rubric: str | None
    kind: str
    body: str | None
    poll_question: str | None
    poll_options: list[str]
    scheduled_at: str | None
    status: str
    published_at: str | None
    telegram_message_id: int | None


class ContentCreateIn(BaseModel):
    kind: Literal["text", "poll"] = "text"
    body: str | None = Field(default=None, max_length=4096)
    poll_question: str | None = Field(default=None, max_length=300)
    poll_options: list[str] = Field(default_factory=list, max_length=12)
    rubric: str | None = Field(default=None, max_length=120)
    scheduled_at: datetime | None = None


class ContentUpdateIn(BaseModel):
    body: str | None = Field(default=None, max_length=4096)
    poll_question: str | None = Field(default=None, max_length=300)
    poll_options: list[str] | None = None
    rubric: str | None = Field(default=None, max_length=120)


class TaskCreateIn(BaseModel):
    task_kinds: list[Literal["text", "design", "photo", "video", "editing", "stories"]]


class MediaConfigOut(BaseModel):
    auto_enabled: bool
    paused_indefinitely: bool
    paused_until: str | None


class AutoIn(BaseModel):
    enabled: bool


class PauseIn(BaseModel):
    until: datetime | None = None
    indefinitely: bool = False


class RescheduleIn(BaseModel):
    scheduled_at: datetime


class PublishOut(BaseModel):
    ok: bool
    code: str
    message_id: int | None


class MediaAnalyticsOut(BaseModel):
    planned: int
    published: int
    failed: int
    on_time_rate: float | None
    tasks_created: int
    tasks_completed: int


class MediaRequestIn(BaseModel):
    package_type: Literal["announcement", "photo", "video", "reels", "full"] = "full"


class MediaRequestOut(BaseModel):
    id: int
    source_type: str
    source_id: int
    package_type: str
    content_id: int | None
    status: str


def _task_out(task: Task) -> MediaTaskOut:
    return MediaTaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        deadline=task.deadline.isoformat(),
        points=task.points,
        status=task.status,
    )


def _content_out(item: MediaContentItem) -> ContentOut:
    return ContentOut(
        id=item.id,
        source_kind=item.source_kind,
        source_type=item.source_type,
        source_id=item.source_id,
        week=item.week,
        theme=item.theme,
        rubric=item.rubric,
        kind=item.kind,
        body=item.body,
        poll_question=item.poll_question,
        poll_options=list(item.poll_options or []),
        scheduled_at=item.scheduled_at.isoformat() if item.scheduled_at else None,
        status=item.status,
        published_at=item.published_at.isoformat() if item.published_at else None,
        telegram_message_id=item.telegram_message_id,
    )


def _library_out(item: MediaLibraryItem) -> LibraryItemOut:
    return LibraryItemOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        description=item.description,
        url=item.url,
    )


def _request_out(item: MediaRequest) -> MediaRequestOut:
    return MediaRequestOut(
        id=item.id,
        source_type=item.source_type,
        source_id=item.source_id,
        package_type=item.package_type,
        content_id=item.content_id,
        status=item.status,
    )


async def require_media_hub(user: User = Depends(get_current_user)) -> User:
    if not media_service.can_use_media_hub(user):
        raise HTTPException(status_code=403, detail="media_hub_access_required")
    return user


async def require_media_desk(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not await media_service.can_manage_media(session, user, settings):
        raise HTTPException(status_code=403, detail="media_desk_access_required")
    return user


@router.get("/hub", response_model=MediaHubOut)
async def read_media_hub(
    user: User = Depends(require_media_hub),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MediaHubOut:
    open_tasks = await media_service.media_tasks_for_user(session, user.id, mine=False)
    my_tasks = await media_service.media_tasks_for_user(session, user.id, mine=True)
    my_ids = {task.id for task in my_tasks}
    return MediaHubOut(
        chat_url=settings.media_chat_url,
        channel_url=settings.era_channel_url,
        open_tasks=[_task_out(task) for task in open_tasks if task.id not in my_ids],
        my_tasks=[_task_out(task) for task in my_tasks],
        can_manage=await media_service.can_manage_media(session, user, settings),
    )


@router.get("/library", response_model=list[LibraryItemOut])
async def read_media_library(
    _user: User = Depends(require_media_hub),
    session: AsyncSession = Depends(get_session),
) -> list[LibraryItemOut]:
    return [_library_out(item) for item in await media_service.list_library(session)]


@router.post("/ideas", response_model=ContentOut)
async def submit_media_idea(
    payload: IdeaIn,
    user: User = Depends(require_media_hub),
    session: AsyncSession = Depends(get_session),
) -> ContentOut:
    item = await media_service.create_idea(session, user, payload.text.strip())
    return _content_out(item)


@router.get("/desk/config", response_model=MediaConfigOut)
async def read_media_config(
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> MediaConfigOut:
    config = await media_service.media_config(session)
    return MediaConfigOut(**config)


@router.get("/desk/content", response_model=list[ContentOut])
async def read_media_content_plan(
    status: str | None = None,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> list[ContentOut]:
    return [
        _content_out(item)
        for item in await media_service.list_content(session, status=status)
    ]


@router.get("/desk/today", response_model=list[ContentOut])
async def read_media_today(
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[ContentOut]:
    return [_content_out(item) for item in await media_service.today_content(session, settings)]


@router.post("/desk/content", response_model=ContentOut)
async def create_media_content(
    payload: ContentCreateIn,
    manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> ContentOut:
    if payload.kind == "text" and not (payload.body or "").strip():
        raise HTTPException(status_code=422, detail="body_required")
    if payload.kind == "poll":
        if not (payload.poll_question or "").strip() or len(payload.poll_options) < 2:
            raise HTTPException(status_code=422, detail="poll_required")
    scheduled_at = payload.scheduled_at
    if scheduled_at is not None:
        if scheduled_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="timezone_required")
        scheduled_at = scheduled_at.astimezone(timezone.utc)
    item = await media_service.create_content(
        session,
        creator_id=manager.id,
        kind=payload.kind,
        body=payload.body,
        poll_question=payload.poll_question,
        poll_options=payload.poll_options,
        rubric=payload.rubric,
        scheduled_at=scheduled_at,
    )
    return _content_out(item)


@router.patch("/desk/content/{content_id}", response_model=ContentOut)
async def update_media_content(
    content_id: int,
    payload: ContentUpdateIn,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> ContentOut:
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    if item.status == "published":
        raise HTTPException(status_code=409, detail="already_published")
    changes = payload.model_dump(exclude_unset=True)
    if "body" in changes:
        item.body = changes["body"].strip() if changes["body"] else None
    if "poll_question" in changes:
        item.poll_question = changes["poll_question"].strip() if changes["poll_question"] else None
    if "poll_options" in changes:
        item.poll_options = [option.strip() for option in (changes["poll_options"] or []) if option.strip()]
    if "rubric" in changes:
        item.rubric = changes["rubric"].strip() if changes["rubric"] else None
    await session.flush()
    return _content_out(item)


@router.post("/desk/content/{content_id}/tasks", response_model=list[MediaTaskOut])
async def create_media_content_tasks(
    content_id: int,
    payload: TaskCreateIn,
    manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> list[MediaTaskOut]:
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    try:
        links = await media_service.create_content_tasks(
            session, item, creator_id=manager.id, task_kinds=payload.task_kinds
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tasks = [await session.get(Task, link.task_id) for link in links]
    return [_task_out(task) for task in tasks if task is not None]


@router.post("/desk/auto", response_model=MediaConfigOut)
async def set_media_auto(
    payload: AutoIn,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> MediaConfigOut:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    try:
        config = await media_service.set_auto_enabled(
            session, bot, settings, enabled=payload.enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MediaConfigOut(**config)


@router.post("/desk/pause", response_model=MediaConfigOut)
async def pause_media_auto(
    payload: PauseIn,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> MediaConfigOut:
    until = payload.until
    if until is not None and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="timezone_required")
    config = await media_service.pause_publication(
        session,
        until=until.astimezone(timezone.utc) if until else None,
        indefinitely=payload.indefinitely,
    )
    return MediaConfigOut(**config)


@router.post("/desk/resume", response_model=MediaConfigOut)
async def resume_media_auto(
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> MediaConfigOut:
    return MediaConfigOut(**(await media_service.resume_publication(session)))


@router.post("/desk/content/{content_id}/skip", response_model=ContentOut)
async def skip_media_content(
    content_id: int,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> ContentOut:
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    try:
        await media_service.skip_content(session, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _content_out(item)


@router.post("/desk/content/{content_id}/reschedule", response_model=ContentOut)
async def reschedule_media_content(
    content_id: int,
    payload: RescheduleIn,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> ContentOut:
    if payload.scheduled_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="timezone_required")
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    try:
        await media_service.reschedule_content(session, item, payload.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _content_out(item)


@router.post("/desk/content/{content_id}/publish-now", response_model=PublishOut)
async def publish_media_content_now(
    content_id: int,
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> PublishOut:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    result = await media_service.publish_content(session, bot, settings, item, manual=True)
    return PublishOut(ok=result.ok, code=result.code, message_id=result.message_id)


@router.get("/desk/channel-health")
async def media_channel_health(
    _manager: User = Depends(require_media_desk),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> dict[str, str | bool]:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    from app.services.chat_registry_service import check_chats_health

    health = await check_chats_health(bot, settings)
    item = next((entry for entry in health if entry.chat_key == "era_channel"), None)
    if item is None:
        return {"ok": False, "detail": "not_bound"}
    return {"ok": item.ok, "detail": item.detail}


@router.get("/desk/analytics", response_model=MediaAnalyticsOut)
async def read_media_analytics(
    _manager: User = Depends(require_media_desk),
    session: AsyncSession = Depends(get_session),
) -> MediaAnalyticsOut:
    result = await media_service.analytics(session)
    return MediaAnalyticsOut(**result.__dict__)


async def _request_media(
    source_type: Literal["event", "project"],
    source_id: int,
    payload: MediaRequestIn,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> MediaRequestOut:
    try:
        item = await media_service.request_media_package(
            session,
            source_type=source_type,
            source_id=source_id,
            package_type=payload.package_type,
            requester=user,
            settings=settings,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(
            status_code=404 if detail == "source_not_found" else 422,
            detail=detail,
        ) from exc
    return _request_out(item)


@router.post("/requests/event/{event_id}", response_model=MediaRequestOut)
async def request_event_media(
    event_id: int,
    payload: MediaRequestIn,
    user: User = Depends(require_media_hub),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MediaRequestOut:
    return await _request_media("event", event_id, payload, user, session, settings)


@router.post("/requests/project/{project_id}", response_model=MediaRequestOut)
async def request_project_media(
    project_id: int,
    payload: MediaRequestIn,
    user: User = Depends(require_media_hub),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MediaRequestOut:
    return await _request_media("project", project_id, payload, user, session, settings)
