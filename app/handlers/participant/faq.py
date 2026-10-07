"""Private FAQ navigation; feature actions use their existing callback owners."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.era_faq import (
    FAQ_CATEGORIES,
    FAQ_DATA,
    FAQ_HOME_TEXT,
    faq_category_text,
)
from app.database.models import User
from app.handlers.participant.navigation import _approved
from app.keyboards.faq import (
    faq_category_keyboard,
    faq_home_keyboard,
    get_faq_answer_keyboard,
)
from app.services.audit_service import audit
from app.utils import texts
from app.utils.telegram import edit_text_or_answer

router = Router(name="participant_faq")


@router.callback_query(F.data == "faq:home")
@router.callback_query(F.data.startswith("faq:cat:"))
@router.callback_query(F.data.startswith("faq:q:"))
async def faq_navigation(
    call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession
) -> None:
    if not _approved(user):
        await call.answer(texts.APPLICATION_PENDING, show_alert=True)
        return
    await state.clear()
    category_id = question_id = None
    if call.data == "faq:home":
        text, keyboard = FAQ_HOME_TEXT, faq_home_keyboard()
        event = "faq_opened"
    elif call.data.startswith("faq:cat:"):
        category_id = call.data.removeprefix("faq:cat:")
        if category_id not in FAQ_CATEGORIES:
            await call.answer("Раздел не найден")
            await edit_text_or_answer(
                call.message,
                FAQ_HOME_TEXT,
                reply_markup=faq_home_keyboard(),
                parse_mode=None,
            )
            return
        text, keyboard = (
            faq_category_text(category_id),
            faq_category_keyboard(category_id),
        )
        event = "faq_category_opened"
    else:
        question_id = call.data.removeprefix("faq:q:")
        item = FAQ_DATA.get(question_id)
        if not item or item["category"] not in FAQ_CATEGORIES:
            await call.answer("Ответ не найден")
            await edit_text_or_answer(
                call.message,
                FAQ_HOME_TEXT,
                reply_markup=faq_home_keyboard(),
                parse_mode=None,
            )
            return
        category_id = item["category"]
        text = item["text"]
        keyboard = get_faq_answer_keyboard(f"faq:cat:{category_id}", item.get("action"))
        event = "faq_question_opened"
    await call.answer()
    await edit_text_or_answer(
        call.message, text, reply_markup=keyboard, parse_mode=None
    )
    await audit(
        session,
        actor_id=user.id,
        action=event,
        entity_type="faq",
        new_value={
            "user_id": user.id,
            "category": category_id,
            "question": question_id,
            "action": None,
        },
    )
