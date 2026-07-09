from datetime import date, datetime

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
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
from app.keyboards.participant import event_card_keyboard, event_list_keyboard
from app.services.event_service import (
    available_places,
    published_events,
    register_for_event,
)
from app.services.notification_service import notify_admins
from app.states.event import EventActivityStates, FeedbackStates, SelfieStates
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, RegistrationStatus
from app.utils.validators import clean_text

router = Router(name="events")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _send_event_list(
    message: Message, user: User | None, session: AsyncSession
) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    events = await published_events(session)
    if not events:
        await message.answer(ux_texts.EVENTS_EMPTY)
        return
    await message.answer(
        ux_texts.EVENTS_LIST_HEADER,
        reply_markup=event_list_keyboard(events),
    )


@router.message(F.text == "📅 Мероприятия")
@router.message(Command("events"), F.chat.type == "private")
async def event_list_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.callback_query(F.data == "events:list")
async def event_list(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    await _send_event_list(call.message, user, session)


@router.callback_query(F.data.startswith("event:view:"))
async def event_view(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event_id = int(call.data.rsplit(":", 1)[-1])
    event = await session.get(Event, event_id)
    if event is None:
        await call.message.answer(ux_texts.EVENTS_EMPTY)
        return
    places = await available_places(session, event)
    await call.message.answer(
        texts.event_card(event, available=places),
        reply_markup=event_card_keyboard(event.id),
    )


@router.callback_query(F.data.startswith("event:join:"))
async def event_join(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if event is None:
        await call.message.answer(ux_texts.EVENTS_EMPTY)
        return
    _, error = await register_for_event(session, event, user.id)
    if error == "already":
        await call.message.answer(texts.EVENT_ALREADY_REGISTERED)
    elif error == "full":
        await call.message.answer(texts.EVENT_FULL)
    elif error == "closed":
        await call.message.answer("Регистрация на это мероприятие уже закрыта")
    else:
        await call.message.answer(texts.event_registered(event))


@router.callback_query(F.data.startswith("attendance:"))
async def attendance_confirmation(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        return
    _, event_id, answer = call.data.split(":")
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == int(event_id),
            EventRegistration.user_id == user.id,
        )
    )
    if registration is None:
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
    event_id = int(call.data.rsplit(":", 1)[-1])
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
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    event_id = int(data["selfie_event_id"])
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
async def feedback_start(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    event_id = int(call.data.rsplit(":", 1)[-1])
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
async def feedback_rating(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(rating=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(FeedbackStates.liked)
    await call.message.answer(texts.FEEDBACK_LIKED)


@router.message(FeedbackStates.liked)
async def feedback_liked(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(liked=value)
    await state.set_state(FeedbackStates.improve)
    await message.answer(texts.FEEDBACK_IMPROVE)


@router.message(FeedbackStates.improve)
async def feedback_improve(message: Message, state: FSMContext) -> None:
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
    call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    await call.answer()
    data = await state.get_data()
    event_id = int(data["feedback_event_id"])
    existing = await session.scalar(
        select(Feedback).where(
            Feedback.event_id == event_id, Feedback.user_id == user.id
        )
    )
    values = dict(
        rating=data["rating"],
        liked=data["liked"],
        improve=data["improve"],
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
    activity = await session.get(EventActivity, int(call.data.rsplit(":", 1)[-1]))
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
    activity = await session.get(EventActivity, int(data["event_activity_id"]))
    if activity is None:
        await state.clear()
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
        "Спасибо — материал отправлен на проверку. После подтверждения баллы появятся в «Моём пути»"
    )
    await notify_admins(
        bot,
        settings,
        f"✨ Новый результат активности\n\n{user.first_name} {user.last_name or ''}\n"
        f"Активность: {activity.title}\nНаграда: {activity.points} баллов",
    )
