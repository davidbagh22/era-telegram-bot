import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import Settings

logger = logging.getLogger(__name__)


async def is_channel_member(bot: Bot, telegram_id: int, settings: Settings) -> bool:
    if settings.era_channel_id in (None, ""):
        logger.warning("ERA_CHANNEL_ID is not set; subscription gate is disabled")
        return True
    try:
        member = await bot.get_chat_member(settings.era_channel_id, telegram_id)
        return member.status not in {"left", "kicked"}
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception(
            "Subscription check failed. Ensure the bot is an administrator of ERA channel."
        )
        return False
