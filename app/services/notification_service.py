import asyncio
import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import User
from app.database.system_models import NotificationDelivery
from app.utils.constants import Role

logger = logging.getLogger(__name__)

# A process that dies after claiming a delivery must not suppress it forever.
# Five minutes is long enough to cover normal Telegram retries and short enough
# for the scheduler to recover automatically on its next pass.
_DELIVERY_LEASE = timedelta(minutes=5)
_TERMINAL_DELIVERY_STATUSES = {"sent", "blocked", "unreachable", "skipped"}


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


@dataclass(frozen=True)
class NotificationDeliveryResult:
    """Outcome of one durable automatic notification attempt."""

    sent: bool
    status: str
    duplicate: bool
    attempt_count: int
    error_code: str | None = None


@lru_cache(maxsize=8)
def _session_factory(database_url: str) -> async_sessionmaker:
    """Return a cached lightweight session factory for notification persistence."""
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


def _payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _delivery_failure(exc: TelegramAPIError) -> tuple[str, str, bool]:
    """Map Telegram errors to non-sensitive durable statuses/codes."""
    if isinstance(exc, TelegramForbiddenError):
        return "blocked", "telegram_forbidden", False
    if isinstance(exc, TelegramBadRequest):
        # Telegram uses BadRequest both for malformed payloads and for identities
        # it cannot resolve. Only classify the well-known identity cases as
        # unreachable; never persist the raw Telegram error text.
        message = str(exc).casefold()
        if any(
            marker in message
            for marker in (
                "chat not found",
                "user not found",
                "peer_id_invalid",
                "bot can't initiate conversation",
            )
        ):
            return "unreachable", "telegram_unreachable", False
        return "failed", "telegram_bad_request", False
    if isinstance(exc, TelegramRetryAfter):
        return "failed", "telegram_retry_after", True
    if isinstance(exc, TelegramNetworkError):
        return "failed", "telegram_network", True
    if isinstance(exc, TelegramServerError):
        return "failed", "telegram_server", True
    return "failed", "telegram_api", False


async def _claim_delivery(
    settings: Settings,
    *,
    delivery_key: str,
    chat_id: int,
    notification_type: str,
    payload_hash: str,
) -> NotificationDeliveryResult | None:
    """Atomically claim a delivery or return an existing terminal/in-flight result.

    This uses a dedicated DB transaction, intentionally separate from the caller's
    business transaction. A Telegram or ledger failure therefore cannot roll back
    registration, approval, scoring, project or event state.
    """
    if not delivery_key or len(delivery_key) > 200:
        raise ValueError("delivery_key must be 1..200 characters")
    if not notification_type or len(notification_type) > 64:
        raise ValueError("notification_type must be 1..64 characters")

    factory = _session_factory(settings.database_url)
    now = datetime.now(timezone.utc)

    for _ in range(2):
        async with factory() as session:
            row = await session.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.delivery_key == delivery_key)
                .with_for_update()
            )
            if row is None:
                row = NotificationDelivery(
                    delivery_key=delivery_key,
                    chat_id=int(chat_id),
                    notification_type=notification_type,
                    status="pending",
                    attempt_count=1,
                    last_attempt_at=now,
                    payload_hash=payload_hash,
                )
                session.add(row)
                try:
                    await session.commit()
                    return None
                except IntegrityError:
                    # Another worker inserted the same idempotency key between
                    # our SELECT and INSERT. Roll back and evaluate its row.
                    await session.rollback()
                    continue

            if row.payload_hash != payload_hash or int(row.chat_id) != int(chat_id):
                logger.error(
                    "Notification delivery key reused with different payload/recipient key=%s",
                    delivery_key,
                )
                return NotificationDeliveryResult(
                    sent=False,
                    status="conflict",
                    duplicate=True,
                    attempt_count=row.attempt_count,
                    error_code="delivery_key_conflict",
                )

            if row.status in _TERMINAL_DELIVERY_STATUSES:
                return NotificationDeliveryResult(
                    sent=row.status == "sent",
                    status=row.status,
                    duplicate=True,
                    attempt_count=row.attempt_count,
                    error_code=row.error_code,
                )

            last_attempt = _aware_utc(row.last_attempt_at)
            if (
                row.status == "pending"
                and last_attempt is not None
                and now - last_attempt < _DELIVERY_LEASE
            ):
                # A worker currently owns this delivery. Do not send a duplicate.
                return NotificationDeliveryResult(
                    sent=False,
                    status="pending",
                    duplicate=True,
                    attempt_count=row.attempt_count,
                    error_code="delivery_in_flight",
                )

            row.status = "pending"
            row.error_code = None
            row.attempt_count += 1
            row.last_attempt_at = now
            await session.commit()
            return None

    # If the insert race could not be resolved, fail closed rather than sending
    # without an idempotency record.
    return NotificationDeliveryResult(
        sent=False,
        status="failed",
        duplicate=False,
        attempt_count=0,
        error_code="delivery_claim_race",
    )


