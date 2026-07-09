from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.database.models import User
from app.handlers.admin.management_ready import _guard
from app.keyboards.admin import admin_activity_keyboard, admin_panel_keyboard, admin_users_keyboard

router = Router(name="admin_commands_ready")
router.message.filter(F.chat.type == "private")


@router.message(Command("admin_users"))
async def admin_users_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer("👥 Участники\n\nЗаявки, списки, роли, статусы и фильтры участников.", reply_markup=admin_users_keyboard())


@router.message(Command("admin_events"))
async def admin_events_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer("📅 События\n\nМероприятия, проекты, активности после событий, задания и конкурсы.", reply_markup=admin_activity_keyboard())


@router.message(Command("admin_projects"))
async def admin_projects_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(
        "💡 Проекты\n\nОткройте список проектов, проверку заявок и решения по площадкам.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💡 Проекты", callback_data="admin:projects")],
            [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
        ]),
    )


@router.message(Command("admin_partners"))
async def admin_partners_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(
        "🤝 Партнёры и база организаций\n\nЗдесь можно работать с партнёрами, организациями и контактами.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤝 Партнёры", callback_data="admin:partners")],
            [InlineKeyboardButton(text="🏢 База организаций", callback_data="admin:contacts")],
            [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
        ]),
    )


@router.message(Command("admin_tasks"))
async def admin_tasks_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(
        "✅ Задачи\n\nСоздание, проверка и управление заданиями и конкурсами.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Задания и конкурсы", callback_data="admin:tasks")],
            [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
        ]),
    )


@router.message(Command("admin_rights"))
async def admin_rights_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(
        "🔐 Должности и права\n\nНазначения, должности, технические права и доступы.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Должности и права", callback_data="admin:offices")],
            [InlineKeyboardButton(text="👤 Найти участника", callback_data="admin:people:search")],
            [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
        ]),
    )


@router.message(Command("panel"))
async def panel_alias_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer("⚙️ Панель управления ЭРА", reply_markup=admin_panel_keyboard())
