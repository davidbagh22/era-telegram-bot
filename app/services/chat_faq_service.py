"""Pinned private-help FAQ and persistent quick navigation for the general chat.

The FAQ card answers privately so the shared chat stays clean. The separate
persistent reply keyboard gives the group two always-visible shortcuts; presses
are intercepted and converted into private Mini App routes by app.handlers.chat.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AuditLog
from app.keyboards.faq import faq_keyboard, general_chat_navigation_keyboard
from app.services.audit_service import audit

FAQ_PINNED_MESSAGE = """🔥 <b>ЭРА — быстро о главном</b>

ЭРА — это не просто чат. Здесь участие превращается в проекты, опыт, новые связи и возможности.

<b>События</b> и <b>мой профиль</b> всегда доступны кнопками внизу чата. Остальные быстрые ответы — ниже.

Выберите вопрос — бот ответит <b>лично вам</b>, а общий чат останется чистым.

Если нужен человек — нажмите «💬 Задать вопрос»."""

GENERAL_NAV_MESSAGE = """⚡ <b>Быстрый доступ включён</b>

События и ваш профиль теперь всегда доступны кнопками внизу общего чата."""

FAQ_ANSWERS: dict[str, str] = {
    "faq:what_is_era": """🔥 <b>Что такое ЭРА?</b>

ЭРА — среда, где из участника вырастают лидеры через реальные проекты.

Здесь не просто приходят на мероприятия: участники знакомятся, берут задачи, создают идеи, собирают команды и постепенно начинают сами влиять на то, что происходит вокруг.

Главная логика:
<b>участие → опыт → баллы → возможности → лидерство.</b>

Не нужно сразу знать свою идеальную роль. Достаточно начать с одного реального действия.""",
    "faq:what_it_gives": """🚀 <b>Как здесь расти?</b>

Не нужно ждать, пока вас кто-то назовёт активным. Рост начинается с того, что вы делаете.

• приходите на события;
• берите задачи;
• участвуйте в проектах;
• предлагайте идеи;
• помогайте команде.

За реальную активность вы получаете опыт, баллы, достижения и доступ к новым возможностям.

Ваш путь в ЭРА:
<b>Участник → Активный → Лидер.</b>

Здесь растут не «по стажу», а через ответственность и результат.""",
    "faq:what_to_do": """🧭 <b>С чего начать?</b>

Если вы только пришли в ЭРА — не пытайтесь разобраться во всём сразу.

<b>1.</b> Откройте приложение ЭРА и заполните профиль.
<b>2.</b> Посмотрите ближайшие события и проекты.
<b>3.</b> Выберите одно действие: запишитесь, возьмите задачу или присоединитесь к проекту.

Первый шаг важнее идеального плана. Всё остальное станет понятнее уже в движении.""",
    "faq:what_can_i_do": """💡 <b>Как предложить идею?</b>

Идея в ЭРА не должна оставаться сообщением в чате.

Откройте <b>ЭРА → Проекты → Новый проект</b> и коротко опишите:
• что хотите сделать;
• для кого;
• какой результат хотите получить.

Дальше система поможет собрать идею в полноценный проект, а команда сможет дать обратную связь и провести её дальше.

Даже если идея пока сырая — начните с первого варианта. Сильные проекты редко рождаются идеально готовыми.""",
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


async def _navigation_keyboard_already_published(session: AsyncSession) -> bool:
    marker = await session.scalar(
        select(AuditLog.id)
        .where(AuditLog.action == "chat.navigation_keyboard_published")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return marker is not None


async def _upsert_faq_message(bot: Bot, chat_id: int, session: AsyncSession) -> int:
    message_id = await _latest_faq_message_id(session)
    if message_id:
        try:
            await bot.edit_message_text(
                FAQ_PINNED_MESSAGE,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=faq_keyboard(),
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
            reply_markup=faq_keyboard(),
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

    message_id = await _upsert_faq_message(bot, int(chat_id), session)
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


async def publish_general_navigation_keyboard(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    actor_id: int | None = None,
) -> int | None:
    """Publish the persistent group dock once for existing members.

    New members receive the same keyboard from the welcome handler, so deploys
    must not create repeated navigation messages in the shared chat.
    """
    if not settings.general_chat_id:
        raise ChatFaqError("chat_not_bound")
    if await _navigation_keyboard_already_published(session):
        return None
    try:
        sent = await bot.send_message(
            int(settings.general_chat_id),
            GENERAL_NAV_MESSAGE,
            reply_markup=general_chat_navigation_keyboard(),
            parse_mode="HTML",
        )
    except TelegramAPIError as exc:
        raise ChatFaqError("navigation_keyboard_send_failed") from exc
    await audit(
        session,
        actor_id=actor_id,
        action="chat.navigation_keyboard_published",
        entity_type="chat",
        entity_id=sent.message_id,
        new_value={"chat": "general"},
    )
    await session.commit()
    return sent.message_id


async def ensure_general_faq_pinned(
    bot: Bot, settings: Settings, session_factory
) -> None:
    """Fail-soft startup/maintenance job: keep FAQ current and quick nav available."""
    if not settings.general_chat_id:
        return
    async with session_factory() as session:
        try:
            await publish_faq_message(bot, settings, session, actor_id=None)
        except ChatFaqError:
            await session.rollback()
        try:
            await publish_general_navigation_keyboard(bot, settings, session, actor_id=None)
        except ChatFaqError:
            await session.rollback()
