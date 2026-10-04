"""Durable setup for the explicitly bound Leaders forum, never the general chat."""
from __future__ import annotations

import json
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.models import AppSetting

logger = logging.getLogger(__name__)
TOPICS = {
    "tasks": ("✅ Задачи", "Здесь фиксируем поручения и результаты. Ответьте /task на сообщение с поручением: бот спросит исполнителя и срок. Статус задачи связан с ЭРА."),
    "pulse": ("📊 Пульс", "Здесь собираем итоги недели. Ответы и личные напоминания доступны участникам чата ЛИДЕРЫ. В чате показываем общий прогресс; личные ответы доступны только автору и администрации."),
    "important": ("📢 Важно", "Здесь размещаем важные объявления и решения для команды. Обсуждения остаются в общей теме, поручения — в Задачах, итоги недели — в Пульсе."),
}


async def topic_id(session, chat_id: int, key: str) -> int | None:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == f"leaders_forum:{chat_id}:{key}"))
    return json.loads(row.value).get("thread_id") if row else None


async def setup_leaders_topics(bot, settings, session_factory) -> dict:
    chat_id = settings.leaders_chat_id
    if not chat_id or chat_id == settings.general_chat_id:
        return {"status": "not_configured"}
    async with session_factory() as session:
        try:
            chat = await bot.get_chat(chat_id)
            if not chat.is_forum:
                return {"status": "forum_disabled", "chat_id": chat_id}
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id, me.id)
            if not getattr(member, "can_manage_topics", False):
                return {"status": "missing_manage_topics", "chat_id": chat_id}
            result = {}
            for key, (name, description) in TOPICS.items():
                setting_key = f"leaders_forum:{chat_id}:{key}"
                row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
                data = json.loads(row.value) if row else {}
                if not data.get("thread_id"):
                    topic = await bot.create_forum_topic(chat_id, name=name)
                    data = {"thread_id": topic.message_thread_id}
                    if row is None:
                        row = AppSetting(key=setting_key, value=json.dumps(data))
                        session.add(row)
                    else:
                        row.value = json.dumps(data)
                    await session.commit()
                if not data.get("message_id"):
                    keyboard = None
                    if key == "pulse" and me.username:
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                            text="Подключить Пульс ЭРА", url=f"https://t.me/{me.username}?start=pulse_connect"
                        )]])
                    message = await bot.send_message(chat_id, text=description, message_thread_id=data["thread_id"], reply_markup=keyboard)
                    data["message_id"] = message.message_id
                    row.value = json.dumps(data)
                    await session.commit()
                if not data.get("pinned") and getattr(member, "can_pin_messages", False):
                    await bot.pin_chat_message(chat_id, data["message_id"], disable_notification=True)
                    data["pinned"] = True
                    row.value = json.dumps(data)
                    await session.commit()
                result[key] = data
            return {"status": "ready", "chat_id": chat_id, "topics": result}
        except Exception as exc:
            logger.warning("Leaders forum setup: %s", type(exc).__name__)
            return {"status": "error", "error": str(exc)[:500]}
