from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.states.event import EventConfirmationStates
from app.config import Settings
from app.database.models import Event, EventActivity, User
from app.keyboards.participant import event_list_keyboard
from app.services.event_card import send_event_card
from app.services.notification_service import safe_answer_document
from app.services.event_registration_service import registration_stats
from app.services.event_service import (
    PUBLIC_EVENT_STATUSES,
    REGISTRATION_ALLOWED_STATUSES,
    published_events,
    register_for_event,
)
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_events_stability_block8")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _event_keyboard(event_id: int, *, can_register: bool, has_activities: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_register:
        rows.append([InlineKeyboardButton(text="Зарегистрироваться", callback_data=f"event:join:{event_id}")])
    if has_activities:
        rows.append([InlineKeyboardButton(text="✨ Активности", callback_data=f"event:activities:{event_id}")])
    rows.append([InlineKeyboardButton(text="Добавить в календарь", callback_data=f"event:calendar:{event_id}")])
    rows.append([InlineKeyboardButton(text="← Афиша", callback_data="events:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_event_list(message: Message, user: User | None, session: AsyncSession) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    events = await published_events(session)
    if not events:
        await message.answer(
            "📅 Афиша\n\nСейчас нет открытых мероприятий. Как только команда ЭРА опубликует новое событие, оно появится здесь",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")]]
            ),
        )
        return
    await message.answer(ux_texts.EVENTS_LIST_HEADER, reply_markup=event_list_keyboard(events))


@router.message(F.text.in_({"📅 Афиша", "📅 Мероприятия"}))
@router.message(Command("events"), F.chat.type == "private")
async def event_list_button(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.callback_query(F.data == "events:list")
async def event_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    await _send_event_list(call.message, user, session)


@router.callback_query(F.data.startswith("event:view:"))
async def event_view(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings | None = None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await call.message.answer("Это мероприятие сейчас недоступно в афише")
        return
    stats = await registration_stats(session, event)
    can_register = (
        event.status in REGISTRATION_ALLOWED_STATUSES
        and (event.participant_limit is None or int(stats["free"]) > 0)
    )
    has_activities = bool(
        await session.scalar(
            select(func.count())
            .select_from(EventActivity)
            .where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True))
        )
    )
    extra = None
    if event.status not in REGISTRATION_ALLOWED_STATUSES:
        extra = "Регистрация закрыта, но карточка мероприятия остаётся доступна."
    elif event.participant_limit is not None and int(stats["free"]) <= 0:
        extra = "Свободных мест сейчас нет."
    keyboard = _event_keyboard(event.id, can_register=can_register, has_activities=has_activities)
    if settings is not None:
        from app.services.event_attendance_service import attendance_v2_enabled, participant_state
        if attendance_v2_enabled(settings, call.from_user.id):
            attendance = await participant_state(session, event.id, user.id)
            if attendance.confirmation_open:
                keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="✅ Подтвердить посещение кодом", callback_data=f"event:confirm_code:{event.id}")])
    await send_event_card(
        call.message,
        event,
        available=str(stats["free"]),
        registered=int(stats["registered"]),
        extra_text=extra,
        keyboard=keyboard,
    )


@router.callback_query(F.data.regexp(r"^event:calendar:[0-9]+$"), F.message.chat.type == "private")
async def event_calendar(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings):
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    from app.database.event_experience import EventExperience
    from app.services.event_calendar_service import build_event_calendar
    from app.database.models import EventRegistration
    from app.utils.constants import EventStatus
    event_id = int(call.data.rsplit(":", 1)[-1])
    event = await session.get(Event, event_id)
    registration = await session.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == user.id))
    if event is None or (event.status not in PUBLIC_EVENT_STATUSES and not (
        registration and event.status in {EventStatus.CANCELLED, EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}
    )):
        await call.message.answer("Мероприятие недоступно.")
        return
    experience = await session.get(EventExperience, event_id)
    await safe_answer_document(call.message,
        BufferedInputFile(build_event_calendar(event, experience, timezone_name=settings.timezone),
                          filename=f"ERA-{event_id}.ics"),
        caption=f"Время события: {settings.timezone}. Импортируйте файл в календарь. После изменения события скачайте актуальную версию.",
    )


@router.callback_query(F.data.startswith("event:join:"))
async def event_join(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await call.message.answer("Это мероприятие сейчас недоступно")
        return
    _, error = await register_for_event(session, event, user.id)
    if error == "already":
        await call.message.answer(texts.EVENT_ALREADY_REGISTERED)
        return
    if error == "full":
        await call.message.answer(texts.EVENT_FULL)
        return
    if error == "closed":
        await call.message.answer("Регистрация на это мероприятие закрыта, но само событие остаётся в афише")
        return
    stats = await registration_stats(session, event)
    await call.message.answer(
        texts.event_registered(event)
        + f"\n\nЗарегистрировано: {stats['registered']}"
        + (f"\nСвободных мест: {stats['free']}" if event.participant_limit is not None else "")
    )


@router.callback_query(F.data.regexp(r"^event:confirm_code:[0-9]+$"), F.message.chat.type == "private")
async def confirmation_code_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    await call.answer()
    from app.services.event_attendance_service import attendance_v2_enabled, participant_state
    if not _approved(user) or not attendance_v2_enabled(settings, call.from_user.id):
        return
    event_id = int(call.data.rsplit(':', 1)[-1])
    try:
        attendance = await participant_state(session, event_id, user.id)
    except ValueError:
        await call.message.answer('Мероприятие не найдено.')
        return
    if not attendance.confirmation_open:
        await call.message.answer('Подтверждение сейчас закрыто или посещение уже отмечено.')
        return
    from app.states.event import EventConfirmationStates
    await state.set_state(EventConfirmationStates.code)
    await state.update_data(attendance_event_id=event_id)
    await call.message.answer('Введите код, который дал ведущий. Например: ABCD-2345. /cancel отменяет ввод.')


@router.message(EventConfirmationStates.code, F.chat.type == "private", F.text)
async def confirmation_code_submit(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    from app.services.event_attendance_service import attendance_v2_enabled, confirm_attendance
    if not _approved(user) or not attendance_v2_enabled(settings, message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    event_id = data.get('attendance_event_id')
    if not event_id or len(message.text or '') > 32:
        await message.answer('Введите короткий код от ведущего или нажмите /cancel.')
        return
    try:
        result = await confirm_attendance(session, int(event_id), user.id, message.text)
    except ValueError as exc:
        if str(exc) == 'invalid_attendance_code':
            await message.answer('Код не подошёл. Проверьте его у ведущего и повторите ввод.')
        else:
            await state.clear()
            await message.answer('Подтверждение недоступно. Проверьте регистрацию и открыто ли окно подтверждения.')
        return
    from app.services.referral_service import award_first_event_referral
    await award_first_event_referral(session, invitee_user_id=user.id, event_id=int(event_id))
    await session.commit()
    await state.clear()
    await message.answer('Посещение уже подтверждено. Повторного начисления нет.' if result.already_confirmed
                         else f'✅ Посещение подтверждено. Начислено баллов: {result.points_awarded}.')
