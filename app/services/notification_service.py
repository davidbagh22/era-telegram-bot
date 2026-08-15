import logging
import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import User
from app.utils.constants import Role

logger = logging.getLogger(__name__)


@dataclass
class BroadcastFailure:
    chat_id: int
    reason: str
    temporary: bool


@dataclass
class BroadcastResult:
    total: int = 0
    sent: int = 0
    failed: int = 0
    duplicates: int = 0
    failures: list[BroadcastFailure] = field(default_factory=list)

    @property
    def permanent_failed(self) -> int:
        return sum(1 for item in self.failures if not item.temporary)

    @property
    def temporary_failed(self) -> int:
        return sum(1 for item in self.failures if item.temporary)


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


async def safe_send(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    *,
    parse_mode: str | None = None,
) -> bool:
    try:
        await bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver notification to chat %s", chat_id)
        return False


async def safe_send_photo(bot: Bot, chat_id: int, photo, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver photo notification to chat %s", chat_id)
        return False


async def safe_send_document(bot: Bot, chat_id: int, document, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await bot.send_document(chat_id, document, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver document notification to chat %s", chat_id)
        return False


async def safe_send_video(bot: Bot, chat_id: int, video, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await bot.send_video(chat_id, video, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not deliver video notification to chat %s", chat_id)
        return False


async def safe_answer_photo(message, photo, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await message.answer_photo(photo, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not answer with photo")
        return False


async def safe_answer_document(message, document, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await message.answer_document(document, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not answer with document")
        return False


async def safe_answer_video(message, video, *, caption: str | None = None, reply_markup=None) -> bool:
    try:
        await message.answer_video(video, caption=caption, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.exception("Could not answer with video")
        return False


async def safe_answer_media(
    message,
    media,
    *,
    media_type: str | None = None,
    caption: str | None = None,
    reply_markup=None,
) -> bool:
    preferred = media_type if media_type in {"photo", "video", "document"} else None
    order = [preferred] if preferred else []
    order.extend(item for item in ("photo", "video", "document") if item not in order)

    for item in order:
        if item == "photo" and await safe_answer_photo(
            message, media, caption=caption, reply_markup=reply_markup
        ):
            return True
        if item == "video" and await safe_answer_video(
            message, media, caption=caption, reply_markup=reply_markup
        ):
            return True
        if item == "document" and await safe_answer_document(
            message, media, caption=caption, reply_markup=reply_markup
        ):
            return True
    return False


async def admin_notification_recipients(settings: Settings) -> set[int]:
    """Return actual administrators for automatic administrative notifications.

    The leaders chat is intentionally not included here. Automatic events such as
    new registration applications must stay private to admins. Messages explicitly
    sent to the leaders chat from Admin Mode continue to use the dedicated chat
    broadcast path and are unaffected by this recipient list.
    """
    recipients = set(settings.admin_ids)
    recipients.update(await _database_admin_ids(settings))
    return recipients


async def notify_admins(
    bot: Bot, settings: Settings, text: str, reply_markup=None
) -> tuple[int, int]:
    recipients = await admin_notification_recipients(settings)

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


def _dedupe_recipients(telegram_ids: Iterable[int]) -> tuple[list[int], int]:
    seen: set[int] = set()
    recipients: list[int] = []
    duplicates = 0
    for raw_id in telegram_ids:
        try:
            telegram_id = int(raw_id)
        except (TypeError, ValueError):
            duplicates += 1
            continue
        if telegram_id in seen:
            duplicates += 1
            continue
        seen.add(telegram_id)
        recipients.append(telegram_id)
    return recipients, duplicates


def _temporary_error(exc: Exception) -> bool:
    return isinstance(exc, (TelegramRetryAfter, TelegramNetworkError, TelegramServerError))


def _permanent_error(exc: Exception) -> bool:
    return isinstance(exc, (TelegramForbiddenError, TelegramBadRequest))


async def _send_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    reply_markup=None,
    max_attempts: int = 3,
) -> BroadcastFailure | None:
    attempt = 1
    while True:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            return None
        except TelegramRetryAfter as exc:
            if attempt >= max_attempts:
                return BroadcastFailure(chat_id, f"retry_after:{exc.retry_after}", temporary=True)
            await asyncio.sleep(max(0, exc.retry_after))
        except (TelegramNetworkError, TelegramServerError) as exc:
            if attempt >= max_attempts:
                return BroadcastFailure(chat_id, exc.__class__.__name__, temporary=True)
            await asyncio.sleep(min(2**attempt, 10))
        except TelegramAPIError as exc:
            temporary = _temporary_error(exc) and not _permanent_error(exc)
            return BroadcastFailure(chat_id, exc.__class__.__name__, temporary=temporary)
        attempt += 1


async def broadcast_detailed(
    bot: Bot,
    telegram_ids: Iterable[int],
    text: str,
    *,
    reply_markup=None,
    concurrency: int = 8,
    max_attempts: int = 3,
) -> BroadcastResult:
    recipients, duplicates = _dedupe_recipients(telegram_ids)
    result = BroadcastResult(total=len(recipients), duplicates=duplicates)
    if not recipients:
        return result

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def send_one(chat_id: int) -> BroadcastFailure | None:
        async with semaphore:
            return await _send_with_retry(
                bot,
                chat_id,
                text,
                reply_markup=reply_markup,
                max_attempts=max_attempts,
            )

    failures = await asyncio.gather(*(send_one(chat_id) for chat_id in recipients))
    for failure in failures:
        if failure is None:
            result.sent += 1
        else:
            result.failed += 1
            result.failures.append(failure)
            logger.warning(
                "Broadcast delivery failed chat=%s reason=%s temporary=%s",
                failure.chat_id,
                failure.reason,
                failure.temporary,
            )
    return result


async def broadcast(
    bot: Bot, telegram_ids: Iterable[int], text: str
) -> tuple[int, int]:
    result = await broadcast_detailed(bot, telegram_ids, text)
    return result.sent, result.failed
