from __future__ import annotations

import json

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, ChatGreeting, User
from app.utils.constants import Role

router = Router(name="chat_binding")

CHAT_KEYS = {
    "general": ("general_chat_id", "general", "Общий чат"),
    "internal": ("internal_department_chat_id", "internal", "Внутренние связи"),
    "external": ("external_department_chat_id", "external", "Внешние связи"),
    "leaders": ("leaders_chat_id", "leaders", "Чат лидеров"),
    "media": ("media_chat_id", "media", "Медиа"),
    "channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
    "era_channel": ("era_channel_id", "era_channel", "Канал ЭРА"),
}


def _can_bind(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)
    )


def _binding_conflict(key: str, chat_id: int, settings: Settings) -> str | None:
    """Never reuse the general chat as the Leaders workcenter, or vice versa."""
    if key == "leaders" and chat_id == settings.general_chat_id:
        return "Это общий чат ЭРА. Чат лидеров должен быть отдельным."
    if key == "general" and chat_id == settings.leaders_chat_id:
        return "Это чат лидеров. Нельзя назначить его общим чатом ЭРА."
    return None


def _leaders_permission_error(chat, member) -> str | None:
    """Read-only Telegram preflight before persisting a Leaders chat binding."""
    if chat.type not in {"group", "supergroup"}:
        return "Чат лидеров должен быть группой или супергруппой Telegram."
    if member.status not in {"administrator", "creator"}:
        return "Сделайте бота администратором чата лидеров и повторите /bind leaders."
    if chat.is_forum and not getattr(member, "can_manage_topics", False):
        return "Для форума лидеров дайте боту право управлять темами и повторите /bind leaders."
    return None


