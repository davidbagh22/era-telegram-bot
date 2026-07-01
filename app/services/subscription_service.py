import logging
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import Settings

logger = logging.getLogger(__name__)


def channel_target(settings: Settings) -> int | str | None:
    if settings.era_channel_id not in (None, ""):
        return settings.era_channel_id
    path = urlparse(settings.era_channel_url).path.strip("/")
    if path and not path.startswith("+") and path != "joinchat":
        return f"@{path}"
    return None


async def is_channel_member(bot: Bot, telegram_id: int, settings: Settings) -> bool:
    if telegram_id in settings.admin_ids:
        return True
    target = channel_target(settings)
    if target is None:
        logger.error(
            "ERA_CHANNEL_ID is required for a private channel; subscription gate is closed"
        )
        return False
    try:
        member = await bot.get_chat_member(target, telegram_id)
        return member.status not in {"left", "kicked"}
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception(
            "Subscription check failed. Ensure the bot is an administrator of ERA channel."
        )
        return False
