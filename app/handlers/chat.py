from collections import defaultdict, deque
from time import monotonic

from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.chat_moderation import ChatModerationSetting
from app.database.models import ChatGreeting, User
from app.repositories.users import get_user_by_telegram_id
from app.services.audit_service import audit
from app.services.chat_access_service import (
    access_message,
    approve_join_request,
    chat_key_for_id,
    check_chat_access,
    close_join_request,
    decline_join_request,
    notify_user,
    remember_join_request,
    restrict_member,
    unrestrict_member,
)
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES

router = Router(name="chat")

_activity: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=8))
_personal_attacks = {"дурак", "идиот", "тупой", "тупая", "ненавижу тебя"}
_dm_notice_sent: dict[tuple[int, int], float] = {}
_DM_NOTICE_COOLDOWN = 300.0


def _private(message: Message) -> bool:
    return message.chat.type == "private"


async def _moderation_enabled(session: AsyncSession, chat_id: int) -> bool:
    setting = await session.scalar(select(ChatModerationSetting).where(ChatModerationSetting.chat_id == chat_id))
    return bool(setting and setting.is_enabled)


def _is_approved_member(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


@router.chat_join_request()
async def handle_chat_join_request(
    request: ChatJoinRequest,
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
) -> None:
    chat_key = chat_key_for_id(settings, request.chat.id)
    if chat_key is None:
        return
    user = await get_user_by_telegram_id(session, request.from_user.id)
    decision = check_chat_access(user, chat_key)
    if decision.allowed:
        if await approve_join_request(bot, request.chat.id, request.from_user.id):
            await close_join_request(
                session,
                chat_id=request.chat.id,
                user_id=request.from_user.id,
                status="approved",
                reason="approved",
            )
            await audit(
                session,
                actor_id=user.id if user else None,
                action="chat_access.join_request_approved",
                entity_type="chat_join_request",
                new_value={
                    "chat_id": request.chat.id,
                    "telegram_id": request.from_user.id,
                    "chat_key": chat_key,
                },
            )
        return

    if decision.chat_key and decision.pending:
        await remember_join_request(
            session,
            chat_id=request.chat.id,
            user_id=request.from_user.id,
            chat_key=decision.chat_key,
            reason=decision.reason,
        )
    elif decision.chat_key:
        await decline_join_request(bot, request.chat.id, request.from_user.id)
        await close_join_request(
            session,
            chat_id=request.chat.id,
            user_id=request.from_user.id,
            status="declined",
            reason=decision.reason,
        )
        await audit(
            session,
            actor_id=user.id if user else None,
            action="chat_access.join_request_declined",
            entity_type="chat_join_request",
            new_value={
                "chat_id": request.chat.id,
                "telegram_id": request.from_user.id,
                "chat_key": decision.chat_key,
                "reason": decision.reason,
            },
        )
    await notify_user(bot, request.from_user.id, access_message(decision.reason))


async def _soft_moderation(message: Message) -> None:
    if not message.from_user:
        return
    text = (message.text or "").casefold()
    if any(word in text for word in _personal_attacks):
        await message.reply(texts.MODERATION_PERSONAL)
        return
    key = (message.chat.id, message.from_user.id)
    now = monotonic()
    bucket = _activity[key]
    bucket.append(now)
    if len(bucket) >= 7 and now - bucket[0] < 20:
        bucket.clear()
        await message.reply(texts.MODERATION_FLOOD)


@router.message(Command("rules"), ~F.chat.type.in_({"private"}))
async def rules(message: Message) -> None:
    await message.answer(texts.CHAT_RULES)


@router.message(Command("links"), ~F.chat.type.in_({"private"}))
async def links(message: Message, bot: Bot, user: User | None, settings: Settings) -> None:
    me = await bot.get_me()
    include_leaders = bool(user and user.role in PRIVILEGED_ROLES)
    await message.answer(texts.links_text(settings, me.username or "era_bot", include_leaders))


@router.message(Command("departments"), ~F.chat.type.in_({"private"}))
async def departments(message: Message, settings: Settings) -> None:
    await message.answer(texts.departments_chat_text(settings))


@router.message(Command("events"), ~F.chat.type.in_({"private"}))
async def events_link(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятия", url=f"https://t.me/{me.username}?start=events")]])
    await message.answer("Откройте бот ЭРА и выберите раздел «Мероприятия».", reply_markup=keyboard)


@router.message(Command("project"), ~F.chat.type.in_({"private"}))
async def project_link(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Создать проект", url=f"https://t.me/{me.username}?start=project")]])
    await message.answer("Проектный конструктор доступен в боте ЭРА.", reply_markup=keyboard)


@router.message(Command("moderation_on"), ~F.chat.type.in_({"private"}))
async def moderation_on(message: Message, user: User | None, session: AsyncSession) -> None:
    if not user or user.role not in PRIVILEGED_ROLES or user.is_blocked or user.is_archived:
        await message.reply("Включить модерацию может только руководитель или администратор ЭРА.")
        return
    setting = await session.scalar(select(ChatModerationSetting).where(ChatModerationSetting.chat_id == message.chat.id))
    if setting is None:
        setting = ChatModerationSetting(chat_id=message.chat.id)
        session.add(setting)
    setting.is_enabled = True
    setting.enabled_by = user.id
    setting.enabled_at = message.date
    await session.flush()
    await message.reply("✅ Модерация включена для этого чата.\n\nТеперь писать смогут только одобренные участники ЭРА, руководители и администраторы.")


@router.message(Command("moderation_off"), ~F.chat.type.in_({"private"}))
async def moderation_off(message: Message, user: User | None, session: AsyncSession) -> None:
    if not user or user.role not in PRIVILEGED_ROLES or user.is_blocked or user.is_archived:
        await message.reply("Выключить модерацию может только руководитель или администратор ЭРА.")
        return
    setting = await session.scalar(select(ChatModerationSetting).where(ChatModerationSetting.chat_id == message.chat.id))
    if setting is not None and setting.is_enabled:
        setting.is_enabled = False
        await session.flush()
    await message.reply("Модерация выключена для этого чата.")


@router.message(Command("moderation_status"), ~F.chat.type.in_({"private"}))
async def moderation_status(message: Message, session: AsyncSession) -> None:
    enabled = await _moderation_enabled(session, message.chat.id)
    await message.reply("Модерация в этом чате: " + ("включена ✅" if enabled else "выключена"))


@router.message(F.new_chat_members)
async def welcome_members(message: Message, bot: Bot, settings: Settings, session: AsyncSession) -> None:
    me = await bot.get_me()
    welcomed = []
    chat_key = chat_key_for_id(settings, message.chat.id)
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        joined_user = await get_user_by_telegram_id(session, member.id)
        decision = check_chat_access(joined_user, chat_key)
        if not decision.allowed:
            restricted = await restrict_member(bot, message.chat.id, member.id)
            if not restricted:
                await message.answer("Не удалось автоматически ограничить доступ. Администратору чата нужно проверить права бота.")
            await notify_user(bot, member.id, access_message(decision.reason))
            continue
        if chat_key:
            await unrestrict_member(bot, message.chat.id, member.id)
        welcomed.append(member.first_name)
    if not welcomed:
        return
    if message.chat.id == settings.internal_department_chat_id:
        chat_key = "internal"
    elif message.chat.id == settings.external_department_chat_id:
        chat_key = "external"
    elif message.chat.id == settings.leaders_chat_id:
        chat_key = "leaders"
    else:
        chat_key = "general"
    greeting = await session.scalar(select(ChatGreeting).where(ChatGreeting.chat_key == chat_key))
    if greeting is not None and not greeting.is_enabled:
        return
    fallback = "Добро пожаловать в ЭРА.\n\nЗдесь общаются участники сообщества, появляются анонсы, проекты и возможности.\n\nРегистрация, баллы, портфолио и личный кабинет — в личном чате с ботом."
    body = greeting.text if greeting is not None else fallback
    body = body.replace("{name}", ", ".join(welcomed))
    await message.answer(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть бот", url=f"https://t.me/{me.username}?start=registration")]]))


@router.callback_query(F.data == "chat:rules")
async def rules_callback(call) -> None:
    await call.answer()
    await call.message.answer(texts.CHAT_RULES)


@router.message(~F.chat.type.in_({"private"}))
async def moderation_gate(message: Message, bot: Bot, user: User | None, settings: Settings, session: AsyncSession) -> None:
    chat_key = chat_key_for_id(settings, message.chat.id)
    decision = check_chat_access(user, chat_key)
    enabled = await _moderation_enabled(session, message.chat.id)
    allowed = decision.allowed if chat_key else (
        _is_approved_member(user)
        or bool(user and user.role in PRIVILEGED_ROLES and not user.is_blocked and not user.is_archived)
    )
    if (chat_key or enabled) and not allowed and message.from_user:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            allowed = member.status in {"administrator", "creator"}
        except TelegramAPIError:
            pass
    if (chat_key or enabled) and not allowed:
        if chat_key and message.from_user:
            await restrict_member(bot, message.chat.id, message.from_user.id)
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        if not message.from_user:
            return
        key = (message.chat.id, message.from_user.id)
        now = monotonic()
        last_sent = _dm_notice_sent.get(key, 0.0)
        if now - last_sent < _DM_NOTICE_COOLDOWN:
            return
        _dm_notice_sent[key] = now
        await notify_user(bot, message.from_user.id, access_message(decision.reason))
        return
    await _soft_moderation(message)


async def soft_moderation(message: Message) -> None:
    await _soft_moderation(message)
