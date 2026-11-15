"""Private, opt-in anniversary RSVP, routed before generic onboarding."""
import csv
import io

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services import anniversary_registration_service as rsvp
from app.services.authorization_service import is_full_admin
from app.services.notification_service import safe_answer_document
from app.utils.constants import RegistrationStatus

router = Router(name="anniversary")


class AnniversaryStates(StatesGroup):
    first_name = State()
    last_name = State()
    organization = State()
    confirm = State()


def keyboard(label: str, action: str):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=f"anniversary:{action}")]])


def blocked(user) -> bool:
    return user is not None and (user.is_blocked or user.is_archived)


def summary(data: dict) -> str:
    return f"Имя: {data['first_name']}\nФамилия: {data['last_name']}\nОрганизация: {data['organization']}"


@router.message(StateFilter("*"), CommandStart(), F.chat.type == "private", F.text.regexp(r"^/start(?:@\w+)?\s+anniversary2026\s*$"))
async def entry(message: Message, state: FSMContext, session, user):
    if blocked(user):
        await message.answer("Регистрация недоступна. Свяжитесь с организаторами.")
        return
    await state.clear()
    existing = await rsvp.get_registration(session, message.from_user.id)
    if existing:
        await message.answer(f"Вы уже зарегистрированы!\n\n{rsvp.DETAILS}\n\n{summary(existing)}", parse_mode=None)
        return
    try:
        if await _check_existing_event(session, user, message.from_user.id):
            await _show_result(message, state)
            return
    except ValueError as exc:
        await message.answer(_registration_error(exc))
        return
    if rsvp.registration_open():
        if len(rsvp.profile_defaults(user)) == 3:
            await message.answer(f"{rsvp.DETAILS}\n\n{rsvp.CONSENT}",
                                 reply_markup=keyboard("Зарегистрироваться", "quick"), parse_mode=None)
        else:
            await message.answer(f"{rsvp.DETAILS}\n\nДля регистрации нужны имя, фамилия и организация. "
                                 "Если вы приходите лично, можно указать «Без организации».",
                                 reply_markup=keyboard("Зарегистрироваться на годовщину", "begin"), parse_mode=None)
    else:
        await message.answer("Регистрация на годовщину завершена.")


async def _start_form(message, state, defaults):
    await state.clear()
    await state.update_data(**defaults)
    if "first_name" not in defaults:
        await state.set_state(AnniversaryStates.first_name)
        await message.answer("Как вас зовут? Напишите имя.\nДля отмены — /cancel.")
    elif "last_name" not in defaults:
        await state.set_state(AnniversaryStates.last_name)
        await message.answer("Ваша фамилия?")
    else:
        await state.set_state(AnniversaryStates.organization)
        await message.answer("Какую организацию или учебное заведение вы представляете?\nЕсли приходите лично, напишите «Без организации».")


async def _check_existing_event(session, user, telegram_id):
    event = await rsvp.find_event(session)
    if event is None:
        return False
    return await rsvp.check_event_registration(session, event, telegram_id, user)


def _registration_error(exc):
    if str(exc) == "full":
        return "Свободных мест на годовщину больше нет."
    if str(exc) in {"event_not_found", "anniversary_registration_closed"}:
        return "Регистрация на годовщину закрыта."
    if str(exc) == "anniversary_waitlisted":
        return "Вы в листе ожидания на годовщину."
    return str(exc)


async def _show_result(message, state, data=None):
    await state.clear()
    headline = "Вы зарегистрированы на годовщину ЭРЫ!" if data else "Вы уже зарегистрированы!"
    details = f"\n\n{summary(data)}\n\nДо встречи!" if data else ""
    await message.answer(f"{headline}\n\n{rsvp.DETAILS}{details}", parse_mode=None)


@router.message(StateFilter("*"), F.chat.type == "private", F.text == rsvp.MENU_BUTTON)
async def menu_registration(message: Message, state: FSMContext, session, user):
    if blocked(user):
        await message.answer("Регистрация недоступна.")
        return
    telegram_id = message.from_user.id
    event = await rsvp.featured_event(session)
    if event is None:
        await message.answer("Регистрация на годовщину недоступна.")
        return
    defaults = rsvp.profile_defaults(user)
    try:
        if await rsvp.check_event_registration(session, event, telegram_id, user):
            await _show_result(message, state)
        elif len(defaults) == 3:
            await _show_result(message, state, await rsvp.register(session, telegram_id, defaults))
        else:
            await _start_form(message, state, defaults)
    except ValueError as exc:
        await message.answer(_registration_error(exc), parse_mode=None)


