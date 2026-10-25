from __future__ import annotations

from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.media_models import MediaContentItem
from app.database.models import User
from app.services import media_service
from app.utils.telegram_html import sanitize_telegram_html

router = APIRouter(prefix="/media", tags=["media"])


class PublishOut(BaseModel):
    ok: bool
    code: str
    message_id: int | None


async def _require_media_desk(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not await media_service.can_manage_media(session, user, settings):
        raise HTTPException(status_code=403, detail="media_desk_access_required")
    return user


class _RichMediaBot:
    """Narrow Bot proxy used only by Media Desk channel publication.

    The delivery/idempotency logic remains in media_service.publish_content;
    only send_message is adapted so approved editor markup is rendered by
    Telegram instead of appearing as one plain monolithic text block.
    """

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bot, name)

    async def send_message(self, *, chat_id: int | str, text: str, **kwargs: Any):
        kwargs["parse_mode"] = "HTML"
        return await self._bot.send_message(
            chat_id=chat_id,
            text=sanitize_telegram_html(text),
            **kwargs,
        )


@router.post("/desk/content/{content_id}/publish-now", response_model=PublishOut)
async def publish_media_content_rich(
    content_id: int,
    _manager: User = Depends(_require_media_desk),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> PublishOut:
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    item = await session.get(MediaContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content_not_found")
    result = await media_service.publish_content(
        session,
        _RichMediaBot(bot),  # type: ignore[arg-type]
        settings,
        item,
        manual=True,
    )
    return PublishOut(ok=result.ok, code=result.code, message_id=result.message_id)
