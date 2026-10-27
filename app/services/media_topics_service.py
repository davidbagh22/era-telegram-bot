"""Durable Media forum setup. Unknown create outcomes require explicit binding."""
from __future__ import annotations

import hashlib
import json
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.models import AppSetting
from app.services.notification_service import safe_send_once

logger = logging.getLogger(__name__)
TOPICS = {
    "important": "📢 Важное", "tasks": "🎯 Задания", "ideas": "💡 Идеи",
    "shooting": "🎬 Съёмки", "materials": "📁 Материалы",
    "knowledge": "📚 База знаний", "opportunities": "🚀 Возможности", "chat": "💬 Общение",
}


def registry_key(chat_id, key):
    if key not in TOPICS:
        raise ValueError("unknown_media_topic")
    return f"media_forum:{chat_id}:{key}"


async def _lock(session, chat_id):
    if session.bind.dialect.name == "postgresql":
        lock_id = int.from_bytes(hashlib.sha256(f"media_forum:{chat_id}".encode()).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


async def read_topics(session, chat_id):
    rows = (await session.scalars(select(AppSetting).where(
        AppSetting.key.in_([registry_key(chat_id, key) for key in TOPICS]),
    ))).all()
    result = {}
    for row in rows:
        try:
            value = row.value if isinstance(row.value, dict) else json.loads(row.value)
            if not isinstance(value, dict):
                raise ValueError("invalid_topic")
            result[row.key.rsplit(":", 1)[1]] = value
        except (ValueError, TypeError):
            result[row.key.rsplit(":", 1)[1]] = {"state": "needs_attention"}
    return result


def topic_id(value):
    value = value.get("thread_id")
    return value if type(value) is int and value > 0 else None


async def delivery_topic(session, chat_id, key):
    topics = await read_topics(session, chat_id)
    value = topics.get(key, {})
    thread_id = topic_id(value)
    if value.get("state") != "ready" or not thread_id:
        return None
    if any(other != key and topic_id(item) == thread_id for other, item in topics.items()):
        return None
    return thread_id


async def topic_links(session, chat_id):
    if not chat_id or not str(chat_id).startswith("-100"):
        return []
    topics = await read_topics(session, chat_id)
    result = []
    for key, name in TOPICS.items():
        value = topics.get(key, {})
        thread_id = topic_id(value)
        if value.get("state") != "ready" or not thread_id:
            continue
        if any(other != key and topic_id(item) == thread_id for other, item in topics.items()):
            continue
        result.append({"key": key, "title": name, "url": f"https://t.me/c/{str(chat_id)[4:]}/{thread_id}"})
    return result


async def bind_topic(session, chat_id, key, thread_id):
    """Explicit admin repair/reuse; never guess IDs from topic titles."""
    setting_key = registry_key(chat_id, key)
    if type(thread_id) is not int or thread_id <= 0:
        raise ValueError("invalid_thread")
    await _lock(session, chat_id)
    topics = await read_topics(session, chat_id)
    if any(other != key and topic_id(value) == thread_id for other, value in topics.items()):
        raise ValueError("duplicate_thread")
    row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    value = json.dumps({"thread_id": thread_id, "state": "ready"})
    if row is None:
        session.add(AppSetting(key=setting_key, value=value))
    else:
        row.value = value
    await session.commit()


async def _ensure_topic(bot, factory, chat_id, key):
    setting_key = registry_key(chat_id, key)
    async with factory() as session:
        await _lock(session, chat_id)
        row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
        if row is not None:
            # Even a crash between Telegram and acknowledgement must not create
            # a second topic. Administrator can bind the original ID explicitly.
            return
        session.add(AppSetting(key=setting_key, value=json.dumps({"state": "creating"})))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return
    try:
        topic = await bot.create_forum_topic(chat_id, name=TOPICS[key])
        thread_id = topic.message_thread_id
        if type(thread_id) is not int or thread_id <= 0:
            raise ValueError("missing_thread_confirmation")
    except (TelegramRetryAfter, TelegramBadRequest):
        # Telegram explicitly rejected creation: retry is safe next cycle.
        async with factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
            if row:
                await session.delete(row)
                await session.commit()
        return
    except Exception:
        logger.exception("Media topic creation needs binding key=%s", key)
        return
    async with factory() as session:
        await bind_topic(session, chat_id, key, thread_id)


async def setup_media_topics(bot, settings, session_factory):
    chat_id = settings.media_chat_id
    if not chat_id or chat_id in {settings.general_chat_id, settings.leaders_chat_id}:
        logger.warning("Media forum unavailable: chat_not_configured")
        return {"status": "chat_not_configured"}
    try:
        chat = await bot.get_chat(chat_id)
        member = await bot.get_chat_member(chat_id, bot.id)
        if not chat.is_forum:
            logger.warning("Media forum unavailable: forum_disabled")
            return {"status": "forum_disabled"}
        if member.status != "creator" and not (
            member.status == "administrator" and member.can_manage_topics and member.can_pin_messages
        ):
            logger.warning("Media forum unavailable: missing_topic_or_pin_permissions")
            return {"status": "missing_topic_or_pin_permissions"}
        for key in TOPICS:
            await _ensure_topic(bot, session_factory, chat_id, key)
        async with session_factory() as session:
            topics = await read_topics(session, chat_id)
        ids = [topic_id(topics.get(key, {})) for key in TOPICS]
        # A persisted thread_id alone is not proof that Telegram creation was
        # acknowledged. Never publish navigation or report readiness while a
        # route remains in creating/needs_attention state.
        if (not all(topics.get(key, {}).get("state") == "ready" for key in TOPICS)
                or not all(ids) or len(set(ids)) != len(TOPICS)):
            logger.warning("Media forum setup needs attention: incomplete_or_conflicting_registry")
            return {"status": "needs_attention", "topics": topics}
        for thread_id in ids:
            try:
                await bot.reopen_forum_topic(chat_id, thread_id)
            except TelegramBadRequest as exc:
                if "TOPIC_NOT_MODIFIED" not in str(exc).upper():
                    return {"status": "needs_attention", "topics": topics}
        lines = ["Медиа ЭРА · навигация", "", "Выберите раздел:"]
        for (key, name), thread_id in zip(TOPICS.items(), ids):
            lines.append(f"{name} — https://t.me/c/{str(chat_id)[4:]}/{thread_id}")
        result = await safe_send_once(
            bot, settings, chat_id, "\n".join(lines),
            delivery_key=f"media-forum:{chat_id}:navigation:v1",
            notification_type="media_navigation", parse_mode=None,
            message_thread_id=ids[0],
        )
        if result.sent and result.message_id:
            await bot.pin_chat_message(chat_id, result.message_id, disable_notification=True)
            logger.info("Media forum ready: topics=8 navigation_message_id=%s", result.message_id)
        return {"status": "ready" if result.sent and result.message_id else "navigation_unconfirmed", "topics": topics}
    except Exception:
        logger.exception("Media forum setup failed")
        return {"status": "telegram_unavailable"}
