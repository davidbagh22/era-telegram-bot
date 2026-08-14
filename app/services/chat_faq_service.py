"""Pinned private-help FAQ for the registered general Telegram chat.

The general chat contains one compact card. Tapping a button never posts a
personal answer back into the group: app.handlers.chat_faq sends the answer to
the participant's DM. Publishing is idempotent — we reuse the latest recorded
FAQ message when Telegram still has it, so deploys do not create FAQ spam.
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

Не нужно искать ответы по сотням сообщений.
Выберите вопрос ниже — бот отправит короткий ответ <b>лично вам</b>, а общий чат останется чистым.

Если нужен человек, а не готовый ответ — нажмите «💬 Задать вопрос»."""

FAQ_ANSWERS: dict[str, str] = {
    "faq:what_is_era": """🔥 <b>Что такое ЭРА</b>

ЭРА — среда, где участник получает не «галочку за участие», а реальный опыт: знакомится с людьми, берёт задачи, создаёт проекты и постепенно начинает сам влиять на то, что происходит вокруг.

Путь простой:
<b>участник → активный → лидер</b>.

Не нужно сразу знать свою идеальную роль. Достаточно начать с одного действия — события, задачи или собственной идеи.""",
    "faq:what_it_gives": """🚀 <b>Как здесь расти</b>

Каждое реальное действие собирается в ваш путь внутри ЭРА:

• проекты и командный опыт;
• новые знакомства и рабочие связи;
• задачи, где виден результат;
• баллы, достижения и портфолио;
• доступ к новым ролям и возможностям.

Рост здесь не происходит «по стажу». Чем больше ответственности и результата вы берёте, тем быстрее открывается следующий уровень.""",
    "faq:what_to_do": """🧭 <b>С чего начать</b>

1. Откройте приложение ЭРА.
2. Посмотрите ближайшее событие или доступную задачу.
3. Выберите то, где действительно хочется включиться.
4. Есть своя идея — создайте проект, конструктор проведёт по шагам.

Не пытайтесь охватить всё сразу. Одно хорошо сделанное действие ценнее десяти сохранённых «на потом».""",
    "faq:what_can_i_do": """💡 <b>Как предложить идею</b>

Не нужно приносить готовый проект на двадцать страниц.

Откройте <b>ЭРА → Проекты → Новый проект</b> и начните с одного предложения: <i>что хотим сделать, для кого и зачем</i>.

Дальше конструктор поможет разобрать аудиторию, сценарий, команду, бюджет, продвижение, риски и результат. У каждого шага есть объяснение и короткий промпт для ИИ.

Сильная идея начинается не с идеального оформления, а с понятной пользы для людей.""",
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
        # New entries use the structured entity_id field. Read the older JSON
        # shape too so a deploy can reuse a FAQ card created by the previous
        # release instead of posting a duplicate.
        if isinstance(row.entity_id, int) and row.entity_id > 0:
            return row.entity_id
        legacy_message_id = payload.get("message_id")
        if isinstance(legacy_message_id, int) and legacy_message_id > 0:
            return legacy_message_id
    return None


async def _upsert_faq_message(bot: Bot, chat_id: int, session: AsyncSession) -> int:
    message_id = await _latest_faq_message_id(session)
    if message_id:
        try:
            await bot.edit_message_text(
                FAQ_PINNED_MESSAGE,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=faq_keyboard(),
            )
            return message_id
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return message_id
        except TelegramAPIError as exc:
            raise ChatFaqError("faq_refresh_failed") from exc

    try:
        sent = await bot.send_message(chat_id, FAQ_PINNED_MESSAGE, reply_markup=faq_keyboard())
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
