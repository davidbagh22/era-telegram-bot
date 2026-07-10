from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers.participant.navigation import _approved, _send_event_list, _send_main_menu, _send_personal_cabinet
from app.keyboards.participant import about_keyboard, contact_keyboard, profile_sections_keyboard
from app.repositories.users import user_stats
from app.services.points_service import total_points
from app.utils import texts
from app.utils.constants import STATUS_LABELS

router = Router(name="participant_commands_ready")


def _age_from_birth_date(birth_date) -> int | None:
    if not birth_date:
        return None
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def _my_data_text(user: User, stats: dict[str, int]) -> str:
    birth_date = getattr(user, "birth_date", None)
    birth_date_text = birth_date.strftime("%d.%m.%Y") if birth_date else "не указана"
    age = _age_from_birth_date(birth_date) if birth_date else user.age
    directions = ", ".join(item.direction.name for item in user.directions) or "не выбраны"
    status = STATUS_LABELS.get(user.participation_status, user.participation_status)
    return f"""⚙️ Мои данные

Имя: {user.first_name}
Фамилия: {user.last_name or 'не указана'}
Дата рождения: {birth_date_text}
Возраст: {age or 'не указан'}
Город: {user.city or 'не указан'}
Телефон: {user.phone or 'не указан'}
Email: {user.email or 'не указан'}
Статус: {status}
Баланс: {stats['points']} баллов
Направления: {directions}"""


@router.message(Command("menu"), F.chat.type == "private")
async def menu_command(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    await _send_main_menu(message, user)


@router.message(Command("profile"), F.chat.type == "private")
async def profile_command(message: Message, user: User | None, session: AsyncSession, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_personal_cabinet(message, user, session, settings)


@router.message(Command("data"), F.chat.type == "private")
async def data_command(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    stats = await user_stats(session, user.id)
    await message.answer(_my_data_text(user, stats), reply_markup=profile_sections_keyboard())


@router.message(Command("events"), F.chat.type == "private")
async def events_command(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.message(Command("opportunities"), F.chat.type == "private")
async def opportunities_command(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await message.answer(
        f"⭐ Возможности\n\nВаш баланс: {balance} баллов\n\n"
        "Здесь доступны партнёры, каталог возможностей, аукционы, награды и специальные форматы ЭРА.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤝 Партнёры", callback_data="partners:list")],
            [InlineKeyboardButton(text="⭐ Каталог возможностей", callback_data="rewards:menu")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]),
    )


@router.message(Command("points"), F.chat.type == "private")
async def points_command(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await message.answer(
        f"🏆 Баллы\n\nВаш баланс: {balance} баллов\n\n"
        "Баллы начисляются за подтверждённое участие, задачи, проекты и реальный вклад в ЭРА.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ История баллов", callback_data="cabinet:points")],
            [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="cabinet:rating")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]),
    )


@router.message(Command("contact"), F.chat.type == "private")
async def contact_command(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer("💬 Связь\n\nВыберите, что Вам нужно.", reply_markup=contact_keyboard())


@router.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.ABOUT_BOT, reply_markup=about_keyboard())