@router.callback_query(StateFilter("*"), F.message.chat.type == "private", F.data.in_({"anniversary:begin", "anniversary:quick"}))
async def begin(call: CallbackQuery, state: FSMContext, session, user):
    if blocked(user) or not rsvp.registration_open():
        await call.answer("Регистрация недоступна.", show_alert=True)
        return
    try:
        already_registered = (
            await rsvp.get_registration(session, call.from_user.id)
            or await _check_existing_event(session, user, call.from_user.id)
        )
    except ValueError as exc:
        await call.answer(_registration_error(exc), show_alert=True)
        return
    if already_registered:
        await call.answer("Вы уже зарегистрированы!", show_alert=True)
        return
    defaults = rsvp.profile_defaults(user)
    await call.answer()
    if len(defaults) == 3:
        if call.data == "anniversary:quick":
            try:
                data = await rsvp.register(session, call.from_user.id, defaults)
            except ValueError as exc:
                await call.message.answer(str(exc), parse_mode=None)
                return
            await _show_result(call.message, state, data)
        else:
            await state.clear()
            await state.update_data(**defaults)
            await state.set_state(AnniversaryStates.confirm)
            await _send_confirmation(call.message, defaults)
    else:
        await _start_form(call.message, state, defaults)


async def _send_confirmation(message, data):
    await message.answer(f"Проверьте данные:\n\n{summary(data)}\n\n"
                         f"{rsvp.CONSENT}\nДля отмены — /cancel.",
                         reply_markup=keyboard("Зарегистрироваться", "save"), parse_mode=None)


@router.message(StateFilter(AnniversaryStates.first_name, AnniversaryStates.last_name, AnniversaryStates.organization), F.chat.type == "private", ~F.text.startswith("/"), ~F.text.in_({"Отмена", "отмена", "❌ Отмена", "Отменить", "отменить"}))
async def field(message: Message, state: FSMContext, user):
    if blocked(user) or not rsvp.registration_open():
        await state.clear()
        await message.answer("Регистрация недоступна.")
        return
    current = await state.get_state()
    is_org = current == AnniversaryStates.organization.state
    try:
        value = rsvp.clean_field(message.text, name=not is_org)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    key = current.rsplit(":", 1)[1]
    await state.update_data(**{key: value})
    data = await state.get_data()
    if "last_name" not in data:
        await state.set_state(AnniversaryStates.last_name)
        await message.answer("Ваша фамилия?")
    elif "organization" not in data:
        await state.set_state(AnniversaryStates.organization)
        await message.answer("Какую организацию или учебное заведение вы представляете?\nЕсли приходите лично, напишите «Без организации».")
    else:
        await state.set_state(AnniversaryStates.confirm)
        await _send_confirmation(message, data)


@router.callback_query(AnniversaryStates.confirm, F.message.chat.type == "private", F.data == "anniversary:save")
async def save(call: CallbackQuery, state: FSMContext, session, user):
    if blocked(user):
        await call.answer("Регистрация недоступна.", show_alert=True)
        return
    await call.answer()
    try:
        if await _check_existing_event(session, user, call.from_user.id):
            await _show_result(call.message, state)
            return
        data = await rsvp.register(session, call.from_user.id, await state.get_data())
    except ValueError as exc:
        await call.message.answer(_registration_error(exc), parse_mode=None)
        return
    await _show_result(call.message, state, data)


@router.callback_query(F.message.chat.type == "private", F.data == "anniversary:save")
async def expired_confirmation(call: CallbackQuery, session, user):
    if not blocked(user):
        legacy_status = await rsvp.legacy_registration_status(session, await rsvp.find_event(session), user)
        if await rsvp.get_registration(session, call.from_user.id) or legacy_status in rsvp.ACTIVE_REGISTRATION_STATUSES:
            await call.answer("Вы уже зарегистрированы!", show_alert=True)
            return
        if legacy_status == RegistrationStatus.WAITLIST:
            await call.answer("Вы в листе ожидания на годовщину.", show_alert=True)
            return
    await call.answer("Откройте приглашение заново, чтобы проверить регистрацию.", show_alert=True)


def csv_cell(value) -> str:
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.message(Command("anniversary_guests"), F.chat.type == "private")
async def export_guests(message: Message, session, user, settings):
    if not is_full_admin(user, settings, message.from_user.id):
        await message.answer("Список гостей доступен только администратору.")
        return
    values = await rsvp.roster(session)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Имя", "Фамилия", "Организация", "Telegram ID", "Дата регистрации"])
    for row in values:
        writer.writerow([csv_cell(row.get(key, "")) for key in ("first_name", "last_name", "organization", "telegram_id", "registered_at")])
    await safe_answer_document(message, BufferedInputFile(output.getvalue().encode("utf-8-sig"), filename="ERA_anniversary_2026_guests.csv"),
                                  caption=f"Зарегистрировано гостей: {len(values)}")
