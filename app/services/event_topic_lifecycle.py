"""Scheduled closing and manual reopening of bot-owned event forum topics.

No broad chat operations. We ONLY target the topic ID that our bot previously
saved in event-forum:{chat_id}:{event_id}.  Closing never deletes messages.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event
from app.services.audit_service import audit

logger = logging.getLogger(__name__)
YEREVAN = ZoneInfo("Asia/Yerevan")


class TopicActionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def utc_aware(value: datetime) -> datetime:
    """Unzoned admin input is explicitly interpreted in Yerevan."""
    return (value.replace(tzinfo=YEREVAN) if value.tzinfo is None else value).astimezone(timezone.utc)


async def _managed_thread(session, settings, event_id: int) -> int:
    chat_id = getattr(settings, "general_chat_id", None)
    if not isinstance(chat_id, int) or chat_id >= 0:
        raise TopicActionError("event_forum_not_configured")
    record = await session.scalar(select(AppSetting).where(
        AppSetting.key == f"event-forum:{chat_id}:{event_id}"
    ))
    value = record.value if record is not None else None
    thread = value.get("thread") if isinstance(value, dict) else None
    if type(thread) is not int or thread <= 1:
        raise TopicActionError("event_topic_not_owned")
    return thread


async def update_topic_status(bot, settings, session, event_id: int, action: str, *, actor_id: int | None = None):
    """Serialize manual and automatic actions by the experience row lock."""
    if action not in {"close", "reopen"}:
        raise ValueError("unsupported_topic_action")
    event = await session.get(Event, event_id)
    if event is None:
        raise TopicActionError("event_not_found")
    exp = await session.scalar(select(EventExperience).where(
        EventExperience.event_id == event_id
    ).with_for_update())
    if exp is None:
        raise TopicActionError("event_topic_not_configured")
    if action == "close" and exp.topic_close_state == "closed":
        return exp
    if action == "reopen" and exp.topic_close_state == "open":
        return exp
    thread = await _managed_thread(session, settings, event_id)
    if bot is None:
        raise TopicActionError("bot_unavailable")
    try:
        if action == "close":
            await bot.close_forum_topic(chat_id=settings.general_chat_id, message_thread_id=thread)
        else:
            await bot.reopen_forum_topic(chat_id=settings.general_chat_id, message_thread_id=thread)
    except TelegramBadRequest as exc:
        msg = str(exc).lower()
        expected = ("already closed", "topic is closed", "topic_closed", "topic_not_modified", "topic not modified") if action == "close" else (
            "already open", "not closed", "topic_not_modified"
        )
        if not any(needle in msg for needle in expected):
            raise TopicActionError("telegram_topic_action_failed") from exc
    except Exception as exc:
        raise TopicActionError("telegram_topic_action_failed") from exc

    exp.topic_close_state = "closed" if action == "close" else "open"
    exp.topic_closed_at = datetime.now(timezone.utc) if action == "close" else None
    if action == "reopen":
        # A past auto-close time must not immediately close a reopened topic.
        exp.topic_close_at = None
    if actor_id is not None:
        await audit(session, actor_id=actor_id, action=f"event.topic_{action}",
                    entity_type="event", entity_id=event_id,
                    new_value={"topic_id": thread, "action": action})
    await session.commit()
    logger.info("Event Telegram topic %s: event_id=%s thread=%s", action, event_id, thread)
    return exp


async def close_due_event_topics(bot, settings, session_factory) -> None:
    """One-minute recovery job: lock records; never close arbitrary forum topics."""
    if bot is None or not getattr(settings, "general_chat_id", None):
        return
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        ids = (await session.scalars(select(EventExperience.event_id).where(
            EventExperience.topic_close_at.is_not(None),
            EventExperience.topic_close_at <= now,
            EventExperience.topic_close_state == "open",
        ).order_by(EventExperience.topic_close_at).limit(50))).all()
    for event_id in ids:
        async with session_factory() as session:
            try:
                # Locking serializes scheduler calls and admin schedule edits.
                exp = await session.scalar(select(EventExperience).where(
                    EventExperience.event_id == event_id
                ).with_for_update(skip_locked=True))
                if exp is None or exp.topic_close_state != "open" or not exp.topic_close_at:
                    continue
                if utc_aware(exp.topic_close_at) > datetime.now(timezone.utc):
                    continue
                await update_topic_status(bot, settings, session, event_id, "close")
            except TopicActionError as exc:
                await session.rollback()
                # Missing bot-owned topic means no safe target; do not invent IDs
                # or close the shared "Мероприятия" topic instead.
                logger.warning("Scheduled event topic closing not completed: event_id=%s reason=%s",
                               event_id, exc.code)
            except Exception:
                await session.rollback()
                logger.exception("Scheduled event topic closing failed: event_id=%s", event_id)
