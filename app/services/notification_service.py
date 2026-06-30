import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import Settings

logger = logging.getLogger(__name__)


async def safe_send(bot: Bot, chat_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver notification to chat %s", chat_id)
        return False


async def notify_admins(
    bot: Bot, settings: Settings, text: str, reply_markup=None
) -> None:
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    for chat_id in recipients:
        await safe_send(bot, chat_id, text, reply_markup)


async def broadcast(
    bot: Bot, telegram_ids: Iterable[int], text: str
) -> tuple[int, int]:
    sent = failed = 0
    for telegram_id in telegram_ids:
        if await safe_send(bot, telegram_id, text):
            sent += 1
        else:
            failed += 1
    return sent, failed
