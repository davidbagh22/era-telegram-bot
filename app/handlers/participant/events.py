from datetime import date, datetime

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    AttendanceProof,
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    Feedback,
    User,
)
from app.services.notification_service import notify_admins
from app.states.event import EventActivityStates, FeedbackStates, SelfieStates
from app.utils import texts
from app.utils.callback_ids import positive_pg_int_callback, positive_pg_int_value
from app.utils.constants import ApplicationStatus, RegistrationStatus
from app.utils.validators import clean_text

router = Router(name="events_supplemental")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


# Afisha/list, event:view:* and event:join:* are intentionally owned by
# events_stability_block8. This module contains only supplemental flows that
# happen around/after an event so router order cannot silently choose between
# two implementations of registration.


@router.callback_query(F.data.startswith("attendance:"))
async def attendance_confirmation(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        return
    parts = (call.data or "").split(":")
    if len(parts) != 3 or parts[0] != "attendance" or parts[2] not in {"yes", "no"}:
        return
    event_id = positive_pg_int_value(parts[1])
    if event_id is None:
        return
    answer = parts[2]
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
        )
    )
    if registration is None:
        return
    if registration.status in {RegistrationStatus.ATTENDED, RegistrationStatus.NO_SHOW, RegistrationStatus.CANCELLED}:
        await call.message.answer("Итог посещения уже зафиксирован. Старое напоминание его не изменяет.")
        return
    registration.status = (
        RegistrationStatus.WILL_COME
        if answer == "yes"
        else RegistrationStatus.NOT_COMING
    )
    await call.message.answer(
        texts.EVENT_CONFIRM_YES if answer == "yes" else texts.EVENT_CONFIRM_NO
    )


@router.callback_query(F.data.startswith("selfie:start:"))
async def selfie_start(
    call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await call.answer()
    if not _approved(user):
        return
    event_id = positive_pg_int_callback(call.data, "selfie:start:")
    if event_id is None:
        await call.message.answer(texts.SELFIE_INVALID)
        return
    event = await session.get(Event, event_id)
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
        )
    )
    if event is None or registration is None or event.event_date != date.today():
        await call.message.answer(texts.SELFIE_INVALID)
        return
    await state.set_state(SelfieStates.photo)
    await state.update_data(selfie_event_id=event_id)
    await call.message.answer(texts.SELFIE_REQUEST)


@router.message(SelfieStates.photo, F.photo)
async def selfie_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User | None,
    bot: Bot,
    settings: Settings,
) -> None:
    # The photo can arrive after the user is blocked or their application is revoked.
    # Fail closed before reading stale FSM data or touching attendance proofs.
    if not _approved(user):
        await state.clear()
        await message.answer(texts.SELFIE_INVALID)
        return
    data = await state.get_data()
    event_id = positive_pg_int_value(data.get("selfie_event_id"))
    if event_id is None:
        await state.clear()
        await message.answer(texts.SELFIE_INVALID)
        return
    # The event or registration can disappear or move to another date while
    # the participant is uploading a photo. Enforce the same eligibility
    # conditions as selfie_start before creating or updating a proof.
    event = await session.get(Event, event_id)
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user.id,
        )
    )
    if event is None or registration is None or event.event_date != date.today():
        await state.clear()
        await message.answer(texts.SELFIE_INVALID)
        return
    exists = await session.scalar(
        select(AttendanceProof).where(
            AttendanceProof.event_id == event_id,
            AttendanceProof.user_id == user.id,
        )
    )
    if exists:
        exists.photo_file_id = message.photo[-1].file_id
        exists.status = "pending"
        proof = exists
    else:
        proof = AttendanceProof(
            event_id=event_id,
            user_id=user.id,
            photo_file_id=message.photo[-1].file_id,
        )
        session.add(proof)
    await session.flush()
    await state.clear()
    await message.answer(texts.SELFIE_PENDING)
    await notify_admins(
        bot,
        settings,
        f"Новое селфи-подтверждение #{proof.id}. Откройте панель администратора для проверки.",
    )


@router.message(SelfieStates.photo)
async def selfie_not_photo(message: Message) -> None:
    await message.answer("Отправьте фотографию как изображение.")


