from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskDelivery, User
from app.utils.constants import TaskStatus
from app.utils.deep_links import miniapp_task_url

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
        "title": task.title,
        "assignee_id": task.assignee_id,
        "assignee_name": (
            f"{assignee.first_name} {assignee.last_name or ''}".strip() if assignee else None
        ),
        "deadline": task.deadline.isoformat() if task.deadline else None,
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
        mention = "Не назначен"
    deadline = task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "—"
    lines = [
        f"✅ <b>Задача ЭРА · #{task.id}</b>",
        "",
        f"<b>{escape(task.title)}</b>",
        "",
        f"Исполнитель: {mention}",
        f"Срок: {deadline}",
        f"Статус: {STATUS_LABELS.get(task.status, escape(str(task.status)))}",
    ]
    if task.comment:
        lines.extend(["", f"⚠️ Блокер: {escape(task.comment[:700])}"])
    return "\n".join(lines)


def task_card_keyboard(task: Task, settings: Settings) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if task.status in {TaskStatus.NEW, TaskStatus.PUBLISHED}:
        rows.append(
            [InlineKeyboardButton(text="Начать", callback_data=f"leaders_task:start:{task.id}")]
        )
    if task.status in {TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS}:
        rows.append(
            [
                InlineKeyboardButton(text="Сдать", callback_data=f"leaders_task:submit:{task.id}"),
                InlineKeyboardButton(text="Есть проблема", callback_data=f"leaders_task:block:{task.id}"),
            ]
        )
    if task.status == TaskStatus.REVIEW:
        rows.append(
            [
                InlineKeyboardButton(text="Принять", callback_data=f"leaders_task:accept:{task.id}"),
                InlineKeyboardButton(text="Вернуть", callback_data=f"leaders_task:return:{task.id}"),
            ]
        )
    url = miniapp_task_url(settings.effective_miniapp_url, task.id)
    if url:
        rows.append([InlineKeyboardButton(text="Открыть задачу в ЭРА", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def sync_leaders_task_cards(bot: Bot, settings: Settings, session_factory) -> None:
    """Retry one-card status/content sync from the Task source of truth."""
    async with session_factory() as session:
        deliveries = (
            await session.scalars(
                select(TaskDelivery).where(
                    TaskDelivery.chat_key == "leaders",
                    TaskDelivery.status == "sent",
                    TaskDelivery.telegram_message_id.is_not(None),
                )
            )
        ).all()
        for delivery in deliveries:
            task = await session.get(Task, delivery.task_id)
            if task is None:
                continue
            assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
            snapshot = card_snapshot(task, assignee)
            if (delivery.last_card_snapshot or {}) == snapshot:
                continue
            try:
                await bot.edit_message_text(
                    chat_id=delivery.chat_id,
                    message_id=delivery.telegram_message_id,
                    text=render_task_card(task, assignee),
                    reply_markup=task_card_keyboard(task, settings),
                    parse_mode="HTML",
                )
            except TelegramAPIError as exc:
                logger.warning("Leaders task card sync failed task=%s: %s", task.id, exc)
                delivery.error = str(exc)[:2000]
                continue
            delivery.last_card_snapshot = snapshot
            delivery.error = None
        await session.commit()
