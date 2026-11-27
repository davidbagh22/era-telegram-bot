import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.states.event import EventConfirmationStates
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity, EventRegistration, User
from app.keyboards.participant import event_list_keyboard
from app.services import anniversary_registration_service as anniversary
from app.services.event_card import send_event_card
from app.services.event_registration_notice_service import (
    RegistrationNoticeKind,
    deliver_registration_notice,
    enqueue_registration_notice,
)
from app.services.event_owner_export_service import deliver_owner_export, enqueue_owner_export
from app.services.event_registration_policy import registration_is_closed
from app.services.notification_service import safe_answer_document
from app.services.event_registration_service import registration_stats
from app.services.event_service import (
    PUBLIC_EVENT_STATUSES,
    REGISTRATION_ALLOWED_STATUSES,
    published_events,
    register_for_event,
)
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, RegistrationStatus

logger = logging.getLogger(__name__)

router = Router(name="participant_events_stability_block8")


def _event_id_from_callback(data: str | None, prefix: str) -> int | None:
    """Reject stale, malformed and PostgreSQL INTEGER-overflow event IDs."""
    if not data or not data.startswith(prefix):
        return None
    raw = data[len(prefix):]
    if not raw or len(raw) > 10 or not raw.isascii() or not raw.isdecimal():
        return None
    event_id = int(raw)
    return event_id if 0 < event_id <= 2_147_483_647 else None


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _event_keyboard(
    event_id: int,
    *,
    registration_button: str | None,
    leave_button: str | None = None,
    has_activities: bool,
) -> InlineKeyboardMarkup:
    rows = []
    if registration_button is not None:
        rows.append([InlineKeyboardButton(text=registration_button, callback_data=f"event:join:{event_id}")])
    if leave_button is not None:
        rows.append([InlineKeyboardButton(text=leave_button, callback_data=f"event:plans_changed:{event_id}")])
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


def _blocked(user: User | None) -> bool:
    return bool(user and (getattr(user, "is_blocked", False) or getattr(user, "is_archived", False)))