@router.callback_query(F.data.startswith("feedback:start:"))
async def feedback_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer("Отзывы доступны только подтверждённым участникам.")
        return
    event_id = positive_pg_int_callback(call.data, "feedback:start:")
    if event_id is None:
        await call.message.answer("Мероприятие не найдено. Откройте отзыв заново.")
        return
    await state.set_state(FeedbackStates.rating)
    await state.update_data(feedback_event_id=event_id)
    buttons = [
        [
            InlineKeyboardButton(text=str(i), callback_data=f"feedback:rating:{i}")
            for i in range(1, 6)
        ]
    ]
    await call.message.answer(
        texts.FEEDBACK_RATING,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(FeedbackStates.rating, F.data.startswith("feedback:rating:"))
async def feedback_rating(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    await call.answer()
    if not _approved(user):
        await state.clear()
        await call.message.answer("Отзывы доступны только подтверждённым участникам.")
        return
    # Telegram callback data is untrusted, including stale and forged buttons.
    raw_rating = (call.data or "").removeprefix("feedback:rating:")
    if not (call.data or "").startswith("feedback:rating:") or raw_rating not in {"1", "2", "3", "4", "5"}:
        await call.message.answer("Выберите оценку от 1 до 5.")
        return
    await state.update_data(rating=int(raw_rating))
    await state.set_state(FeedbackStates.liked)
    await call.message.answer(texts.FEEDBACK_LIKED)


@router.message(FeedbackStates.liked)
async def feedback_liked(
    message: Message, state: FSMContext, user: User | None
) -> None:
    if not _approved(user):
        await state.clear()
        await message.answer("Отзывы доступны только подтверждённым участникам.")
        return
    value = clean_text(message.text or "", 1000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(liked=value)
    await state.set_state(FeedbackStates.improve)
    await message.answer(texts.FEEDBACK_IMPROVE)


@router.message(FeedbackStates.improve)
async def feedback_improve(
    message: Message, state: FSMContext, user: User | None
) -> None:
    if not _approved(user):
        await state.clear()
        await message.answer("Отзывы доступны только подтверждённым участникам.")
        return
    value = clean_text(message.text or "", 1000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(improve=value)
    await state.set_state(FeedbackStates.wants_again)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=value, callback_data=f"feedback:again:{key}")]
            for value, key in (("Да", "yes"), ("Нет", "no"), ("Пока не знаю", "unsure"))
        ]
    )
    await message.answer(texts.FEEDBACK_AGAIN, reply_markup=keyboard)


