import logging
from collections.abc import Iterable
from functools import lru_cache

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import User
from app.utils.constants import Role

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _session_factory(database_url: str) -> async_sessionmaker:
    """Return a cached lightweight session factory for notification recipient lookup."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _database_admin_ids(settings: Settings) -> set[int]:
    """Load active administrators from the database.

    Notifications used to rely only on ADMIN_IDS from Render. That meant an account
    promoted to administrator inside the bot did not receive new applications when
    ADMIN_IDS was empty or outdated.
    """
    try:
        factory = _session_factory(settings.database_url)
        async with factory() as session:
            values = await session.scalars(
                select(User.telegram_id).where(
                    User.role == Role.ADMIN,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                )
            )
            return {int(value) for value in values.all() if value}
    except Exception:
        logger.exception("Could not load administrator recipients from database")
        return set()


async def safe_send(bot: Bot, chat_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver notification to chat %s", chat_id)
        return False


async def notify_admins(
    bot: Bot, settings: Settings, text: str, reply_markup=None
) -> tuple[int, int]:
    recipients = set(settings.admin_ids)
    recipients.update(await _database_admin_ids(settings))
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)

    sent = failed = 0
    if not recipients:
        logger.error(
            "Admin notification was not sent: no recipients configured and no active admin users found"
        )
        return sent, failed

    for chat_id in recipients:
        if await safe_send(bot, chat_id, text, reply_markup):
            sent += 1
        else:
            failed += 1
    return sent, failed


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
