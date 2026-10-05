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


async def panel(session, chat_id, key, username):
    from app.database.models import Task, TaskDelivery
    from app.services.leaders_workspace import meta, TERMINAL
    if key == "tasks":
        tasks = (await session.scalars(select(Task).join(TaskDelivery,TaskDelivery.task_id == Task.id).where(
            TaskDelivery.chat_key == "leaders",TaskDelivery.chat_id == chat_id))).unique().all()
        active=[t for t in tasks if t.status not in TERMINAL]
        text=(f"⚙️ РАБОЧИЙ ЦЕНТР ЭРА\n\nАктивных: {len(active)} · Свободных: {sum(t.assignee_id is None for t in active)}"
              f"\nНа проверке: {sum(t.status == 'review' for t in active)} · Блокеров: {sum(bool(meta(t).get('blocked')) for t in active)}")
        rows=[[('➕ Новая задача','wc:new'),('👤 Мои задачи','wc:list:mine')],
              [('📋 Активные','wc:list:active'),('🟢 Свободные','wc:list:free')],
              [('🔥 Срочные','wc:list:urgent'),('🚧 Блокеры','wc:list:block')]]
    elif key == "important":
        text="📢 ВАЖНЫЕ ОПОВЕЩЕНИЯ\nСообщения и решения для всей команды."
        rows=[[('📣 Оповестить всех','leaders_broadcast:new')]]
    else:
        return TOPICS[key][1], InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="Заполнить / подключить Пульс", url=f"https://t.me/{username}?start=pulse_connect")]]) if username else None
    return text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t,callback_data=d) for t,d in row] for row in rows])


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
                text, keyboard = await panel(session, chat_id, key, me.username)
                snapshot = {"text": text, "keyboard": keyboard.model_dump(mode="json") if keyboard else None}
                if not data.get("message_id"):
                    message = await bot.send_message(chat_id, text=text, message_thread_id=data["thread_id"], reply_markup=keyboard)
                    data["message_id"] = message.message_id
                    data["panel"] = snapshot
                    row.value = json.dumps(data)
                    await session.commit()
                elif data.get("panel") != snapshot:
                    try:
                        await bot.edit_message_text(chat_id=chat_id,message_id=data["message_id"],text=text,reply_markup=keyboard)
                    except Exception as exc:
                        if "message is not modified" not in str(exc).lower():
                            raise
                    data["panel"] = snapshot
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