@router.callback_query(FeedbackStates.wants_again, F.data.startswith("feedback:again:"))
async def feedback_finish(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User | None
) -> None:
    await call.answer()
    if not _approved(user):
        await state.clear()
        await call.message.answer("Отзывы доступны только подтверждённым участникам.")
        return
    # Stale/forged buttons and corrupted FSM data must not reach PostgreSQL.
    if call.data not in {"feedback:again:yes", "feedback:again:no", "feedback:again:unsure"}:
        await call.message.answer("Выберите один из предложенных вариантов.")
        return
    data = await state.get_data()
    event_id = positive_pg_int_value(data.get("feedback_event_id"))
    rating = data.get("rating")
    liked = data.get("liked")
    improve = data.get("improve")
    if (
        event_id is None
        or type(rating) is not int
        or not 1 <= rating <= 5
        or not isinstance(liked, str)
        or not 1 <= len(liked.strip()) <= 1000
        or not isinstance(improve, str)
        or not 1 <= len(improve.strip()) <= 1000
    ):
        await state.clear()
        await call.message.answer("Отзыв устарел. Откройте мероприятие и начните заново.")
        return
    existing = await session.scalar(
        select(Feedback).where(
            Feedback.event_id == event_id, Feedback.user_id == user.id
        )
    )
    values = dict(
        rating=rating,
        liked=liked,
        improve=improve,
        wants_again=call.data.rsplit(":", 1)[-1],
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        session.add(Feedback(event_id=event_id, user_id=user.id, **values))
    await state.clear()
    await call.message.answer(texts.FEEDBACK_DONE)


@router.callback_query(F.data.startswith("event:activity:"))
async def event_activity_start(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    activity_id = positive_pg_int_callback(call.data, "event:activity:")
    if activity_id is None:
        await call.message.answer("Эта активность уже закрыта")
        return
    activity = await session.get(EventActivity, activity_id)
    if (
        activity is None
        or not activity.is_active
        or (activity.deadline and activity.deadline <= datetime.now().astimezone())
    ):
        await call.message.answer("Эта активность уже закрыта")
        return
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == activity.event_id,
            EventRegistration.user_id == user.id,
        )
    )
    if registration is None:
        await call.message.answer("Активность доступна участникам мероприятия")
        return
    existing = await session.scalar(
        select(EventActivitySubmission).where(
            EventActivitySubmission.activity_id == activity.id,
            EventActivitySubmission.user_id == user.id,
        )
    )
    if existing and existing.status in {"pending", "approved"}:
        await call.message.answer("Ваш ответ уже сохранён")
        return
    await state.set_state(EventActivityStates.submission)
    await state.update_data(event_activity_id=activity.id)
    expected = {
        "text": "сообщение",
        "feedback": "сообщение с Вашим мнением",
        "photo": "фотографию",
        "video": "видео",
        "file": "файл",
    }.get(activity.submission_type, "сообщение или файл")
    await call.message.answer(
        f"✨ {activity.title}\n\n{activity.description}\n\n"
        f"Награда: {activity.points} баллов\n\nОтправьте {expected}"
    )


@router.message(EventActivityStates.submission)
async def event_activity_submit(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    activity_id = positive_pg_int_value(data.get("event_activity_id"))
    if activity_id is None:
        await state.clear()
        await message.answer("Активность недоступна. Откройте её заново.")
        return
    # FSM can outlive approval, registration or the activity deadline. Recheck
    # eligibility at submission time rather than trusting the earlier callback.
    if not _approved(user):
        await state.clear()
        await message.answer("Активность недоступна. Откройте её заново.")
        return
    activity = await session.get(EventActivity, activity_id)
    if (
        activity is None
        or not activity.is_active
        or (activity.deadline and activity.deadline <= datetime.now().astimezone())
    ):
        await state.clear()
        await message.answer("Эта активность уже закрыта")
        return
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == activity.event_id,
            EventRegistration.user_id == user.id,
        )
    )
    if registration is None:
        await state.clear()
        await message.answer("Активность доступна участникам мероприятия")
        return
    file_id = file_type = None
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.document:
        file_id, file_type = message.document.file_id, "file"
    text_value = clean_text(message.text or message.caption or "", 3000) or None
    if not file_id and not text_value:
        await message.answer("Отправьте текст, фотографию, видео или файл")
        return
    expected = activity.submission_type
    if expected in {"photo", "video", "file"} and file_type != expected:
        await message.answer(f"Для этой активности нужен формат: {expected}")
        return
    existing = await session.scalar(
        select(EventActivitySubmission).where(
            EventActivitySubmission.activity_id == activity.id,
            EventActivitySubmission.user_id == user.id,
        )
    )
    # A stale FSM message must not overwrite a submission already in review or
    # approved for points. Rejected submissions may still be corrected.
    if existing and existing.status in {"pending", "approved"}:
        await state.clear()
        await message.answer("Ваш ответ уже сохранён")
        return
    if existing:
        existing.text = text_value
        existing.file_id = file_id
        existing.file_type = file_type
        existing.status = "pending"
    else:
        session.add(
            EventActivitySubmission(
                activity_id=activity.id,
                user_id=user.id,
                text=text_value,
                file_id=file_id,
                file_type=file_type,
            )
        )
    await state.clear()
    await message.answer(
        "Спасибо — материал отправлен на проверку. После подтверждения баллы появятся в вашем профиле"
    )
    await notify_admins(
        bot,
        settings,
        f"✨ Новый результат активности\n\n{user.first_name} {user.last_name or ''}\n"
        f"Активность: {activity.title}\nНаграда: {activity.points} баллов",
    )
