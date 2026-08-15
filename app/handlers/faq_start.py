from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
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

router = Router(name="faq_start")

_PAYLOADS = {
    "faq_events": ("faq:events", "Открыть события", miniapp_events_url),
    "faq_projects": ("faq:projects", "Мои проекты", miniapp_projects_url),
    "faq_tasks": ("faq:tasks", "Открыть задания", miniapp_tasks_url),
    "faq_points": ("faq:points", "Мой прогресс", miniapp_profile_url),
    "faq_registration": ("faq:registration", "Посмотреть события", miniapp_events_url),
    "faq_active": ("faq:active", "Посмотреть возможности", miniapp_opportunities_url),
}


def _payload(message: Message) -> str | None:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].startswith("/start"):
        return None
    return parts[1].strip()


@router.message(StateFilter("*"), F.chat.type == "private", F.text.regexp(r"^/start(?:@\w+)?\s+faq_"))
async def faq_private_start(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    payload = _payload(message)
    if not user or user.application_status != ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        await message.answer(texts.APPLICATION_PENDING)
        return

    await state.clear()
    if payload == "faq_contact":
        await message.answer(FAQ_ANSWERS["faq:contact"], parse_mode="HTML")
        await message.answer(texts.QUESTION_START)
        await state.set_state(QuestionStates.text)
        return

    item = _PAYLOADS.get(payload or "")
    if item is None:
        await message.answer("Эта ссылка больше неактуальна. Откройте закреплённую навигацию ЭРА ещё раз.")
        return
    answer_key, label, url_builder = item
    url = url_builder(settings.effective_miniapp_url)
    markup = None
    if url:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
        )
    await message.answer(FAQ_ANSWERS[answer_key], parse_mode="HTML", reply_markup=markup)