async def _record_delivery_outcome(
    settings: Settings,
    *,
    delivery_key: str,
    status: str,
    error_code: str | None,
    sent_at: datetime | None = None,
) -> int:
    factory = _session_factory(settings.database_url)
    async with factory() as session:
        row = await session.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.delivery_key == delivery_key)
            .with_for_update()
        )
        if row is None:
            logger.error("Notification delivery row disappeared key=%s", delivery_key)
            return 0
        row.status = status
        row.error_code = error_code
        if sent_at is not None:
            row.sent_at = sent_at
        await session.commit()
        return row.attempt_count


async def _record_retry_attempt(settings: Settings, *, delivery_key: str) -> int:
    factory = _session_factory(settings.database_url)
    async with factory() as session:
        row = await session.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.delivery_key == delivery_key)
            .with_for_update()
        )
        if row is None:
            return 0
        row.attempt_count += 1
        row.last_attempt_at = datetime.now(timezone.utc)
        await session.commit()
        return row.attempt_count


async def safe_send_once(
    bot: Bot,
    settings: Settings,
    chat_id: int,
    text: str,
    *,
    delivery_key: str,
    notification_type: str = "generic",
    reply_markup=None,
    parse_mode: str | None = None,
    max_attempts: int = 3,
) -> NotificationDeliveryResult:
    """Send one automatic notification durably and idempotently.

    The caller supplies a stable semantic key such as
    ``event:42:published:123456``. Duplicate runs, process restarts and scheduler
    retries reuse the same key and therefore do not send a second message.

    The ledger is committed before Telegram is called and updated afterwards in
    a separate transaction, preserving the existing commit-before-notification
    contract. Message text and reply markup are never stored.
    """
    content_hash = _payload_hash(text)
    try:
        claimed = await _claim_delivery(
            settings,
            delivery_key=delivery_key,
            chat_id=chat_id,
            notification_type=notification_type,
            payload_hash=content_hash,
        )
    except Exception:
        logger.exception("Could not claim durable notification key=%s", delivery_key)
        return NotificationDeliveryResult(
            sent=False,
            status="failed",
            duplicate=False,
            attempt_count=0,
            error_code="delivery_ledger_unavailable",
        )
    if claimed is not None:
        return claimed

    max_attempts = max(1, int(max_attempts))
    attempt_count = 1
    while True:
        try:
            kwargs = {"reply_markup": reply_markup}
            if parse_mode is not None:
                kwargs["parse_mode"] = parse_mode
            await bot.send_message(chat_id, text, **kwargs)
            try:
                attempt_count = await _record_delivery_outcome(
                    settings,
                    delivery_key=delivery_key,
                    status="sent",
                    error_code=None,
                    sent_at=datetime.now(timezone.utc),
                )
            except Exception:
                # Telegram accepted the message. Never retry immediately if only
                # the acknowledgement write failed; that would create a duplicate.
                logger.exception(
                    "Telegram notification sent but delivery acknowledgement failed key=%s",
                    delivery_key,
                )
                return NotificationDeliveryResult(
                    sent=True,
                    status="sent_unconfirmed",
                    duplicate=False,
                    attempt_count=attempt_count,
                    error_code="delivery_ack_failed",
                )
            return NotificationDeliveryResult(
                sent=True,
                status="sent",
                duplicate=False,
                attempt_count=attempt_count,
            )
        except TelegramAPIError as exc:
            status, error_code, temporary = _delivery_failure(exc)
            if temporary and attempt_count < max_attempts:
                if isinstance(exc, TelegramRetryAfter):
                    await asyncio.sleep(max(0, exc.retry_after))
                else:
                    await asyncio.sleep(min(2**attempt_count, 10))
                try:
                    attempt_count = await _record_retry_attempt(
                        settings, delivery_key=delivery_key
                    )
                except Exception:
                    logger.exception(
                        "Could not persist notification retry key=%s", delivery_key
                    )
                    return NotificationDeliveryResult(
                        sent=False,
                        status="failed",
                        duplicate=False,
                        attempt_count=attempt_count,
                        error_code="delivery_retry_ledger_failed",
                    )
                continue

            try:
                attempt_count = await _record_delivery_outcome(
                    settings,
                    delivery_key=delivery_key,
                    status=status,
                    error_code=error_code,
                )
            except Exception:
                logger.exception(
                    "Could not persist notification failure key=%s", delivery_key
                )
            logger.warning(
                "Durable notification failed key=%s status=%s code=%s",
                delivery_key,
                status,
                error_code,
            )
            return NotificationDeliveryResult(
                sent=False,
                status=status,
                duplicate=False,
                attempt_count=attempt_count,
                error_code=error_code,
            )


