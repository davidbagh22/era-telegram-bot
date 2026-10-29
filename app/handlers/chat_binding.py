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


@router.message(Command("leaders_repair"), F.chat.type == "supergroup")
async def repair_leaders_panel(message: Message, user: User | None, settings: Settings,
                               session: AsyncSession, bot: Bot) -> None:
    from app.services.leaders_topics_service import (
        TOPICS, _topic_data, _has_duplicate_thread_route, _has_duplicate_panel_route, panel,
    )
    if (not message.from_user or message.chat.id != settings.leaders_chat_id
            or message.chat.id == settings.general_chat_id
            or not _can_bind(user, settings, message.from_user.id)):
        return
    parts = (message.text or '').split()
    key = parts[1] if len(parts) == 2 else ''
    source = message.reply_to_message
    if (key not in TOPICS or source is None or not source.from_user
            or source.from_user.id != bot.id or source.chat.id != message.chat.id):
        await message.reply('Ответьте /leaders_repair important на существующую панель этого бота в теме «Важно». Также доступны tasks и pulse.')
        return
    # Serialize repairs across workers; never authorize a different destination.
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy import text
        await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': message.chat.id})
    row = await session.scalar(select(AppSetting).where(
        AppSetting.key == f'leaders_forum:{message.chat.id}:{key}').with_for_update())
    data = _topic_data(row)
    thread = data.get('thread_id')
    if (row is None or data.get('mode') not in (None, 'forum')
            or data.get('thread_state') not in (None, 'ready')
            or type(thread) is not int or thread <= 0
            or message.message_thread_id != thread or source.message_thread_id != thread
            or type(source.message_id) is not int or source.message_id <= 0
            or await _has_duplicate_thread_route(session, message.chat.id, key, thread)
            or await _has_duplicate_panel_route(session, message.chat.id, key, source.message_id)):
        await message.reply('Тема не совпадает с сохранённым маршрутом или используется другим разделом. Настройки не изменены.')
        return
    me = await bot.get_me()
    content, keyboard = await panel(session, message.chat.id, key, me.username)
    try:
        await bot.edit_message_text(chat_id=message.chat.id, message_id=source.message_id,
            text=content, reply_markup=keyboard)
    except TelegramAPIError as exc:
        if 'message is not modified' not in str(exc).lower():
            await message.reply('Telegram не подтвердил панель. Настройки не изменены; повторная панель не отправлялась.')
            return
    row.value = json.dumps({**data, 'mode': 'forum', 'thread_state': 'ready',
        'message_id': source.message_id, 'message_state': 'sent',
        'panel': {'text': content, 'keyboard': keyboard.model_dump(mode='json') if keyboard else None}})
    await session.commit()
    await message.reply('Существующая панель подтверждена. Вернитесь к сохранённому черновику рассылки и выберите доставку заново.')

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
    preflight_issue: str | None = None
    try:
        chat = await bot.get_chat(chat_id)
        member = await bot.get_chat_member(chat_id, bot.id)
    except TelegramAPIError as exc:
        lines.append(f"Telegram: не удалось проверить ({type(exc).__name__}).")
        lines.append("Сохранённые ID ниже не подтверждают существование тем.")
    else:
        forum = bool(getattr(chat, "is_forum", False))
        live_forum = forum
        preflight_issue = _leaders_permission_error(chat, member)
        if preflight_issue:
            lines.append(f"Приёмка прав/типа чата: НЕ ПРОЙДЕНА — {preflight_issue}")
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

    # Read all three persisted routes before displaying any of them. A
    # single-pass check only warned about the *second* conflicting route,
    # incorrectly presenting the first route as usable to administrators.
    saved_routes = []
    thread_owners: dict[int, list[str]] = {}
    panel_owners: dict[int, list[str]] = {}
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
        saved_routes.append((key, label, row, data))
        if data.get("mode") in (None, "forum"):
            thread_id = data.get("thread_id")
            panel_id = data.get("message_id")
            if type(thread_id) is int and thread_id > 0:
                thread_owners.setdefault(thread_id, []).append(label)
            if type(panel_id) is int and panel_id > 0:
                panel_owners.setdefault(panel_id, []).append(label)

    for key, label, row, data in saved_routes:
        thread_id = data.get("thread_id")
        panel_id = data.get("message_id")
        # Every owner of a duplicate is unsafe, including the first one.
        # Ignore bool and malformed IDs to avoid false positives.
        is_forum_route = data.get("mode") in (None, "forum")
        duplicate_thread = next(
            (owner for owner in thread_owners.get(thread_id, []) if owner != label),
            None,
        ) if is_forum_route and type(thread_id) is int and thread_id > 0 else None
        duplicate_panel = next(
            (owner for owner in panel_owners.get(panel_id, []) if owner != label),
            None,
        ) if is_forum_route and type(panel_id) is int and panel_id > 0 else None
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
        # A saved route may look structurally valid while the bot has lost
        # its admin/topic rights or the bound chat is no longer a group.
        # Do not present such a route as ready during live diagnostics.
        if preflight_issue and (
            status == "обычная группа, отдельной темы нет"
            or status.startswith("thread_id=")
        ):
            status = "Telegram: проверка прав/типа чата не пройдена; доставка не подтверждена"
        conflicts = []
        if duplicate_thread:
            conflicts.append(f"thread_id={thread_id} совпадает с «{duplicate_thread}»")
        if duplicate_panel:
            conflicts.append(f"message_id={panel_id} совпадает с «{duplicate_panel}»")
        if conflicts:
            status = (
                "конфликт сохранённых маршрутов (" + "; ".join(conflicts)
                + "); доставка заблокирована, нужна ручная сверка"
            )
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
        elif row is not None and data.get("mode") in (None, "forum") and (
            message_id is None or message_state is None
        ):
            # setup_leaders_topics refuses to reuse a forum route without a
            # confirmed panel receipt. The read-only diagnostic must expose
            # the same uncertainty, not silently omit the panel line or show
            # an unconfirmed message ID as a delivered card.
            lines.append("  Карточка: подтверждённая панель темы отсутствует; нужна ручная сверка.")
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