def _entry_gate_keyboard(user: User | None, *, resume_registration: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if user is None:
        if resume_registration:
            rows.append([InlineKeyboardButton(text="Продолжить анкету", callback_data="registration:resume")])
        else:
            rows.append([InlineKeyboardButton(text="Заполнить анкету участника", callback_data="registration:start")])
    else:
        if user.application_status in {ApplicationStatus.REJECTED, ApplicationStatus.NEEDS_INFO}:
            rows.append([InlineKeyboardButton(text="✏️ Дополнить и подать повторно", callback_data="registration:reapply")])
        rows.append([InlineKeyboardButton(text="Проверить статус заявки", callback_data="registration:status")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _entry_gate_text(user: User | None) -> str:
    if user is None:
        return (
            "Чтобы записаться, нужно стать участником ЭРА: заполните короткую анкету. "
            "Мы запомнили это мероприятие — после одобрения заявки бот вернёт вас сюда."
        )
    from app.handlers.registration import application_status_message

    status = user.application_status
    text = application_status_message(status)
    if status == ApplicationStatus.REJECTED:
        return text
    return f"{text}\n\nМероприятие мы запомнили: после одобрения бот пришлёт кнопку для записи."


async def show_public_event_registration_card(
    message: Message,
    user: User | None,
    session: AsyncSession,
    event_id: int | None,
    settings: Settings | None = None,
    telegram_id: int | None = None,
    resume_registration: bool = False,
) -> None:
    """Same published-event card for the afisha and a direct /start URL.

    Approved participants get the full card. Newcomers and applicants see the
    event title/date with the next step (application or its real status) and the
    event is remembered by Telegram ID so the bot can bring them back.
    """
    if _blocked(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    if event_id is None:
        await message.answer("Это мероприятие сейчас недоступно в афише")
        return
    event = await session.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await message.answer("Это мероприятие сейчас недоступно в афише")
        return
    approved = _approved(user)
    actor_telegram_id = getattr(user, "telegram_id", None) or telegram_id
    if approved and actor_telegram_id is not None:
        from app.services import event_entry_service

        await event_entry_service.forget_event(session, actor_telegram_id, event.id)
    if not approved:
        if actor_telegram_id is None:
            await message.answer(texts.APPLICATION_PENDING)
            return
        if not anniversary.is_public_anniversary(event):
            from app.services import event_entry_service

            await event_entry_service.remember_event(session, actor_telegram_id, event.id)
            await send_event_card(
                message,
                event,
                extra_text=_entry_gate_text(user),
                keyboard=_entry_gate_keyboard(user, resume_registration=resume_registration),
            )
            return
    experience = await session.get(EventExperience, event.id)
    if anniversary.is_public_anniversary(event):
        # Guests of the anniversary register without an application, so this
        # branch serves approved members and newcomers alike.
        if approved:
            keyboard = _event_keyboard(event.id, registration_button=None, has_activities=False)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        legacy_status = await anniversary.legacy_registration_status(session, event, user)
        if (
            (actor_telegram_id is not None and await anniversary.get_registration(session, actor_telegram_id))
            or legacy_status in anniversary.ACTIVE_REGISTRATION_STATUSES
        ):
            extra = "Вы зарегистрированы."
        elif legacy_status == RegistrationStatus.WAITLIST:
            extra = "Вы в листе ожидания."
        elif anniversary.event_registration_open(event, experience):
            complete = len(anniversary.profile_defaults(user)) == 3
            extra = anniversary.CONSENT if complete else None
            action = "quick" if complete else "begin"
            keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="Зарегистрироваться", callback_data=f"anniversary:{action}")])
        else:
            extra = "Регистрация закрыта."
        await send_event_card(message, event, extra_text=extra, keyboard=keyboard if keyboard.inline_keyboard else None)
        return
    stats = await registration_stats(session, event)
    registration_open = (
        event.status in REGISTRATION_ALLOWED_STATUSES
        and not registration_is_closed(experience)
    )
    full = event.participant_limit is not None and int(stats["free"]) <= 0
    has_activities = bool(
        await session.scalar(
            select(func.count())
            .select_from(EventActivity)
            .where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True))
        )
    )
    existing = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id,
            EventRegistration.user_id == user.id,
        )
    )
    existing_status = existing.status if existing is not None else None
    extra = None
    registration_button = None
    leave_button = None
    if existing_status == RegistrationStatus.WAITLIST:
        extra = (
            "Вы в листе ожидания. Место ещё не закреплено — "
            "если оно освободится, бот сообщит вам автоматически."
        )
        leave_button = "Покинуть лист ожидания"
    elif existing_status in {
        RegistrationStatus.REGISTERED,
        RegistrationStatus.WILL_COME,
        RegistrationStatus.ATTENDED,
    }:
        extra = "Вы зарегистрированы на это мероприятие."
        if existing_status in {RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME}:
            leave_button = "Отказаться от места"
    elif experience is not None and not experience.registration_required:
        extra = "Для этого мероприятия регистрация не нужна."
    elif not registration_open:
        extra = "Регистрация закрыта, но карточка мероприятия остаётся доступна."
    elif full:
        if experience is not None and experience.waitlist_enabled:
            extra = (
                "Свободных мест нет — можно встать в лист ожидания. "
                "Если место освободится, бот сообщит вам."
            )
            registration_button = "Встать в лист ожидания"
        else:
            extra = "Свободных мест сейчас нет."
    else:
        registration_button = "Зарегистрироваться"
    keyboard = _event_keyboard(
        event.id,
        registration_button=registration_button,
        leave_button=leave_button,
        has_activities=has_activities,
    )
    if settings is not None:
        from app.services.event_attendance_service import attendance_v2_enabled, participant_state
        if attendance_v2_enabled(settings, telegram_id):
            attendance = await participant_state(session, event.id, user.id)
            if attendance.confirmation_open:
                keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="✅ Подтвердить посещение кодом", callback_data=f"event:confirm_code:{event.id}")])
    await send_event_card(
        message,
        event,
        available=str(stats["free"]),
        registered=int(stats["registered"]),
        extra_text=extra,
        keyboard=keyboard,
    )


@router.callback_query(F.data.startswith("event:view:"))
async def event_view(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings | None = None) -> None:
    await call.answer()
    event_id = _event_id_from_callback(call.data, "event:view:")
    await show_public_event_registration_card(
        call.message, user, session, event_id, settings=settings,
        telegram_id=getattr(getattr(call, "from_user", None), "id", None),
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
    event_id = _event_id_from_callback(call.data, "event:calendar:")
    if event_id is None:
        await call.message.answer("Мероприятие недоступно.")
        return
    event = await session.get(Event, event_id)
    registration = await session.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == user.id))
    if event is None or (event.status not in PUBLIC_EVENT_STATUSES and not (
        registration and event.status in {EventStatus.ACTIVE, EventStatus.CANCELLED, EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}
    )):
        await call.message.answer("Мероприятие недоступно.")
        return
    experience = await session.get(EventExperience, event_id)
    await safe_answer_document(call.message,
        BufferedInputFile(build_event_calendar(event, experience, timezone_name=settings.timezone),
                          filename=f"ERA-{event_id}.ics"),
        caption=f"Время события: {settings.timezone}. Импортируйте файл в календарь. После изменения события скачайте актуальную версию.",
    )


