from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import Settings
from app.database.models import User
from app.services.chat_faq_service import FAQ_ANSWERS
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

_PAYLOADS = {
    "faq_events": ("faq:events", "Открыть события", miniapp_events_url),
    "faq_projects": ("faq:projects", "Мои проекты", miniapp_projects_url),
    "faq_tasks": ("faq:tasks", "Открыть задания", miniapp_tasks_url),
    "faq_points": ("faq:points", "Мой прогресс", miniapp_profile_url),
    "faq_registration": ("faq:registration", "Посмотреть события", miniapp_events_url),
    "faq_active": ("faq:active", "Посмотреть возможности", miniapp_opportunities_url),
}


def is_faq_payload(payload: str | None) -> bool:
    return bool(payload and payload.startswith("faq_"))


async def try_handle_faq_payload(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    payload: str | None,
) -> bool:
    """Handle a pinned-chat /start payload inside the production start owner.

    emergency.router intentionally remains the first dispatcher router. Keeping
    FAQ handling as a helper here avoids breaking the global FSM recovery
    invariant while still letting the pinned FAQ open a private, contextual
    answer before the generic main menu fallback.
    """
    if not is_faq_payload(payload):
        return False
    if (
        not user
        or user.application_status != ApplicationStatus.APPROVED
        or user.is_blocked
        or user.is_archived
    ):
        await message.answer(texts.APPLICATION_PENDING)
        return True

    await state.clear()
    if payload == "faq_contact":
        await message.answer(FAQ_ANSWERS["faq:contact"], parse_mode="HTML")
        await message.answer(texts.QUESTION_START)
        await state.set_state(QuestionStates.text)
        return True

    item = _PAYLOADS.get(payload or "")
    if item is None:
        await message.answer(
            "Эта ссылка больше неактуальна. Откройте закреплённую навигацию ЭРА ещё раз."
        )
        return True
    answer_key, label, url_builder = item
    url = url_builder(settings.effective_miniapp_url)
    markup = None
    if url:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]
            ]
        )
    await message.answer(
        FAQ_ANSWERS[answer_key], parse_mode="HTML", reply_markup=markup
    )
    return True
