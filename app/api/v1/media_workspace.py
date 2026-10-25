from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services import media_workspace_service as service
from app.services import media_scope_service as scopes

router = APIRouter(prefix="/media/workspaces", tags=["media"])
Area = Literal["era", "ksoors"]
Platform = Literal["telegram", "instagram", "facebook", "tiktok", "youtube"]
CalendarStatusGroup = Literal["all", "active", "published"]


class CalendarCreate(BaseModel):
    request_key: UUID
    title: str = Field(min_length=2, max_length=255)
    body: str = Field(default="", max_length=4096)
    platform: Platform = "telegram"
    scheduled_at: datetime | None = None
    responsible_id: int | None = Field(default=None, gt=0)
    materials: str = Field(default="", max_length=3000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Введите название материала")
        return value.strip()

    @field_validator("scheduled_at")
    @classmethod
    def aware_date(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Укажите часовой пояс даты")
            return value.astimezone(timezone.utc)
        return value


class CalendarUpdate(BaseModel):
    revision: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    body: str | None = Field(default=None, max_length=4096)
    scheduled_at: datetime | None = None
    responsible_id: int | None = Field(default=None, gt=0)
    materials: str | None = Field(default=None, max_length=3000)
    status: Literal["planned", "in_progress", "review", "ready", "published", "skipped"] | None = None
    publication_url: str | None = Field(default=None, max_length=1000)

    _aware_date = field_validator("scheduled_at")(CalendarCreate.aware_date.__func__)


def _error(error):
    code = 403 if isinstance(error, PermissionError) else 404 if isinstance(error, LookupError) else 409
    return HTTPException(status_code=code, detail=str(error))


@router.get("")
async def workspaces(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session),
                     settings: Settings = Depends(get_settings)):
    try:
        await service.require_access(session, user, settings)
    except PermissionError as error:
        raise _error(error) from error
    can_manage = await service.media_service.can_manage_media(session, user, settings)
    return [{"id": key, **value, "can_manage": await scopes.can_edit_calendar(session, user, settings, key),
             "can_assign_editors": can_manage} for key, value in service.AREAS.items()]


@router.get("/{area}/calendar")
async def calendar(area: Area, before_id: int | None = Query(default=None, gt=0),
                   status_group: CalendarStatusGroup = Query(default="all"),
                   user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session),
                   settings: Settings = Depends(get_settings)):
    try:
        await service.require_access(session, user, settings)
    except PermissionError as error:
        raise _error(error) from error
    return await service.calendar(session, area, before_id=before_id, status_group=status_group)


@router.post("/{area}/calendar")
async def create(area: Area, payload: CalendarCreate, user: User = Depends(get_current_user),
                 session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    try:
        item = await service.create_entry(session, user, settings, area,
            payload.model_dump(exclude={"request_key"}), str(payload.request_key))
    except (PermissionError, ValueError) as error:
        raise _error(error) from error
    return service.item_out(item)


@router.patch("/{area}/calendar/{item_id}")
async def update(area: Area, item_id: int, payload: CalendarUpdate, user: User = Depends(get_current_user),
                 session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    changes = payload.model_dump(exclude_unset=True, exclude={"revision"})
    if any(changes.get(key, "valid") is None for key in ("title", "body", "materials", "status")):
        raise HTTPException(status_code=422, detail="Поле не может быть пустым")
    try:
        item = await service.update_entry(session, user, settings, area, item_id, changes, payload.revision)
    except (PermissionError, LookupError, ValueError) as error:
        raise _error(error) from error
    return service.item_out(item)


class EditorChange(BaseModel):
    user_id: int = Field(gt=0)
    enabled: bool
    revision: int = Field(ge=0)


@router.get("/{area}/team")
async def area_team(area: Area, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session),
                    settings: Settings = Depends(get_settings)):
    try:
        await service.require_access(session, user, settings)
    except PermissionError as error:
        raise _error(error) from error
    return [{"id": member.id, "name": f"{member.first_name} {member.last_name or ''}".strip()}
            for member in await service.media_service.list_media_members(session)
            if not member.is_blocked and not member.is_archived and member.application_status == "approved"]


@router.get("/{area}/editors")
async def editors(area: Area, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session),
                   settings: Settings = Depends(get_settings)):
    try:
        return await scopes.scope_state(session, user, settings, area)
    except PermissionError as error:
        raise _error(error) from error


@router.post("/{area}/editors")
async def change_editor(area: Area, payload: EditorChange, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    try:
        return await scopes.set_editor(session, user, settings, area, payload.user_id, payload.enabled, payload.revision)
    except (PermissionError, ValueError) as error:
        raise _error(error) from error
