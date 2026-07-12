from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import User
from app.services.survey_service import survey_questions
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="participant_surveys")


class SurveyAnswerStates(StatesGroup):
    answer = State()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Отменить опрос", callback_data="survey:cancel")]]
    )


def _is_ready(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _ask(message: Message, survey: AdminSurvey, index: int, state: FSMContext) -> None:
    questions = survey_questions(survey)
    await state.update_data(survey_index=index, survey_questions=questions)
    await message.answer(
        f"🗳 {survey.title}\n\n"
        f"Вопрос {index + 1} из {len(questions)}\n"
        f"{questions[index]}\n\n"
        "Ответьте обычным сообщением — можно коротко, честно и по делу",
        reply_markup=_cancel_keyboard(),
    )


@router.callback_query(F.data.startswith("survey:start:"))
async def start_survey(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await call.answer()
    if not _is_ready(user):
        await call.message.answer("Опросы доступны после одобрения заявки участника")
        return
    survey_id = int(call.data.rsplit(":", 1)[-1])
    survey = await session.get(AdminSurvey, survey_id)
    if not survey or survey.status not in {"draft", "active", "sent"}:
        await call.message.answer("Этот опрос уже недоступен")
        return
    questions = survey_questions(survey)
    if not questions:
        await call.message.answer("В этом опросе пока нет вопросов")
        return
    existing = await session.scalar(
        select(AdminSurveyResponse).where(
            AdminSurveyResponse.survey_id == survey.id,
            AdminSurveyResponse.user_id == user.id,
        )
    )
    if existing and existing.status == "completed":
        await call.message.answer("Спасибо, Ваш ответ по этому опросу уже сохранён")
        return
    await state.set_state(SurveyAnswerStates.answer)
    await state.update_data(survey_id=survey.id, survey_index=0, survey_answers=[])
    await _ask(call.message, survey, 0, state)


@router.message(SurveyAnswerStates.answer)
async def collect_answer(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not _is_ready(user):
        await state.clear()
        await message.answer("Опрос остановлен: профиль участника сейчас недоступен")
        return
    answer = clean_text(message.text or message.caption or "", 2000)
    if not answer:
        await message.answer("Отправьте ответ текстом — так я смогу аккуратно сохранить его для аналитики")
        return
    data = await state.get_data()
    survey = await session.get(AdminSurvey, int(data.get("survey_id", 0)))
    if not survey:
        await state.clear()
        await message.answer("Опрос не найден, попробуйте открыть его заново")
        return
    questions = list(data.get("survey_questions") or survey_questions(survey))
    index = int(data.get("survey_index", 0))
    answers = list(data.get("survey_answers") or [])
    if index >= len(questions):
        await state.clear()
        await message.answer("Опрос уже завершён, спасибо за ответы")
        return
    answers.append({"question": questions[index], "answer": answer})
    index += 1
    if index < len(questions):
        await state.update_data(survey_index=index, survey_answers=answers)
        await _ask(message, survey, index, state)
        return

    existing = await session.scalar(
        select(AdminSurveyResponse).where(
            AdminSurveyResponse.survey_id == survey.id,
            AdminSurveyResponse.user_id == user.id,
        )
    )
    now = datetime.now().astimezone()
    if existing:
        existing.answers_json = answers
        existing.status = "completed"
        existing.submitted_at = now
    else:
        session.add(
            AdminSurveyResponse(
                survey_id=survey.id,
                user_id=user.id,
                answers_json=answers,
                status="completed",
                submitted_at=now,
            )
        )
    await session.commit()
    await state.clear()
    await message.answer(
        "Спасибо, ответ сохранён 🌿\n\n"
        "Это помогает ЭРА лучше видеть настроение команды, слабые места и идеи для следующего шага"
    )


@router.callback_query(F.data == "survey:cancel")
async def cancel_survey(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Опрос отменён. Если захотите — сможете пройти его позже")
