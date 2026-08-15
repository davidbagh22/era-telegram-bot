"""Handlers for the FAQ card's buttons in the general chat (see
app/services/chat_faq_service.py for how the card gets posted). Every
button here answers into the tapper's own DM, never back into the group --
group-chat bot messages are visible to everyone, so nothing personal (a
canned answer, a question to admins) ever lands in the shared chat.
2026-08 master spec, P5.
"""

from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import Settings
from app.database.models import User
from app.services.chat_faq_service import FAQ_ANSWERS
from app.services.notification_service import safe_send
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import miniapp_events_url, miniapp_profile_url

router = Router(name="chat_faq")
router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked)


def _miniapp_button(label: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


async def _send_private_route(
    call: CallbackQuery,
    user: User | None,
    bot: Bot,
    settings: Settings,
    *,
    label: str,
    text: str,
    url: str,
) -> None:
    if not _approved(user):
        await call.answer(texts.APPLICATION_PENDING, show_alert=True)
        return
    if not settings.effective_miniapp_url or not url:
        await call.answer("Приложение ЭРА временно недоступно", show_alert=True)
        return
    ok = await safe_send(
        bot,
        user.telegram_id,
        text,
        reply_markup=_miniapp_button(label, url),
    )
    if ok:
        await call.answer("Открыл раздел в личных сообщениях 👍")
    else:
        await call.answer(texts.FAQ_ANSWER_SEND_FAILED, show_alert=True)


@router.callback_query(F.data == "faq:events")
async def faq_events(
    call: CallbackQuery, user: User | None, bot: Bot, settings: Settings
) -> None:
    await _send_private_route(
        call,
        user,
        bot,
        settings,
        label="📅 Открыть события",
        text="📅 События ЭРА\n\nАфиша, регистрация и ваши ближайшие события — в приложении.",
        url=miniapp_events_url(settings.effective_miniapp_url),
    )


@router.callback_query(F.data == "faq:profile")
async def faq_profile(
    call: CallbackQuery, user: User | None, bot: Bot, settings: Settings
) -> None:
    await _send_private_route(
        call,
        user,
        bot,
        settings,
        label="👤 Открыть мой профиль",
        text="👤 Ваш профиль ЭРА\n\nБаллы, путь, достижения и портфолио — в одном месте.",
        url=miniapp_profile_url(settings.effective_miniapp_url),
    )


@router.callback_query(F.data.in_(FAQ_ANSWERS))
async def faq_answer(call: CallbackQuery, user: User | None, bot: Bot) -> None:
    if not _approved(user):
        await call.answer(texts.APPLICATION_PENDING, show_alert=True)
        return
    ok = await safe_send(
        bot,
        user.telegram_id,
        FAQ_ANSWERS[call.data],
        parse_mode="HTML",
    )
    if ok:
        await call.answer("Ответ отправлен вам в личные сообщения 👍")
    else:
        await call.answer(texts.FAQ_ANSWER_SEND_FAILED, show_alert=True)


@router.callback_query(F.data == "faq:contact")
async def faq_contact(call: CallbackQuery, user: User | None, bot: Bot, state: FSMContext) -> None:
    if not _approved(user):
        await call.answer(texts.APPLICATION_PENDING, show_alert=True)
        return
    ok = await safe_send(bot, user.telegram_id, texts.QUESTION_START)
    if not ok:
        await call.answer(texts.FAQ_ANSWER_SEND_FAILED, show_alert=True)
        return
    # `state` here is scoped to (this group chat, user) -- the reply the
    # user is about to type will arrive as a *private* message, which
    # aiogram keys by (private_chat_id, user_id) instead. Building a second
    # FSMContext on the same storage but with the private chat's key is the
    # standard aiogram way to pre-arm a conversation state in a chat the
    # handler isn't currently running in.
    private_key = StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
    private_state = FSMContext(storage=state.storage, key=private_key)
    await private_state.set_state(QuestionStates.text)
    await call.answer("Открыл вопрос в личных сообщениях 👍")