async def _drop_join_button(message: Message, event_id: int, leave_button: str | None = None) -> None:
    """Refresh the tapped card so a second tap on a stale join button is impossible.

    Best-effort: Telegram edit failures must never affect the saved registration.
    """
    join_data = f"event:join:{event_id}"
    leave_data = f"event:plans_changed:{event_id}"
    markup = getattr(message, "reply_markup", None)
    if markup is None:
        return
    rows = [
        [button for button in row if button.callback_data != join_data]
        for row in markup.inline_keyboard
    ]
    rows = [row for row in rows if row]
    if leave_button is not None and not any(
        button.callback_data == leave_data for row in rows for button in row
    ):
        rows.insert(0, [InlineKeyboardButton(text=leave_button, callback_data=leave_data)])
    try:
        await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        return


@router.callback_query(F.data.startswith("event:join:"))
async def event_join(
    call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings | None = None
) -> None:
    await call.answer()
    event_id = _event_id_from_callback(call.data, "event:join:")
    if not _approved(user):
        # Stale or forwarded button from a person without an approved profile:
        # route through the same entry card instead of a dead-end notice.
        await show_public_event_registration_card(
            call.message, user, session, event_id,
            telegram_id=getattr(getattr(call, "from_user", None), "id", None),
        )
        return
    if event_id is None:
        await call.message.answer("Это мероприятие сейчас недоступно")
        return
    event = await session.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        await call.message.answer("Это мероприятие сейчас недоступно")
        return
    registration, error = await register_for_event(session, event, user.id)
    if error == "signup_required":
        from app.utils.deep_links import telegram_event_miniapp_url
        username = (await call.bot.get_me()).username
        url = telegram_event_miniapp_url(username, event.id)
        await call.message.answer("Заполните короткую форму участия.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Зарегистрироваться", url=url)]]))
        return
    if error is not None:
        reply = {
            "already": texts.EVENT_ALREADY_REGISTERED,
            "full": texts.EVENT_FULL,
            "closed": "Регистрация на это мероприятие закрыта, но само событие остаётся в афише",
            "registration_not_required": "Для этого мероприятия регистрация не нужна.",
            "anniversary_registration_required": "Откройте карточку годовщины или нажмите «🎟 Зарегистрироваться на годовщину» в главном меню.",
        }[error]
        if error == "already":
            status = await session.scalar(
                select(EventRegistration.status).where(
                    EventRegistration.event_id == event.id, EventRegistration.user_id == user.id
                )
            )
            if status == RegistrationStatus.WAITLIST:
                reply = "Вы уже в листе ожидания на это мероприятие."
        await session.commit()
        await call.message.answer(reply)
        if error in {"already", "full", "closed", "registration_not_required"}:
            await _drop_join_button(call.message, event.id)
        return
    assert registration is not None
    notice = await enqueue_registration_notice(session, registration, user.telegram_id, RegistrationNoticeKind.TELEGRAM)
    owner_export = await enqueue_owner_export(session, settings, registration) if settings is not None else None
    await session.commit()
    await deliver_registration_notice(
        session, notice, lambda _recipient, text, **kwargs: call.message.answer(text, **kwargs)
    )
    if owner_export is not None:
        try:
            await deliver_owner_export(session, owner_export, call.bot.send_document, settings)
        except Exception:
            logger.exception("Registration saved, owner Excel delivery pending event_id=%s", event.id)
    leave = (
        "Покинуть лист ожидания"
        if registration.status == RegistrationStatus.WAITLIST
        else "Отказаться от места"
    )
    await _drop_join_button(call.message, event.id, leave_button=leave)


@router.callback_query(F.data.regexp(r"^event:confirm_code:[0-9]+$"), F.message.chat.type == "private")
async def confirmation_code_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    await call.answer()
    from app.services.event_attendance_service import attendance_v2_enabled, participant_state
    if not _approved(user) or not attendance_v2_enabled(settings, call.from_user.id):
        return
    event_id = _event_id_from_callback(call.data, "event:confirm_code:")
    if event_id is None:
        await call.message.answer('Мероприятие не найдено.')
        return
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