@router.message(Command("bind"), ~F.chat.type.in_({"private"}))
async def bind_current_chat(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not message.from_user or not _can_bind(user, settings, message.from_user.id):
        await message.reply("Привязать чат может только администратор ЭРА")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip().lower() not in CHAT_KEYS:
        await message.reply(
            "Напишите так: /bind general\n\n"
            "Варианты: general, internal, external, leaders, media, channel"
        )
        return

    raw_key = parts[1].strip().lower()
    setting_key, greeting_key, title = CHAT_KEYS[raw_key]

    conflict = _binding_conflict(raw_key, message.chat.id, settings)
    if conflict:
        await message.reply(conflict)
        return
    if raw_key == "leaders":
        try:
            chat = await bot.get_chat(message.chat.id)
            member = await bot.get_chat_member(message.chat.id, bot.id)
        except TelegramAPIError:
            await message.reply("Не удалось проверить права бота в чате лидеров. Повторите привязку позже.")
            return
        permission_error = _leaders_permission_error(chat, member)
        if permission_error:
            await message.reply(permission_error)
            return

    stored = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    if stored is None:
        stored = AppSetting(
            key=setting_key,
            value=str(message.chat.id),
            updated_by=user.id if user else None,
        )
        session.add(stored)
    else:
        stored.value = str(message.chat.id)
        stored.updated_by = user.id if user else None

    greeting = await session.scalar(
        select(ChatGreeting).where(ChatGreeting.chat_key == greeting_key)
    )
    if greeting is not None:
        greeting.chat_id = message.chat.id
        greeting.updated_by = user.id if user else None

    await session.commit()
    setattr(settings, setting_key, message.chat.id)
    await message.reply(
        f"✅ {title} привязан. Настройка сохранена в ЭРА и применяется без перезапуска."
    )


@router.message(Command("leaders_diag"), F.chat.type == "private")
async def leaders_readonly_diagnostics(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Admin-only, read-only view of the Leaders binding and saved forum IDs.

    Telegram does not provide a reliable list-forum-topics endpoint, so a
    persisted thread ID must never be presented as a live-verified topic.
    This command never creates topics, sends to the group, or changes settings.
    """
    if not message.from_user or not _can_bind(user, settings, message.from_user.id):
        await message.answer("Диагностика чата лидеров доступна только администратору ЭРА.")
        return

    chat_id = settings.leaders_chat_id
    if not chat_id or chat_id == settings.general_chat_id:
        await message.answer("Чат лидеров не привязан отдельно от общего чата. Используйте /bind leaders в нужной группе.")
        return

    lines = ["Чат лидеров · диагностика (только чтение)", f"chat_id: {chat_id}"]
    live_forum: bool | None = None
    try:
        chat = await bot.get_chat(chat_id)
        member = await bot.get_chat_member(chat_id, bot.id)
    except TelegramAPIError as exc:
        lines.append(f"Telegram: не удалось проверить ({type(exc).__name__}).")
        lines.append("Сохранённые ID ниже не подтверждают существование тем.")
    else:
        forum = bool(getattr(chat, "is_forum", False))
        live_forum = forum
        lines.append(f"Тип: {getattr(chat, 'type', 'неизвестно')}")
        lines.append(f"Форум: {'да' if forum else 'нет'}")
        lines.append(f"Бот администратор: {'да' if member.status in {'administrator', 'creator'} else 'нет'}")
        if forum:
            lines.append(f"Управление темами: {'да' if getattr(member, 'can_manage_topics', False) else 'нет'}")
        # Pinning is optional for initial delivery, but without this right
        # the Tasks/Pulse/Important panels cannot be pinned for the team.
        can_pin = member.status == "creator" or bool(getattr(member, "can_pin_messages", False))
        lines.append(f"Закрепление сообщений: {'да' if can_pin else 'нет'}")
        lines.append("Telegram API не подтверждает существование темы по сохранённому ID.")

    for key, label in (("tasks", "Задачи"), ("pulse", "Пульс"), ("important", "Важно")):
        row = await session.scalar(
            select(AppSetting).where(AppSetting.key == f"leaders_forum:{chat_id}:{key}")
        )
        try:
            data = json.loads(row.value) if row and isinstance(row.value, str) else (row.value if row else {})
            if not isinstance(data, dict):
                data = {}
        except (ValueError, TypeError):
            data = {}
        thread_id = data.get("thread_id")
        state = data.get("thread_state")
        # A saved numeric ID alone is not evidence of a ready topic.
        # Prioritize uncertain/damaged durable states in read-only diagnostics.
        if state not in (None, "ready"):
            status = "создание не подтверждено; нужна ручная сверка, не создавать повторно"
        elif data.get("mode") not in (None, "forum", "plain"):
            status = "режим темы повреждён; нужна ручная сверка, не создавать повторно"
        elif live_forum is True and data.get("mode") == "plain":
            status = "Telegram: форум, но сохранён режим обычной группы; нужна ручная сверка"
        elif live_forum is False and (
            data.get("mode") == "forum" or (type(thread_id) is int and thread_id > 0)
        ):
            status = "Telegram: обычная группа, но сохранён ID темы/режим форума; нужна ручная сверка"
        elif data.get("mode") == "plain":
            if thread_id is not None:
                status = "настройки обычной группы противоречат друг другу; нужна ручная сверка"
            elif key != "tasks" and (
                data.get("message_id") is not None
                or data.get("message_state") is not None
            ):
                # Plain Pulse/Important have no panel receipts. The delivery
                # router rejects these conflicting settings; diagnostics must
                # not report a route as ready when actual delivery is blocked.
                status = "настройки обычной группы содержат чужую квитанцию панели; нужна ручная сверка"
            elif key == "tasks" and (
                type(data.get("message_id")) is not int
                or data["message_id"] <= 0
                or data.get("message_state") != "sent"
            ):
                status = "панель задач не подтверждена; нужна ручная сверка, не отправлять повторно"
            elif live_forum is None:
                # A saved plain-mode setting is not proof that Telegram still
                # considers this chat an ordinary group. Network failures must
                # not make diagnostics present the routing mode as verified.
                status = "режим обычной группы сохранён, но тип чата в Telegram не подтверждён; нужна ручная сверка"
            else:
                status = "обычная группа, отдельной темы нет"
        elif type(thread_id) is int and thread_id > 0:
            status = f"thread_id={thread_id} (из БД, не проверен в Telegram)"
        elif row is not None:
            status = "настройка темы повреждена; нужна ручная сверка, не создавать повторно"
        else:
            status = "тема не настроена"
        lines.append(f"{label}: {status}")
        # Corrupt JSON may contain lists/dicts instead of scalar receipt fields.
        # Diagnostics must remain read-only and never crash on those values.
        message_state = data.get("message_state")
        message_id = data.get("message_id")
        if key != "tasks" and data.get("mode") == "plain" and (
            message_id is not None or message_state is not None
        ):
            lines.append("  Карточка: чужая квитанция панели, доставка не подтверждена.")
        elif message_state in ("sending", "uncertain"):
            lines.append("  Карточка: доставка не подтверждена, требуется сверка.")
        elif (
            message_state not in (None, "sent")
            or (message_id is not None and (type(message_id) is not int or message_id <= 0))
        ):
            lines.append("  Карточка: данные квитанции повреждены; нужна ручная сверка.")
        elif type(message_id) is int and message_id > 0:
            lines.append(f"  Карточка message_id={message_id} (из БД).")

    # Read-only aggregate: helps distinguish Telegram delivery uncertainty from
    # successful sends without exposing task text or personal information.
    from app.database.models import TaskDelivery

    delivery_rows = await session.execute(
        select(TaskDelivery.status, func.count(TaskDelivery.id))
        .where(TaskDelivery.chat_key == "leaders", TaskDelivery.chat_id == chat_id)
        .group_by(TaskDelivery.status)
    )
    delivery_counts = dict(delivery_rows.all())
    if delivery_counts:
        lines.append(
            "Доставка задач: "
            f"отправлено {delivery_counts.get('sent', 0)} · "
            f"ожидает {delivery_counts.get('pending', 0)} · "
            f"требует сверки {delivery_counts.get('review_required', 0)} · "
            f"ошибки {delivery_counts.get('failed', 0)}"
        )
        if delivery_counts.get("review_required", 0):
            lines.append("Не повторяйте отправку до ручной сверки карточек в Telegram.")

    await message.answer("\n".join(lines))
