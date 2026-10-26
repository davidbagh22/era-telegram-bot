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


def _topic_data(row) -> dict:
    """Treat damaged or unexpected stored settings as unconfigured, never as a thread."""
    if row is None:
        return {}
    try:
        data = json.loads(row.value) if isinstance(row.value, str) else row.value
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


async def topic_id(session, chat_id: int, key: str) -> int | None:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == f"leaders_forum:{chat_id}:{key}"))
    data = _topic_data(row)
    thread_id = data.get('thread_id')
    if (data.get('mode') not in (None, 'forum') or data.get('thread_state') not in (None, 'ready')
            or type(thread_id) is not int or thread_id <= 0):
        return None
    return thread_id


async def delivery_topic(session, chat_id, key):
    """Fail closed unless an explicit plain mode or a valid forum thread is saved."""
    row = await session.scalar(select(AppSetting).where(AppSetting.key == f'leaders_forum:{chat_id}:{key}'))
    data = _topic_data(row)
    mode = data.get('mode')
    if mode == 'plain':
        if data.get('thread_id') is not None:
            raise ValueError('Настройки чата лидеров противоречат друг другу. Проверьте темы.')
        return None
    # An unknown persisted mode is not proof that the saved thread belongs
    # to this forum. Never route a task into a potentially unrelated topic.
    if mode not in (None, 'forum'):
        raise ValueError('Режим темы лидеров повреждён. Требуется ручная сверка.')
    # A plausible thread ID is not proof of successful creation while a
    # durable creating/failed marker is present. Never route into it.
    if data.get('thread_state') not in (None, 'ready'):
        raise ValueError('Создание темы не подтверждено. Требуется ручная сверка.')
    thread_id = data.get('thread_id')
    if type(thread_id) is not int or thread_id <= 0:
        raise ValueError('Рабочая тема не настроена. Проверьте привязку чата лидеров.')
    return thread_id


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
              [('🔥 Срочные','wc:list:urgent'),('🚧 Блокеры','wc:list:block')],
              [('📢 Сообщение команде','lc:new')]]
    elif key == "important":
        text="📢 ВАЖНЫЕ ОПОВЕЩЕНИЯ\nСообщения и решения для всей команды."
        rows=[[('📣 Сообщение команде','lc:new')]]
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
            me = await bot.get_me()
            member = await bot.get_chat_member(chat_id, me.id)
            # A previously valid binding can lose its permissions or be changed
            # to a different Telegram chat type after /bind leaders.
            # Never create topics or send panels before revalidating the live chat.
            if chat.type not in {"group", "supergroup"}:
                return {"status": "invalid_chat_type", "chat_id": chat_id}
            if member.status not in {"administrator", "creator"}:
                return {"status": "missing_admin_rights", "chat_id": chat_id}
            if not chat.is_forum:
                existing=await session.scalar(select(AppSetting).where(AppSetting.key==f'leaders_forum:{chat_id}:tasks'))
                data = _topic_data(existing)
                if data.get('thread_id'):
                    return {'status':'forum_disabled','chat_id':chat_id}
                if existing is not None:
                    # A legacy, damaged or uncertain panel record may already
                    # correspond to a Telegram message. Never post a replacement
                    # into the group's main feed without manual reconciliation.
                    message_id = data.get('message_id')
                    if (
                        data.get('mode') != 'plain'
                        or data.get('thread_id') is not None
                        or type(message_id) is not int
                        or message_id <= 0
                        or data.get('message_state') != 'sent'
                    ):
                        return {'status':'panel_needs_review','chat_id':chat_id}
                text,keyboard=await panel(session,chat_id,'tasks',me.username)
                if not data.get('message_id'):
                    if existing is None:
                        existing=AppSetting(key=f'leaders_forum:{chat_id}:tasks',value='{}')
                        session.add(existing)
                    existing.value=json.dumps({'mode':'plain','thread_id':None,'message_state':'sending'})
                    await session.commit()
                    try:
                        sent=await bot.send_message(chat_id,text,reply_markup=keyboard)
                    except Exception:
                        existing.value=json.dumps({'mode':'plain','thread_id':None,'message_state':'uncertain'})
                        await session.commit()
                        raise
                    # Telegram may return a malformed message object even if a
                    # panel was published. Keep the durable sending marker and
                    # require reconciliation rather than retrying the send.
                    message_id = getattr(sent, 'message_id', None)
                    if type(message_id) is not int or message_id <= 0:
                        return {'status': 'panel_needs_review', 'chat_id': chat_id}
                    data={'mode':'plain','thread_id':None,'message_id':message_id,'message_state':'sent'}
                else:
                    try:
                        await bot.edit_message_text(chat_id=chat_id,message_id=data['message_id'],text=text,reply_markup=keyboard)
                    except Exception as exc:
                        if 'message is not modified' not in str(exc).lower(): raise
                existing.value=json.dumps(data)
                for key in ('important','pulse'):
                    row=await session.scalar(select(AppSetting).where(AppSetting.key==f'leaders_forum:{chat_id}:{key}'))
                    if row is None: session.add(AppSetting(key=f'leaders_forum:{chat_id}:{key}',value=json.dumps({'mode':'plain','thread_id':None})))
                await session.commit()
                if getattr(member,'can_pin_messages',False) and not data.get('pinned'):
                    await bot.pin_chat_message(chat_id,data['message_id'],disable_notification=True)
                    existing.value=json.dumps({**data,'pinned':True})
                    await session.commit()
                return {'status':'ready_plain','chat_id':chat_id}
            if not getattr(member, 'can_manage_topics', False):
                return {'status': 'missing_manage_topics', 'chat_id': chat_id}
            result = {}
            for key, (name, description) in TOPICS.items():
                setting_key = f"leaders_forum:{chat_id}:{key}"
                row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
                data = _topic_data(row)
                created_topic_now = row is None
                # A stored row may represent a topic created just before a
                # Telegram timeout. Never create a replacement automatically,
                # even if its JSON or thread ID is damaged.
                if row is not None:
                    thread_id = data.get("thread_id")
                    if (
                        data.get("mode") not in (None, "forum")
                        or data.get("thread_state") not in (None, "ready")
                        or type(thread_id) is not int
                        or thread_id <= 0
                    ):
                        return {"status": "topic_needs_review", "chat_id": chat_id, "topic": key}
                else:
                    row = AppSetting(key=setting_key, value=json.dumps({"thread_state": "creating"}))
                    session.add(row)
                    await session.commit()
                    topic = await bot.create_forum_topic(chat_id, name=name)
                    thread_id = getattr(topic, "message_thread_id", None)
                    if type(thread_id) is not int or thread_id <= 0:
                        # Keep the durable creating marker: the Telegram call
                        # may have created a real topic despite a bad response.
                        return {"status": "topic_needs_review", "chat_id": chat_id, "topic": key}
                    data = {"thread_id": thread_id}
                    row.value = json.dumps(data)
                    await session.commit()
                text, keyboard = await panel(session, chat_id, key, me.username)
                snapshot = {"text": text, "keyboard": keyboard.model_dump(mode="json") if keyboard else None}
                # A damaged saved panel ID or ambiguous delivery state must
                # never trigger a fresh send, edit, or pin. Telegram may already
                # contain the panel, so require an administrator to reconcile it.
                message_id = data.get('message_id')
                message_state = data.get('message_state')
                # A legacy row may already have a published panel even when
                # its message ID/state was never saved. Only a topic created
                # during this invocation can safely send its first panel.
                if not created_topic_now and message_id is None and message_state is None:
                    return {'status':'panel_needs_review','chat_id':chat_id,'topic':key}
                if (
                    (message_id is not None and (type(message_id) is not int or message_id <= 0))
                    or (message_state == 'sent' and message_id is None)
                    or message_state not in (None, 'sent')
                ):
                    return {'status':'panel_needs_review','chat_id':chat_id,'topic':key}
                if not data.get("message_id"):
                    data['message_state']='sending'
                    row.value=json.dumps(data)
                    await session.commit()
                    message = await bot.send_message(chat_id, text=text, message_thread_id=data["thread_id"], reply_markup=keyboard)
                    message_id = getattr(message, 'message_id', None)
                    if type(message_id) is not int or message_id <= 0:
                        # The send may have succeeded; never retry blindly.
                        return {'status': 'panel_needs_review', 'chat_id': chat_id, 'topic': key}
                    data["message_id"] = message_id
                    data["message_state"] = "sent"
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
