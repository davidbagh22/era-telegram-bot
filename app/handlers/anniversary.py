"""Private, opt-in anniversary RSVP, routed before generic onboarding."""
import csv
import io

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database.models import AppSetting
from app.services import anniversary_registration_service as rsvp
from app.services.authorization_service import is_full_admin
from app.services.notification_service import safe_answer_document

router = Router(name="anniversary")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


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


@router.message(StateFilter("*"), CommandStart(), F.text.regexp(r"^/start(?:@\w+)?\s+anniversary2026\s*$"))
async def entry(message: Message, state: FSMContext, session, user):
    if blocked(user):
        await message.answer("Регистрация недоступна. Свяжитесь с организаторами.")
        return
    await state.clear()
    existing = await rsvp.get_registration(session, message.from_user.id)
    if existing:
        await message.answer(f"Вы уже зарегистрированы!\n\n{rsvp.DETAILS}\n\n{summary(existing)}", parse_mode=None)
    elif not rsvp.registration_open():
        await message.answer("Регистрация на годовщину завершена.")
    else:
        await message.answer(f"{rsvp.DETAILS}\n\nПриглашаем отметить первый год ЭРЫ вместе!\n"
                             "Для регистрации нужны имя, фамилия и организация. Если вы приходите лично, можно указать «Без организации».\n\n"
                             "Это регистрация на мероприятие, не заявка на вступление в ЭРА.",
                             reply_markup=keyboard("Зарегистрироваться на годовщину", "begin"), parse_mode=None)


@router.callback_query(StateFilter("*"), F.data == "anniversary:begin")
async def begin(call: CallbackQuery, state: FSMContext, session, user):
    if blocked(user) or not rsvp.registration_open():
        await call.answer("Регистрация недоступна.", show_alert=True)
        return
    if await rsvp.get_registration(session, call.from_user.id):
        await call.answer("Вы уже зарегистрированы!", show_alert=True)
        return
    await state.clear()
    await state.set_state(AnniversaryStates.first_name)
    await call.answer()
    await call.message.answer("Как вас зовут? Напишите имя.\nДля отмены — /cancel.")


@router.message(StateFilter(AnniversaryStates.first_name, AnniversaryStates.last_name, AnniversaryStates.organization), ~F.text.startswith("/"), ~F.text.in_({"Отмена", "отмена", "❌ Отмена", "Отменить", "отменить"}))
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
    if current == AnniversaryStates.first_name.state:
        await state.update_data(first_name=value)
        await state.set_state(AnniversaryStates.last_name)
        await message.answer("Ваша фамилия?")
    elif current == AnniversaryStates.last_name.state:
        await state.update_data(last_name=value)
        await state.set_state(AnniversaryStates.organization)
        await message.answer("Какую организацию или учебное заведение вы представляете?\nЕсли приходите лично, напишите «Без организации».")
    else:
        await state.update_data(organization=value)
        await state.set_state(AnniversaryStates.confirm)
        await message.answer(f"Проверьте данные:\n\n{summary(await state.get_data())}\n\n"
                             "Нажимая «Подтвердить регистрацию», вы соглашаетесь передать имя, фамилию, организацию "
                             "и Telegram ID организаторам ЭРЫ для учёта участников этого мероприятия. "
                             "Эта форма не оформляет подписку на рассылку.\nДля отмены — /cancel.",
                             reply_markup=keyboard("Подтвердить регистрацию", "save"), parse_mode=None)


@router.callback_query(AnniversaryStates.confirm, F.data == "anniversary:save")
async def save(call: CallbackQuery, state: FSMContext, session, user):
    if blocked(user):
        await call.answer("Регистрация недоступна.", show_alert=True)
        return
    await call.answer()
    try:
        data = await rsvp.register(session, call.from_user.id, await state.get_data())
    except ValueError as exc:
        await call.message.answer(str(exc))
        return
    await state.clear()
    await call.message.answer(f"Вы зарегистрированы на годовщину ЭРЫ!\n\n{rsvp.DETAILS}\n\n{summary(data)}\n\nДо встречи!", parse_mode=None)


@router.callback_query(F.data == "anniversary:save")
async def expired_confirmation(call: CallbackQuery):
    await call.answer("Откройте приглашение заново, чтобы проверить регистрацию.", show_alert=True)


def csv_cell(value) -> str:
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.message(Command("anniversary_guests"))
async def export_guests(message: Message, session, user, settings):
    if not is_full_admin(user, settings, message.from_user.id):
        await message.answer("Список гостей доступен только администратору.")
        return
    values = (await session.scalars(select(AppSetting.value).where(AppSetting.key.startswith(rsvp.PREFIX))
                                   .order_by(AppSetting.key))).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Имя", "Фамилия", "Организация", "Telegram ID", "Дата регистрации"])
    for row in values:
        writer.writerow([csv_cell(row.get(key, "")) for key in ("first_name", "last_name", "organization", "telegram_id", "registered_at")])
    await safe_answer_document(message, BufferedInputFile(output.getvalue().encode("utf-8-sig"), filename="ERA_anniversary_2026_guests.csv"),
                                  caption=f"Зарегистрировано гостей: {len(values)}")
