from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import Settings
from app.database.models import Task, TaskDelivery, User
from app.utils.constants import TaskStatus
from app.services.leaders_workspace import meta, deadline_label

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    TaskStatus.NEW: "⚪ Новая",
    TaskStatus.PUBLISHED: "⚪ Новая",
    TaskStatus.IN_PROGRESS: "🟡 В работе",
    TaskStatus.REVIEW: "🔵 На проверке",
    TaskStatus.COMPLETED: "🟢 Выполнено",
    TaskStatus.OVERDUE: "🔴 Просрочено",
    TaskStatus.CANCELLED: "⚫ Отменена",
}


def card_snapshot(task: Task, assignee: User | None) -> dict:
    return {
        "version": 2,
        "meta": meta(task),
        "title": task.title,
        "assignee_id": task.assignee_id,
        "assignee_name": (
            f"{assignee.first_name} {assignee.last_name or ''}".strip() if assignee else None
        ),
        "deadline": (task.deadline.isoformat() if task.deadline else "") if task.deadline else None,
        "status": str(task.status),
        "comment": task.comment,
    }


def render_task_card(task: Task, assignee: User | None) -> str:
    if assignee and assignee.username:
        mention = f"@{escape(assignee.username)}"
    elif assignee:
        name = escape(f"{assignee.first_name} {assignee.last_name or ''}".strip())
        mention = f'<a href="tg://user?id={assignee.telegram_id}">{name}</a>'
    else:
        mention = "Свободна"
    deadline = deadline_label(task.deadline)
    lines = [
        f"{'🔥' if meta(task).get('priority') == 'urgent' else '✅'} <b>Задача ЭРА · #{task.id}</b>",
        "",
        f"<b>{escape(task.title)}</b>",
        "",
        f"Исполнитель: {mention}",
        f"Срок: {deadline}",
        f"Статус: {'🚧 Есть проблема' if meta(task).get('blocked') else ('🔵 Предложена' if task.status in {TaskStatus.NEW,TaskStatus.PUBLISHED} and task.assignee_id and meta(task).get('accepted') is False else STATUS_LABELS.get(task.status, escape(str(task.status))))}",
    ]
    if task.comment:
        lines.extend(["", f"⚠️ Блокер: {escape(task.comment[:700])}"])
    return "\n".join(lines)


def task_card_keyboard(task: Task, settings: Settings) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Подробнее", callback_data=f"wc:details:{task.id}"),
             InlineKeyboardButton(text="Действия", callback_data=f"wc:actions:{task.id}")]]
    if task.assignee_id is None and task.status in {TaskStatus.NEW, TaskStatus.PUBLISHED}:
        rows.append([InlineKeyboardButton(text="Взять задачу", callback_data=f"wc:claim:{task.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def sync_one_card(session, bot, settings, task):
    delivery = await session.scalar(select(TaskDelivery).where(TaskDelivery.task_id == task.id,
        TaskDelivery.chat_key == "leaders", TaskDelivery.chat_id == settings.leaders_chat_id).with_for_update())
    if delivery is None:
        return
    # A previous Telegram send may have succeeded despite a lost response.
    # Review the original message instead of attempting a new send.
    if delivery.status == "review_required" and not delivery.telegram_message_id:
        return
    from app.services.leaders_topics_service import topic_id
    from datetime import datetime, timezone
    assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
    snapshot = card_snapshot(task, assignee)
    stored=delivery.last_card_snapshot or {}
    content=stored.get('content',stored)
    generation=stored.get('generation',0)
    if delivery.telegram_message_id and content == snapshot:
        return
    try:
        if delivery.telegram_message_id:
            await bot.edit_message_text(chat_id=delivery.chat_id, message_id=delivery.telegram_message_id,
                text=render_task_card(task,assignee),reply_markup=task_card_keyboard(task,settings),parse_mode="HTML")
        else:
            thread_id = await topic_id(session,delivery.chat_id,'tasks')
            if not thread_id:
                import json
                from app.database.models import AppSetting
                row=await session.scalar(select(AppSetting).where(AppSetting.key==f'leaders_forum:{delivery.chat_id}:tasks'))
                config=(json.loads(row.value) if isinstance(row.value,str) else row.value) if row else {}
                if config.get('mode')!='plain':
                    delivery.error='Раздел Задачи ещё не настроен'
                    return
            from app.services.notification_service import safe_send_once
            from aiogram.types import InlineKeyboardMarkup
            text=stored.get('initial_text') or render_task_card(task,assignee)
            markup=stored.get('initial_markup')
            keyboard=InlineKeyboardMarkup.model_validate(markup) if markup else task_card_keyboard(task,settings)
            delivery.last_card_snapshot={'content':content,'generation':generation,'initial_text':text,
                'initial_markup':keyboard.model_dump(mode='json'),
                'initial_snapshot':stored.get('initial_snapshot',snapshot)}
            await session.commit()
            sent=await safe_send_once(bot,settings,delivery.chat_id,text,
                delivery_key=f'leaders-card:{delivery.id}:{generation}',notification_type='leaders_task_card',
                message_thread_id=thread_id,reply_markup=keyboard,parse_mode='HTML')
            if not sent.sent:
                delivery.status='review_required' if sent.status in {'uncertain','conflict'} else 'pending'
                delivery.error=sent.error_code or sent.status
                return
            if not sent.message_id:
                delivery.status='review_required'
                delivery.error='missing_message_id'
                return
            snapshot=delivery.last_card_snapshot['initial_snapshot']
            delivery.telegram_message_id=sent.message_id
            delivery.message_thread_id=thread_id
            delivery.sent_at=datetime.now(timezone.utc)
        delivery.status="sent"
        delivery.last_card_snapshot={'content':snapshot,'generation':generation}
        delivery.error=None
    except TelegramAPIError as exc:
        if "message is not modified" in str(exc).lower():
            delivery.last_card_snapshot={'content':snapshot,'generation':generation}
            delivery.error=None
        else:
            delivery.error=str(exc)[:1000]
            if "message to edit not found" in str(exc).lower():
                delivery.telegram_message_id=None
                delivery.last_card_snapshot={'content':{},'generation':generation+1}
                delivery.status="pending"
            logger.warning("Leaders card sync failed task=%s: %s",task.id,exc)


async def sync_leaders_task_cards(bot: Bot, settings: Settings, session_factory) -> None:
    if not settings.leaders_chat_id:
        return
    async with session_factory() as session:
        tasks = (await session.scalars(select(Task).join(TaskDelivery,TaskDelivery.task_id == Task.id).where(
            TaskDelivery.chat_key=="leaders", TaskDelivery.chat_id==settings.leaders_chat_id))).unique().all()
        for task in tasks:
            await sync_one_card(session,bot,settings,task)
            await session.commit()
