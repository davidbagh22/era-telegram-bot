"""Public announcements and broadcasts belong to durable general-chat topics."""
from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select, text as sql_text

from app.database.models import AppSetting
from app.services.notification_service import _session_factory, safe_send, safe_send_once

logger = logging.getLogger(__name__)
TOPICS = {"announcements": "Объявления", "notifications": "Оповещения"}


async def ensure_topic(bot, settings, key: str, *, session_factory=None) -> int | None:
    """Never fall back to the main thread when forum setup is unavailable.

    Separate transaction: creating a topic must not commit a caller's draft.
    PostgreSQL advisory lock serializes setup across API/scheduler workers.
    Existing IDs are reused; deleted topics require explicit administrator repair.
    """
    name = TOPICS[key]
    chat_id = settings.general_chat_id
    if not chat_id:
        return None
    factory = session_factory or _session_factory(settings.database_url)
    setting_key = f"general_forum:{chat_id}:{key}"
    try:
        async with factory() as session:
            if session.bind.dialect.name == "postgresql":
                lock_id = int.from_bytes(hashlib.sha256(setting_key.encode()).digest()[:8], "big", signed=True)
                await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
            data = json.loads(row.value) if row else {}
            if data.get("thread_id"):
                return int(data["thread_id"])
            chat = await bot.get_chat(chat_id)
            if not chat.is_forum:
                logger.warning("General topics unavailable: forum_disabled")
                return None
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id, me.id)
            if member.status != "creator" and not getattr(member, "can_manage_topics", False):
                logger.warning("General topics unavailable: missing_manage_topics")
                return None
            topic = await bot.create_forum_topic(chat_id, name=name)
            value = json.dumps({"thread_id": topic.message_thread_id})
            if row is None:
                session.add(AppSetting(key=setting_key, value=value))
            else:
                row.value = value
            await session.commit()
            return topic.message_thread_id
    except Exception:
        logger.exception("General topic setup failed key=%s", key)
        return None


async def setup_general_topics(bot, settings, session_factory) -> dict:
    result = {}
    for key in TOPICS:
        result[key] = await ensure_topic(bot, settings, key, session_factory=session_factory)
    return result


async def send_general_topic(bot, settings, key, text, *, reply_markup=None, delivery_key=None, parse_mode=None) -> bool:
    thread_id = await ensure_topic(bot, settings, key)
    if thread_id is None:
        return False
    if delivery_key:
        result = await safe_send_once(
            bot, settings, settings.general_chat_id, text,
            delivery_key=f"general-topic:{key}:{delivery_key}",
            notification_type=f"general_{key}", reply_markup=reply_markup,
            message_thread_id=thread_id, parse_mode=parse_mode,
        )
        return result.sent
    return await safe_send(bot, settings.general_chat_id, text,
                           reply_markup=reply_markup, message_thread_id=thread_id, parse_mode=parse_mode)
