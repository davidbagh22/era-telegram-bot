"""Public announcements and broadcasts belong to durable general-chat topics."""
from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select, text as sql_text

from app.database.models import AppSetting
from app.services.notification_service import NotificationDeliveryResult, _session_factory, safe_send, safe_send_once

logger = logging.getLogger(__name__)
TOPICS = {"announcements": "Мероприятия", "notifications": "Оповещения", "literature": "Литература", "games": "🎮 Интерактив"}
SETUP_TOPICS = ("announcements", "notifications")  # Existing bootstrapping contract


async def ensure_topic(bot, settings, key: str, *, session_factory=None, create_if_missing: bool = True) -> int | None:
    """Reuse a durable forum route, failing closed after ambiguous creation.

    PostgreSQL advisory locking protects the claim; a committed creating
    row is persisted before the Telegram API call. If Telegram creates a
    topic but its reply or the acknowledgement commit is lost, a later worker
    must not create a duplicate. An administrator must reconcile the real ID.
    """
    name = TOPICS[key]
    chat_id = settings.general_chat_id
    if not chat_id:
        return None
    factory = session_factory or _session_factory(settings.database_url)
    setting_key = f"general_forum:{chat_id}:{key}"

    async def lock(session):
        if session.bind.dialect.name == "postgresql":
            lock_id = int.from_bytes(hashlib.sha256(setting_key.encode()).digest()[:8], "big", signed=True)
            await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})

    try:
        async with factory() as session:
            await lock(session)
            row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
            if row is not None:
                try:
                    data = json.loads(row.value) if isinstance(row.value, str) else row.value
                except (TypeError, ValueError):
                    data = None
                thread_id = data.get("thread_id") if isinstance(data, dict) else None
                # Keep legacy positive numeric strings readable, but never
                # coerce booleans/floats or a negative ID into a destination.
                if type(thread_id) is str:
                    try:
                        thread_id = int(thread_id)
                    except ValueError:
                        thread_id = None
                if type(thread_id) is int and thread_id > 0:
                    return thread_id
                logger.warning("General topic settings need reconciliation key=%s", key)
                return None
            if not create_if_missing:
                return None
            if key == "announcements":
                logger.warning("Existing events topic is not configured; refusing to create a replacement")
                return None
            chat = await bot.get_chat(chat_id)
            if not chat.is_forum:
                logger.warning("General topics unavailable: forum_disabled")
                return None
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id, me.id)
            if member.status != "creator" and not getattr(member, "can_manage_topics", False):
                logger.warning("General topics unavailable: missing_manage_topics")
                return None

            # The claim is committed before any non-transactional Telegram I/O.
            # A lost API response must not cause the next scheduler to recreate.
            session.add(AppSetting(key=setting_key, value=json.dumps({"state": "creating"})))
            await session.commit()

        try:
            topic = await bot.create_forum_topic(chat_id, name=name)
            thread_id = topic.message_thread_id
            if type(thread_id) is not int or thread_id <= 0:
                raise ValueError("missing_thread_confirmation")
        except Exception:
            # Even an explicit rejection is kept for manual reconciliation:
            # no automatic retry may duplicate a remotely created topic.
            logger.exception("General topic creation outcome needs reconciliation key=%s", key)
            return None

        async with factory() as session:
            await lock(session)
            row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
            if row is None:
                logger.warning("General topic claim disappeared after creation key=%s", key)
                return None
            try:
                current = json.loads(row.value) if isinstance(row.value, str) else row.value
            except (TypeError, ValueError):
                current = None
            if current != {"state": "creating"}:
                logger.warning("General topic claim changed after creation key=%s", key)
                return None
            row.value = json.dumps({"thread_id": thread_id, "name": name})
            await session.commit()
            return thread_id
    except Exception:
        logger.exception("General topic setup failed key=%s", key)
        return None

async def setup_general_topics(bot, settings, session_factory) -> dict:
    result = {}
    for key in SETUP_TOPICS:
        result[key] = await ensure_topic(bot, settings, key, session_factory=session_factory)
    return result


async def send_general_topic_once(bot, settings, key, text, *, delivery_key, reply_markup=None, parse_mode=None, photo=None, max_attempts=3) -> NotificationDeliveryResult:
    """Expose the durable outcome so callers can stop on payload conflicts."""
    thread_id = await ensure_topic(bot, settings, key)
    if thread_id is None:
        return NotificationDeliveryResult(False, "failed", False, 0, "topic_unavailable")
    media_kwargs = {"photo": photo} if photo is not None else {}
    return await safe_send_once(
        bot, settings, settings.general_chat_id, text,
        delivery_key=f"general-topic:{key}:{delivery_key}",
        notification_type=f"general_{key}", reply_markup=reply_markup,
        message_thread_id=thread_id, parse_mode=parse_mode,
        max_attempts=max_attempts,
        **media_kwargs,
    )


async def send_general_topic(bot, settings, key, text, *, reply_markup=None, delivery_key=None, parse_mode=None, photo=None) -> bool:
    if delivery_key:
        result = await send_general_topic_once(
            bot, settings, key, text, delivery_key=delivery_key,
            reply_markup=reply_markup, parse_mode=parse_mode, photo=photo,
        )
        return result.sent or (result.duplicate and result.status == 'sent')
    if photo is not None:
        raise ValueError("Public media requires a durable delivery_key")
    thread_id = await ensure_topic(bot, settings, key)
    if thread_id is None:
        return False
    return await safe_send(bot, settings.general_chat_id, text,
                           reply_markup=reply_markup, message_thread_id=thread_id, parse_mode=parse_mode)
