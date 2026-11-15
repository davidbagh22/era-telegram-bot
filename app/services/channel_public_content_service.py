from __future__ import annotations

from datetime import datetime

from aiogram import Bot

from app.config import Settings
from app.services.daily_public_content_service import (
    MOSCOW,
    WINDOW_END,
    WINDOW_START,
    _channel_target,
    _has_explicit_channel_approval,
    _deliver_once,
    scheduled_minute,
    text_for_day,
)


async def run_daily_channel_content(bot: Bot, settings: Settings, session_factory) -> None:
    """Publish the daily ERA channel post without sending quotes to the general chat."""
    local = datetime.now(MOSCOW)
    minute = local.hour * 60 + local.minute
    if minute < WINDOW_START or minute >= WINDOW_END:
        return

    day = local.date().isoformat()
    kind = "channel_post"
    target = _channel_target(settings)
    if target is None or minute < scheduled_minute(day, kind):
        return

    content = text_for_day(day, kind)
    # This legacy entrypoint is still used by the polling process. Keep the
    # same exact day/destination/text approval as the web scheduler.
    if not _has_explicit_channel_approval(day, target, content):
        return

    await _deliver_once(
        bot,
        session_factory,
        key=f"era-daily:{kind}:{day}",
        chat_id=target,
        kind=f"era_daily_{kind}",
        text=content,
    )
