"""Pinned private-help FAQ for the registered general Telegram chat.

The general chat contains one compact card. Its primary buttons are t.me /start
links that open the participant's private bot chat immediately; the production
/start handler then returns the requested answer. Publishing is idempotent — we
reuse the latest recorded FAQ message when Telegram still has it, so deploys do
not create FAQ spam.
"""

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

FAQ_PINNED_MESSAGE = """🔥 <b>ЭРА — быстро о главном</b>

Здесь не нужно искать нужное сообщение в истории чата. Выберите вопрос — Telegram сразу откроет личный диалог с ботом и покажет ответ.

<b>ЭРА — это движение:</b> события → задачи → проекты → опыт → новые возможности.

Нужен не готовый ответ, а человек? Нажмите «💬 Задать вопрос»."""

FAQ_ANSWERS: dict[str, str] = {
    "faq:what_is_era": """🔥 <b>Что такое ЭРА?</b>

ЭРА — среда, где из участника вырастают лидеры через реальные проекты.

Здесь не просто приходят на мероприятия. Можно включиться в задачу, собрать команду, предложить свою идею и постепенно брать больше ответственности.

<b>Как устроен путь:</b>
Участник → Активный → Лидер.

Каждое действие остаётся в вашей истории: опыт, баллы, достижения и портфолио. Начать можно с одного шага — дальше система подскажет следующий.""",
    "faq:what_it_gives": """🚀 <b>Как здесь расти?</b>

В ЭРА рост не зависит от того, сколько месяцев вы состоите в чате. Он виден по действиям и результату.

<b>Что двигает вас вперёд:</b>
• участие в событиях;
• выполненные задачи;
• работа в проектной команде;
• собственные инициативы;
• помощь другим участникам.

За реальную активность формируются баллы, портфолио, новые роли и доступ к возможностям.

<b>Главное:</b> не пытайтесь сделать всё сразу. Одно хорошо доведённое дело сильнее десяти намерений.""",
    "faq:what_to_do": """🧭 <b>С чего начать?</b>

Если вы только вошли в ЭРА, не нужно изучать всю систему за один вечер.

<b>Первый маршрут:</b>
1. Откройте приложение ЭРА и проверьте профиль.
2. Посмотрите ближайшие события.
3. Выберите одну задачу или проект, где хочется включиться.
4. Сделайте первое действие — оно уже станет частью вашего пути.

Если пока не понимаете, что подходит именно вам, напишите через «💬 Задать вопрос» — поможем выбрать точку входа.""",
    "faq:what_can_i_do": """💡 <b>Как предложить идею?</b>

Не нужно заранее готовить презентацию или длинный документ.

Откройте <b>ЭРА → Проекты → Новый проект</b> и начните с простой формулы:
<i>что хотим сделать → для кого → зачем.</i>

Дальше конструктор проведёт по шагам: аудитория, сценарий, команда, бюджет, продвижение, риски и результат. У каждого вопроса есть объяснение и короткий промпт для ИИ.

Идея может быть сырой. Важно, чтобы в ней была понятная польза — форму мы поможем собрать.""",
}

# /start payload -> answer key. Kept next to the editorial copy so the pinned
# card, emergency /start route and tests share one source of truth.
FAQ_START_PAYLOADS: dict[str, str] = {
    "faq_what_is_era": "faq:what_is_era",
    "faq_what_it_gives": "faq:what_it_gives",
    "faq_what_to_do": "faq:what_to_do",
    "faq_what_can_i_do": "faq:what_can_i_do",
}
FAQ_CONTACT_PAYLOAD = "faq_contact"


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


async def _resolve_bot_username(bot: Bot, settings: Settings) -> str:
    configured = settings.bot_username.strip().lstrip("@")
    if configured:
        return configured
    try:
        me = await bot.get_me()
    except TelegramAPIError as exc:
        raise ChatFaqError("bot_identity_unavailable") from exc
    username = (me.username or "").strip().lstrip("@")
    if not username:
        raise ChatFaqError("bot_username_missing")
    return username


async def _upsert_faq_message(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    bot_username: str,
) -> int:
    message_id = await _latest_faq_message_id(session)
    keyboard = faq_keyboard(bot_username)
    if message_id:
        try:
            await bot.edit_message_text(
                FAQ_PINNED_MESSAGE,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard,
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
            reply_markup=keyboard,
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

    bot_username = await _resolve_bot_username(bot, settings)
    message_id = await _upsert_faq_message(
        bot,
        int(chat_id),
        session,
        bot_username,
    )
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
    """Fail-soft startup/maintenance job: keep the FAQ current and pinned."""
    if not settings.general_chat_id:
        return
    async with session_factory() as session:
        try:
            await publish_faq_message(bot, settings, session, actor_id=None)
        except ChatFaqError:
            await session.rollback()
