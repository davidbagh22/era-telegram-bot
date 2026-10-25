from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EventActivity, EventActivitySubmission, EventRegistration, User
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="participant_event_activities_block7")


class ActivitySubmitStates(StatesGroup):
    result = State()


def approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def activity_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"activity:submit:{activity_id}")]])


@router.callback_query(F.data.startswith("activity:submit:"))
async def activity_submit_start(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    activity = await session.get(EventActivity, int(call.data.rsplit(":", 1)[-1]))
    if not activity or not activity.is_active:
        await call.message.answer("Активность недоступна")
        return
    registration = await session.scalar(select(EventRegistration).where(
        EventRegistration.event_id == activity.event_id,
        EventRegistration.user_id == user.id,
    ))
    if registration is None:
        await call.message.answer("Активность доступна только участникам мероприятия")
        return
    existing = await session.scalar(select(EventActivitySubmission).where(EventActivitySubmission.activity_id == activity.id, EventActivitySubmission.user_id == user.id))
    if existing and existing.status == "approved":
        await call.message.answer("Эта активность уже принята. Повторно отправлять нельзя.")
        return
    if existing and existing.status in {"pending", "leader_approved"}:
        await call.message.answer("Ваш результат уже на проверке.")
        return
    await state.set_state(ActivitySubmitStates.result)
    await state.update_data(activity_id=activity.id)
    await call.message.answer(
        f"✨ {activity.title}\n\n{activity.description}\n\n"
        f"Формат результата: {activity.submission_type}\n"
        f"Баллы: {activity.points}\n\n"
        "Отправьте результат текстом, фото, видео или файлом."
    )


@router.message(ActivitySubmitStates.result)
async def activity_submit_finish(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    activity = await session.get(EventActivity, int(data["activity_id"]))
    if not activity or not activity.is_active:
        await state.clear()
        await message.answer("Активность недоступна")
        return
    text = clean_text(message.text or message.caption or "", 3000) or None
    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    if not text and not file_id:
        await message.answer("Добавьте текст или прикрепите материал.")
        return
    existing = await session.scalar(select(EventActivitySubmission).where(EventActivitySubmission.activity_id == activity.id, EventActivitySubmission.user_id == user.id))
    if existing:
        if existing.status == "approved":
            await state.clear()
            await message.answer("Эта активность уже принята.")
            return
        existing.text = text
        existing.file_id = file_id
        existing.file_type = file_type
        existing.status = "pending"
        existing.admin_comment = None
        existing.reviewed_by = None
    else:
        session.add(EventActivitySubmission(activity_id=activity.id, user_id=user.id, text=text, file_id=file_id, file_type=file_type, status="pending"))
    await state.clear()
    await message.answer("Результат отправлен на проверку. После решения Вы получите уведомление.")
