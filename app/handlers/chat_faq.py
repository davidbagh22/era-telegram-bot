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
from app.utils.deep_links import (
    miniapp_events_url,
    miniapp_opportunities_url,
    miniapp_profile_url,
    miniapp_projects_url,
    miniapp_tasks_url,
)

router = Router(name="chat_faq")
router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))

# Pinned FAQ callbacks that must open Mini App (parity with /start faq_* payloads).
_MINIAPP_FAQ_ROUTES: dict[str, tuple[str, object]] = {
    "faq:events": ("📅 Открыть события", miniapp_events_url),
    "faq:projects": ("🚀 Открыть проекты", miniapp_projects_url),
    "faq:tasks": ("✅ Открыть задания", miniapp_tasks_url),
    "faq:points": ("⭐ Открыть прогресс", miniapp_profile_url),
    "faq:registration": ("📅 Посмотреть события", miniapp_events_url),
    "faq:active": ("🌍 Смотреть возможности", miniapp_opportunities_url),
}
_LEGACY_FAQ_ANSWERS = {
    key: value
    for key, value in FAQ_ANSWERS.items()
    if key not in _MINIAPP_FAQ_ROUTES and key != "faq:contact"
}


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
    parse_mode: str | None = None,
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
        parse_mode=parse_mode,
    )
    if ok:
        await call.answer("Открыл раздел в личных сообщениях 👍")
    else:
        await call.answer(texts.FAQ_ANSWER_SEND_FAILED, show_alert=True)


@router.callback_query(F.data.in_(set(_MINIAPP_FAQ_ROUTES)))
async def faq_miniapp_route(
    call: CallbackQuery, user: User | None, bot: Bot, settings: Settings
) -> None:
    label, url_builder = _MINIAPP_FAQ_ROUTES[call.data]
    await _send_private_route(
        call,
        user,
        bot,
        settings,
        label=label,
        text=FAQ_ANSWERS[call.data],
        url=url_builder(settings.effective_miniapp_url),
        parse_mode="HTML",
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


@router.callback_query(F.data.in_(_LEGACY_FAQ_ANSWERS))
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