async def safe_send(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    *,
    parse_mode: str | None = None,
) -> bool:
    """Best-effort transport for interactive replies and non-repeatable messages.

    Scheduled/automatic notifications must use ``safe_send_once`` or a
    subsystem-specific durable delivery ledger.
    """
    try:
        kwargs = {"reply_markup": reply_markup}
        # Preserve the historical send_message call shape for every existing
        # plain-text caller; only FAQ/rich-text callers opt into parse_mode.
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        await bot.send_message(chat_id, text, **kwargs)
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


async def notify_admins_once(
    bot: Bot,
    settings: Settings,
    text: str,
    *,
    delivery_key: str,
    notification_type: str,
    reply_markup=None,
) -> tuple[int, int, int]:
    """Durably notify all admins once per semantic event and recipient."""
    recipients = await admin_notification_recipients(settings)
    sent = failed = duplicates = 0
    for chat_id in recipients:
        result = await safe_send_once(
            bot,
            settings,
            chat_id,
            text,
            delivery_key=f"{delivery_key}:{chat_id}",
            notification_type=notification_type,
            reply_markup=reply_markup,
        )
        if result.duplicate:
            duplicates += 1
        elif result.sent:
            sent += 1
        else:
            failed += 1
    return sent, failed, duplicates


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


async def broadcast_detailed_once(
    bot: Bot,
    settings: Settings,
    telegram_ids: Iterable[int],
    text: str,
    *,
    delivery_key: str,
    notification_type: str,
    reply_markup=None,
    concurrency: int = 8,
    max_attempts: int = 3,
) -> BroadcastResult:
    """Durable/idempotent broadcast for scheduled and automatic messages."""
    recipients, input_duplicates = _dedupe_recipients(telegram_ids)
    result = BroadcastResult(total=len(recipients), duplicates=input_duplicates)
    if not recipients:
        return result

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def send_one(chat_id: int) -> tuple[int, NotificationDeliveryResult]:
        async with semaphore:
            delivery = await safe_send_once(
                bot,
                settings,
                chat_id,
                text,
                delivery_key=f"{delivery_key}:{chat_id}",
                notification_type=notification_type,
                reply_markup=reply_markup,
                max_attempts=max_attempts,
            )
            return chat_id, delivery

    deliveries = await asyncio.gather(*(send_one(chat_id) for chat_id in recipients))
    for chat_id, delivery in deliveries:
        if delivery.duplicate:
            result.duplicates += 1
        elif delivery.sent:
            result.sent += 1
        else:
            result.failed += 1
            result.failures.append(
                BroadcastFailure(
                    chat_id=chat_id,
                    reason=delivery.error_code or delivery.status,
                    temporary=delivery.status == "failed",
                )
            )
    return result


async def broadcast(
    bot: Bot, telegram_ids: Iterable[int], text: str
) -> tuple[int, int]:
    result = await broadcast_detailed(bot, telegram_ids, text)
    return result.sent, result.failed
