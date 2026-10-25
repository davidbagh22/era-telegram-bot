from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.audit_service import audit
from app.services.authorization_service import is_full_admin
from app.services.general_chat_content_service import (
    calendar_items,
    create_custom_holiday,
    custom_holidays,
    delivery_history,
    get_autocontent_settings,
    save_item_override,
    send_item_now,
    static_item_by_id,
    update_autocontent_settings,
    update_custom_content,
)

router = APIRouter(prefix="/admin/autocontent", tags=["admin-autocontent"])


async def require_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class SettingsPatch(BaseModel):
    paused: bool | None = None
    quotes: bool | None = None
    challenges: bool | None = None
    themes: bool | None = None
    holidays: bool | None = None


class ItemPatch(BaseModel):
    text: str | None = Field(default=None, max_length=4096)
    is_enabled: bool | None = None
    is_skipped: bool | None = None
    title: str | None = Field(default=None, max_length=180)


class HolidayCreate(BaseModel):
    date_key: str = Field(min_length=5, max_length=10)
    title: str = Field(min_length=1, max_length=180)
    text: str = Field(min_length=1, max_length=4096)


class PreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


@router.get("/overview")
async def overview(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    return {
        "settings": await get_autocontent_settings(session),
        "items": await calendar_items(
            session,
            start=today,
            days=2,
            timezone_name=settings.timezone,
        ),
        "custom_holidays": await custom_holidays(session),
        "timezone": settings.timezone,
    }


@router.get("/calendar")
async def calendar(
    start: date | None = None,
    days: int = Query(default=31, ge=1, le=90),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    current = start or datetime.now(ZoneInfo(settings.timezone)).date()
    return await calendar_items(
        session,
        start=current,
        days=days,
        timezone_name=settings.timezone,
    )


@router.get("/history")
async def history(
    limit: int = Query(default=100, ge=1, le=300),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await delivery_history(session, limit)


@router.patch("/settings")
async def patch_settings(
    body: SettingsPatch,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    changes = body.model_dump(exclude_none=True)
    try:
        result = await update_autocontent_settings(session, changes, actor_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit(
        session,
        actor_id=admin.id,
        action="autocontent.settings_updated",
        entity_type="general_autocontent",
        new_value=changes,
    )
    await session.commit()
    return result


@router.patch("/items/{content_id}")
async def patch_item(
    content_id: str,
    body: ItemPatch,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    try:
        if content_id.startswith("holiday-custom-"):
            row = await update_custom_content(
                session,
                content_id,
                actor_id=admin.id,
                text=body.text,
                is_enabled=body.is_enabled,
                is_skipped=body.is_skipped,
                title=body.title,
            )
            result = {
                "content_id": row.content_id,
                "text": row.text,
                "is_enabled": row.is_enabled,
                "is_skipped": row.is_skipped,
                "title": row.title,
            }
        else:
            row = await save_item_override(
                session,
                content_id,
                actor_id=admin.id,
                text=body.text,
                is_enabled=body.is_enabled,
                is_skipped=body.is_skipped,
            )
            base = static_item_by_id(content_id)
            result = {
                "content_id": row.content_id,
                "text": row.override_text or (base.text if base else ""),
                "is_enabled": row.is_enabled,
                "is_skipped": row.is_skipped,
                "title": base.title if base else None,
            }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="content_not_found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit(
        session,
        actor_id=admin.id,
        action="autocontent.item_updated",
        entity_type="general_autocontent_item",
        new_value={"content_id": content_id, **payload},
    )
    await session.commit()
    return result


@router.post("/items/{content_id}/skip")
async def skip_item(
    content_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        if content_id.startswith("holiday-custom-"):
            row = await update_custom_content(
                session,
                content_id,
                actor_id=admin.id,
                is_skipped=True,
            )
            skipped = row.is_skipped
        else:
            row = await save_item_override(
                session,
                content_id,
                actor_id=admin.id,
                is_skipped=True,
            )
            skipped = row.is_skipped
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="content_not_found") from exc
    await audit(
        session,
        actor_id=admin.id,
        action="autocontent.item_skipped",
        entity_type="general_autocontent_item",
        new_value={"content_id": content_id},
    )
    await session.commit()
    return {"content_id": content_id, "skipped": skipped}


@router.post("/items/{content_id}/send-now")
async def send_now(
    content_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        outcome = await send_item_now(bot, settings, session, content_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="content_not_found") from exc
    await audit(
        session,
        actor_id=admin.id,
        action="autocontent.manual_send",
        entity_type="general_autocontent_item",
        entity_id=outcome.delivery_id,
        new_value={"content_id": content_id, "status": outcome.status},
    )
    await session.commit()
    return {
        "status": outcome.status,
        "delivery_id": outcome.delivery_id,
        "message_id": outcome.message_id,
    }


@router.post("/holidays")
async def add_holiday(
    body: HolidayCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = await create_custom_holiday(
            session,
            date_key=body.date_key,
            title=body.title,
            text=body.text,
            actor_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit(
        session,
        actor_id=admin.id,
        action="autocontent.holiday_created",
        entity_type="general_autocontent_item",
        entity_id=row.id,
        new_value={"content_id": row.content_id, "date_key": row.date_key},
    )
    await session.commit()
    return {
        "content_id": row.content_id,
        "date_key": row.date_key,
        "title": row.title,
        "text": row.text,
        "is_enabled": row.is_enabled,
        "is_skipped": row.is_skipped,
    }


@router.post("/preview")
async def preview(
    body: PreviewIn,
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    return {
        "text": body.text,
        "characters": len(body.text),
        "lines": body.text.count("\n") + 1,
        "parse_mode": "HTML",
    }
