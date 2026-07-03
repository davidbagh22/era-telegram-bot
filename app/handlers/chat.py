from collections import defaultdict, deque
from time import monotonic

from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import ChatGreeting, User
from app.repositories.users import get_user_by_telegram_id
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES

router = Router(name="chat")

_activity: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=8))
_personal_attacks = {"дурак", "идиот", "тупой", "тупая", "ненавижу тебя"}


def _private(message: Message) -> bool:
    return message.chat.type == "private"


@router.message(Command("rules"), ~F.chat.type.in_({"private"}))
async def rules(message: Message) -> None:
    await message.answer(texts.CHAT_RULES)


@router.message(Command("links"), ~F.chat.type.in_({"private"}))
async def links(
    message: Message, bot: Bot, user: User | None, settings: Settings
) -> None:
    me = await bot.get_me()
    include_leaders = bool(user and user.role in PRIVILEGED_ROLES)
    await message.answer(
        texts.links_text(settings, me.username or "era_bot", include_leaders)
    )


@router.message(Command("departments"), ~F.chat.type.in_({"private"}))
async def departments(message: Message, settings: Settings) -> None:
    await message.answer(texts.departments_chat_text(settings))


@router.message(Command("events"), ~F.chat.type.in_({"private"}))
async def events_link(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть мероприятия",
                    url=f"https://t.me/{me.username}?start=events",
                )
            ]
        ]
    )
    await message.answer(
        "Откройте бот ЭРА и выберите раздел «Мероприятия».", reply_markup=keyboard
    )


@router.message(Command("project"), ~F.chat.type.in_({"private"}))
async def project_link(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Создать проект",
                    url=f"https://t.me/{me.username}?start=project",
                )
            ]
        ]
    )
    await message.answer(
        "Проектный конструктор доступен в боте ЭРА.", reply_markup=keyboard
    )


@router.message(F.new_chat_members)
async def welcome_members(
    message: Message,
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
) -> None:
    me = await bot.get_me()
    welcomed = []
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        if message.chat.id == settings.leaders_chat_id:
            joined_user = await get_user_by_telegram_id(session, member.id)
            if not joined_user or joined_user.role not in PRIVILEGED_ROLES:
                try:
                    await bot.ban_chat_member(message.chat.id, member.id)
                    await bot.unban_chat_member(
                        message.chat.id,
                        member.id,
                        only_if_banned=True,
                    )
                except TelegramAPIError:
                    await message.answer(
                        "Не удалось автоматически ограничить доступ. Администратору чата нужно проверить права бота."
                    )
                continue
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

    greeting = await session.scalar(
        select(ChatGreeting).where(ChatGreeting.chat_key == chat_key)
    )
    if greeting is not None and not greeting.is_enabled:
        return

    fallback = (
        "Добро пожаловать в ЭРА.\n\n"
        "Здесь общаются участники сообщества, появляются анонсы, проекты и возможности.\n\n"
        "Регистрация, баллы, портфолио и личный кабинет — в личном чате с ботом."
    )
    body = greeting.text if greeting is not None else fallback
    body = body.replace("{name}", ", ".join(welcomed))
    await message.answer(
        body,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть бот",
                    url=f"https://t.me/{me.username}?start=registration",
                )
            ]]
        ),
    )

@router.callback_query(F.data == "chat:rules")
async def rules_callback(call) -> None:
    await call.answer()
    await call.message.answer(texts.CHAT_RULES)


@router.message(F.text, ~F.chat.type.in_({"private"}))
async def soft_moderation(message: Message) -> None:
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
