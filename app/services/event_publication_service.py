"""Durable event announcements, including uploaded posters and full quick text."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from html import escape

from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, text as sql_text

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.database.system_models import NotificationDelivery
from app.services.general_topics_service import send_general_topic_once
from app.services.notification_service import broadcast_detailed_once
from app.utils.constants import ApplicationStatus, EventStatus
from app.utils.deep_links import telegram_event_miniapp_url

logger = logging.getLogger(__name__)
PUBLIC_STATUSES = {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}
RECOVERY_CURSOR_KEY = "event-announcement-recovery:cursor"
RECOVERY_BATCH_SIZE = 20


def text_parts(text: str, first_limit: int = 4000) -> list[str]:
    """Preserve every character while respecting Telegram's UTF-16 limits."""
    parts: list[str] = []
    start = 0
    units = 0
    limit = first_limit
    for index, char in enumerate(text):
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > limit:
            parts.append(text[start:index])
            start, units, limit = index, 0, 4000
        units += size
    parts.append(text[start:])
    return parts


def escaped_text_parts(text: str, first_limit: int = 4000) -> list[str]:
    """Split HTML-escaped plain text without breaking an entity or Telegram limit."""
    escaped = escape(text, quote=False)
    tokens = re.findall(r"&(?:amp|lt|gt);|.", escaped, flags=re.DOTALL)
    parts: list[str] = []
    current: list[str] = []
    units = 0
    limit = first_limit
    for token in tokens:
        size = len(token.encode("utf-16-le")) // 2
        if units + size > limit and current:
            parts.append("".join(current))
            current = []
            units = 0
            limit = 4000
        current.append(token)
        units += size
    parts.append("".join(current))
    return parts


async def public_event_keyboard(bot, settings, event):
    username = (settings.bot_username or "").strip() or (await bot.get_me()).username
    url = telegram_event_miniapp_url(username or "", event.id)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть мероприятие", url=url)
    ]]) if url else None


def announcement_text(event, experience) -> str:
    schedule = f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n📍 {event.location}"
    if getattr(experience, "creation_mode", "wizard") == "quick":
        text = experience.full_description or event.description
        title = "" if text.split("\n", 1)[0].strip() == event.title.strip() else f"{event.title}\n\n"
        return f"{title}{text}\n\n{schedule}"
    return (
        f"🔥 {event.title}\n\n{experience.short_description or event.description}\n\n"
        f"{schedule}"
    )


async def publish_event_announcement(bot, settings, session, event, experience) -> bool:
    if bot is None:
        return False
    markup = await public_event_keyboard(bot, settings, event)
    text = announcement_text(event, experience)
    poster = getattr(experience, "poster_bytes", None)
    parts = escaped_text_parts(text, 1000 if poster else 4000)
    for index, part in enumerate(parts):
        media = {}
        if index == 0 and poster:
            content_type = experience.poster_content_type or "image/jpeg"
            extension = {"image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
            media["photo"] = BufferedInputFile(poster, filename=f"event-{event.id}.{extension}")
        result = await send_general_topic_once(
            bot, settings, "announcements", part, parse_mode="HTML",
            reply_markup=markup if index == len(parts) - 1 else None,
            delivery_key=f"event:{event.id}:published" + (f":part:{index}" if index else ""),
            max_attempts=1,
            **media,
        )
        if result.status == "conflict":
            # Keep already-sent ledger receipts intact, but stop the outbox even
            # when another part still has a retryable failure.
            experience.announcement_status = "needs_attention"
        if not result.sent:
            return False
    targets = set(experience.broadcast_targets or [])
    if experience.broadcast_enabled and targets.intersection({"bot", "all", "bot_and_chat"}):
        # An explicit wizard choice is the only way to request personal delivery.
        recipients = await session.scalars(select(User.telegram_id).where(
            User.application_status == ApplicationStatus.APPROVED,
            User.is_blocked.is_(False), User.is_archived.is_(False),
        ))
        summary = f"{event.title}\n\n{experience.short_description or event.description}"
        outcome = await broadcast_detailed_once(
            bot, settings, [int(value) for value in recipients.all() if value], summary[:3500],
            reply_markup=markup, delivery_key=f"event:{event.id}:published",
            notification_type="event_published",
        )
        if outcome.failed:
            # The general-topic receipt can be successful while some personal
            # deliveries failed or have an uncertain outcome. Do not claim that
            # the entire announcement was sent, or automatically replay it.
            experience.announcement_status = "needs_attention"
            logger.warning(
                "Event announcement requires personal delivery reconciliation event_id=%s failed=%s",
                event.id, outcome.failed,
            )
            return False
    return True


async def record_announcement_status(session, event_id: int, delivered: bool) -> None:
    experience = await session.scalar(select(EventExperience).where(
        EventExperience.event_id == event_id,
    ).with_for_update().execution_options(populate_existing=True))
    if experience.announcement_status in {"sent", "needs_attention"}:
        return
    if delivered:
        experience.announcement_status = "sent"
    else:
        rows = list((await session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.delivery_key.like(f"general-topic:announcements:event:{event_id}:published%"),
        ))).all())
        attention = any(row.status in {"uncertain", "blocked", "unreachable", "conflict"}
                        or row.error_code == "telegram_bad_request" for row in rows)
        # A rejected call with only sent rows indicates a changed payload/key
        # conflict. Do not keep retrying it or create a replacement message.
        attention = attention or (bool(rows) and all(row.status == "sent" for row in rows))
        experience.announcement_status = "needs_attention" if attention else "pending"


