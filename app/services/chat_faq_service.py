"""Single pinned FAQ/navigation card for the general ERA chat."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AuditLog
from app.keyboards.faq import faq_keyboard
from app.services.audit_service import audit

FAQ_PINNED_MESSAGE = """🔥 <b>ЭРА — всё нужное в одном месте</b>

Не знаете, где найти мероприятие, посмотреть баллы или разобраться с заданиями?

Выберите нужный раздел — бот сразу откроет ответ лично для вас."""

FAQ_ANSWERS: dict[str, str] = {
    "faq:events": """📅 <b>Ближайшие события</b>

<b>Здесь начинается движение.</b>

Мы собрали ближайшие мероприятия ЭРА в одном месте.

Вы можете посмотреть программу, количество свободных мест и сразу зарегистрироваться.""",
    "faq:projects": """🚀 <b>Мои проекты</b>

<b>Ваши идеи и проекты — здесь.</b>

Откройте проекты, в которых вы участвуете, посмотрите команду, задачи и следующий шаг.""",
    "faq:tasks": """✅ <b>Мои задания</b>

<b>Здесь видно, что можно сделать прямо сейчас.</b>

Выполняйте задания, участвуйте в проектах и получайте баллы за реальный вклад.""",
    "faq:points": """⭐ <b>Баллы и возможности</b>

<b>Баллы показывают вашу активность. Но главное — что они открывают дальше.</b>

Участие, проекты и выполненные задания помогают двигаться от участника к активной роли и лидерству.""",
    "faq:registration": """🙋 <b>Как зарегистрироваться</b>

<b>Нашли мероприятие, куда хотите попасть?</b>

Откройте его и нажмите «Зарегистрироваться».

После регистрации бот отправит подтверждение и напомнит о событии заранее.

Если планы изменятся — участие можно отменить в один клик.""",
    "faq:active": """🔥 <b>Как стать активным</b>

<b>Не обязательно ждать приглашения.</b>

Выбирайте проекты, берите задания, помогайте командам и предлагайте собственные идеи.

В ЭРА рост начинается с действия.""",
    "faq:contact": """💬 <b>Связаться с командой</b>

<b>Есть вопрос или идея?</b>

Напишите команде ЭРА — сообщение попадёт ответственному человеку.""",
    # Backward-compatible aliases for already-sent callback buttons. They are
    # not shown in the new pinned FAQ, but old Telegram messages must not die.
    "faq:what_is_era": """🔥 <b>Что такое ЭРА?</b>

ЭРА — среда, где участник растёт через реальные события, проекты, задания и командную работу.""",
    "faq:what_it_gives": """⭐ <b>Что даёт ЭРА?</b>

Опыт, команду, портфолио, баллы и доступ к новым возможностям через реальный вклад.""",
}


class ChatFaqError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class FaqPublishResult:
    pinned: bool
    message_id: int


async def _latest_faq_message_id(session: AsyncSession) -> int | None:
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "chat.faq_published")
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    ).all()
    for row in rows:
        payload = row.new_value or {}
        if payload.get("chat") != "general":
            continue
        if isinstance(row.entity_id, int) and row.entity_id > 0:
            return row.entity_id
        legacy_message_id = payload.get("message_id")
        if isinstance(legacy_message_id, int) and legacy_message_id > 0:
            return legacy_message_id
    return None


async def _bot_username(bot: Bot, settings: Settings) -> str | None:
    if settings.bot_username:
        return settings.bot_username
    getter = getattr(bot, "get_me", None)
    if getter is None:
        return None
    me = await getter()
    return getattr(me, "username", None)


async def _upsert_faq_message(
    bot: Bot,
    settings: Settings,
    chat_id: int,
    session: AsyncSession,
) -> int:
    markup = faq_keyboard(await _bot_username(bot, settings))
    message_id = await _latest_faq_message_id(session)
    if message_id:
        try:
            await bot.edit_message_text(
                FAQ_PINNED_MESSAGE,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
                parse_mode="HTML",
            )
            return message_id
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return message_id
        except TelegramAPIError as exc:
            raise ChatFaqError("faq_refresh_failed") from exc

    try:
        sent = await bot.send_message(
            chat_id,
            FAQ_PINNED_MESSAGE,
            reply_markup=markup,
            parse_mode="HTML",
        )
    except TelegramAPIError as exc:
        raise ChatFaqError("send_failed") from exc
    return sent.message_id


async def publish_faq_message(
    bot: Bot, settings: Settings, session: AsyncSession, actor_id: int | None
) -> FaqPublishResult:
    chat_id = settings.general_chat_id
    if not chat_id:
        raise ChatFaqError("chat_not_bound")

    message_id = await _upsert_faq_message(bot, settings, int(chat_id), session)
    pinned = True
    try:
        await bot.pin_chat_message(int(chat_id), message_id, disable_notification=True)
    except TelegramAPIError:
        pinned = False

    await audit(
        session,
        actor_id=actor_id,
        action="chat.faq_published",
        entity_type="chat",
        entity_id=message_id,
        new_value={"chat": "general", "pinned": pinned},
    )
    await session.commit()
    return FaqPublishResult(pinned=pinned, message_id=message_id)


async def ensure_general_faq_pinned(
    bot: Bot, settings: Settings, session_factory
) -> None:
    """Refresh/edit the same FAQ card. Never create a navigation-message stream."""
    if not settings.general_chat_id:
        return
    async with session_factory() as session:
        try:
            await publish_faq_message(bot, settings, session, actor_id=None)
        except ChatFaqError:
            await session.rollback()
