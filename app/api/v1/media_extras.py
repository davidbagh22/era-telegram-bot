from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.media_models import MediaAttachment, MediaContentItem, MediaLibraryItem
from app.database.models import Task, User
from app.services import media_service, task_service
from app.services.media_attachment_service import attached_files
from app.services.media_dashboard_service import (
    MEDIA_GUIDE,
    actionable_today,
    average_cycle_time_hours,
    team_analytics,
)

router = APIRouter(prefix="/media", tags=["media"])


class TodayActionOut(BaseModel):
    kind: str
    severity: str
    title: str
    detail: str
    content_id: int | None
    task_id: int | None


class TeamMemberOut(BaseModel):
    user_id: int
    name: str
    materials_created: int
    tasks_completed: int
    deadline_rate: float | None
    published_contributions: int
    media_points: int


class PipelineUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status: Literal[
        "IDEA",
        "PLANNED",
        "ASSIGNED",
        "IN_PROGRESS",
        "REVIEW",
        "READY",
        "SCHEDULED",
        "PUBLISHED",
        "SKIPPED",
        "FAILED",
    ] | None = None
    needs_visual: bool | None = None
    needs_video: bool | None = None
    channel_id: str | None = Field(default=None, max_length=128)


class AttachmentCreateIn(BaseModel):
    target_type: Literal["content", "task", "library"]
    target_id: int
    media_type: Literal["link", "file", "photo", "video", "document", "template", "brand_asset"]
    telegram_file_id: str | None = Field(default=None, max_length=512)
    telegram_file_unique_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    filename: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=160)


class AttachmentOut(BaseModel):
    id: int
    target_type: str
    target_id: int
    uploader_id: int
    status: str
    media_type: str
    external_url: str | None
    filename: str | None
    mime_type: str | None
    confirmed_at: str | None


class LibraryCreateIn(BaseModel):
    kind: Literal["link", "file", "photo", "video", "document", "template", "guide", "brand_asset"]
    category: Literal[
        "logos",
        "canva",
        "photo",
        "video",
        "fonts_visual",
        "guides",
        "examples",
        "partner_materials",
        "archive",
    ] = "archive"
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    url: str = Field(min_length=4, max_length=1000)


async def _hub_user(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    level = await media_service.media_access_level(session, user, settings)
    if not media_service.can_use_media_hub(level):
        raise HTTPException(status_code=403, detail="media_hub_access_required")
    return user


async def _manager(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not await media_service.can_manage_media(session, user, settings):
        raise HTTPException(status_code=403, detail="media_desk_access_required")
    return user


def _attachment_out(item: MediaAttachment) -> AttachmentOut:
    return AttachmentOut(
        id=item.id,
        target_type=item.target_type,
        target_id=item.target_id,
        uploader_id=item.uploader_id,
        status=item.status,
        media_type=item.media_type,
        external_url=item.external_url,
        filename=item.filename,
        mime_type=item.mime_type,
        confirmed_at=item.confirmed_at.isoformat() if item.confirmed_at else None,
    )


@router.get("/guide")
async def read_media_guide(_user: User = Depends(_hub_user)) -> dict[str, list[str]]:
    return MEDIA_GUIDE


@router.get("/desk/today-actions", response_model=list[TodayActionOut])
async def read_media_today_actions(
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> list[TodayActionOut]:
    return [TodayActionOut(**item.__dict__) for item in await actionable_today(session)]


@router.get("/desk/team", response_model=list[TeamMemberOut])
async def read_media_team(
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> list[TeamMemberOut]:
    return [TeamMemberOut(**item.__dict__) for item in await team_analytics(session)]


@router.get("/desk/analytics/extended")
async def read_extended_media_analytics(
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, float | None]:
    return {"avg_content_cycle_time_hours": await average_cycle_time_hours(session)}


@router.patch("/desk/content/{content_id}/pipeline")
async def update_media_pipeline(
    content_id: int,
    payload: PipelineUpdateIn,
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        item.title = changes["title"].strip() if changes["title"] else None
    if "status" in changes:
        item.status = changes["status"].lower()
    if "needs_visual" in changes:
        item.needs_visual = bool(changes["needs_visual"])
    if "needs_video" in changes:
        item.needs_video = bool(changes["needs_video"])
    if "channel_id" in changes:
        item.channel_id = changes["channel_id"].strip() if changes["channel_id"] else None
    await session.flush()
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status.upper(),
        "needs_visual": item.needs_visual,
        "needs_video": item.needs_video,
        "channel_id": item.channel_id,
    }


@router.post("/desk/attachments", response_model=AttachmentOut)
async def create_media_attachment(
    payload: AttachmentCreateIn,
    manager: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> AttachmentOut:
    if not payload.external_url and not payload.telegram_file_id:
        raise HTTPException(status_code=422, detail="file_reference_required")
    if payload.target_type == "content" and await session.get(MediaContentItem, payload.target_id) is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    if payload.target_type == "task":
        task = await session.get(Task, payload.target_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
    if payload.target_type == "library" and await session.get(MediaLibraryItem, payload.target_id) is None:
        raise HTTPException(status_code=404, detail="library_item_not_found")
    item = MediaAttachment(
        target_type=payload.target_type,
        target_id=payload.target_id,
        uploader_id=manager.id,
        status="attached",
        media_type=payload.media_type,
        telegram_file_id=payload.telegram_file_id,
        telegram_file_unique_id=payload.telegram_file_unique_id,
        external_url=payload.external_url,
        filename=payload.filename,
        mime_type=payload.mime_type,
        confirmed_at=datetime.now(timezone.utc),
    )
    session.add(item)
    await session.flush()
    return _attachment_out(item)


@router.get("/desk/attachments/{target_type}/{target_id}", response_model=list[AttachmentOut])
async def read_media_attachments(
    target_type: Literal["content", "task", "library"],
    target_id: int,
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> list[AttachmentOut]:
    return [
        _attachment_out(item)
        for item in await attached_files(session, target_type=target_type, target_id=target_id)
    ]


@router.get("/tasks/{task_id}/attachments", response_model=list[AttachmentOut])
async def read_my_media_task_attachments(
    task_id: int,
    user: User = Depends(_hub_user),
    session: AsyncSession = Depends(get_session),
) -> list[AttachmentOut]:
    task = await session.get(Task, task_id)
    if task is None or not await task_service.can_view(session, task, user):
        raise HTTPException(status_code=404, detail="task_not_found")
    return [
        _attachment_out(item)
        for item in await attached_files(session, target_type="task", target_id=task_id)
    ]


@router.post("/desk/library")
async def create_media_library_item(
    payload: LibraryCreateIn,
    _user: User = Depends(_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    item = MediaLibraryItem(
        kind=payload.kind,
        category=payload.category,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        url=payload.url.strip(),
        sort_order=100,
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return {
        "id": item.id,
        "kind": item.kind,
        "category": item.category,
        "title": item.title,
        "description": item.description,
        "url": item.url,
    }