async def deliver_event_announcement(bot, settings, session_factory, event_id) -> None:
    """One short-lived session per event; independent API/background ownership."""
    async with session_factory() as session:
        try:
            experience = await session.scalar(select(EventExperience).where(
                EventExperience.event_id == event_id,
                EventExperience.announcement_status == "pending",
            ).with_for_update(skip_locked=True))
            if experience is None:
                return
            event = await session.get(Event, event_id)
            if event is None or event.status not in PUBLIC_STATUSES:
                return
            delivered = await publish_event_announcement(bot, settings, session, event, experience)
            await record_announcement_status(session, event_id, delivered)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Event announcement retry failed event_id=%s", event_id)


async def _pending_announcement_ids(session_factory) -> list[int]:
    """Persist a bounded round-robin page before starting any Telegram work.

    Failed first-page events must not hide newer pending announcements forever.
    Advancing before delivery also permits progress after a worker interruption;
    pending rows wrap around on later runs, with existing delivery receipts intact.
    """
    async with session_factory() as session:
        if session.bind.dialect.name == "postgresql":
            lock_id = int.from_bytes(hashlib.sha256(RECOVERY_CURSOR_KEY.encode()).digest()[:8], "big", signed=True)
            await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        cursor_row = await session.scalar(select(AppSetting).where(AppSetting.key == RECOVERY_CURSOR_KEY))
        try:
            cursor = max(0, int(cursor_row.value)) if cursor_row else 0
        except (TypeError, ValueError):
            cursor = 0
        pending = select(EventExperience.event_id).join(
            Event, Event.id == EventExperience.event_id,
        ).where(EventExperience.announcement_status == "pending", Event.status.in_(PUBLIC_STATUSES))
        pending = pending.order_by(EventExperience.event_id)
        ids = list((await session.scalars(pending.where(
            EventExperience.event_id > cursor,
        ).limit(RECOVERY_BATCH_SIZE))).all())
        if len(ids) < RECOVERY_BATCH_SIZE:
            ids.extend((await session.scalars(pending.where(
                EventExperience.event_id <= cursor,
            ).limit(RECOVERY_BATCH_SIZE - len(ids)))).all())
        if ids:
            if cursor_row is None:
                session.add(AppSetting(key=RECOVERY_CURSOR_KEY, value=str(ids[-1])))
            else:
                cursor_row.value = str(ids[-1])
        await session.commit()
        return ids


async def deliver_pending_event_announcements(bot, settings, session_factory) -> None:
    ids = await _pending_announcement_ids(session_factory)
    semaphore = asyncio.Semaphore(4)

    async def deliver(event_id):
        async with semaphore:
            await deliver_event_announcement(bot, settings, session_factory, event_id)

    await asyncio.gather(*(deliver(event_id) for event_id in ids))
