from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.models import User
from app.keyboards.admin import admin_panel_keyboard
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_dashboard_start")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


@router.message(F.text.in_({"/admin", "⚙️ Управление"}))
async def admin_dashboard(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not _is_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    await state.clear()
    await message.answer("⚙️ Админ-панель ЭРА\n\nСтабильный режим управления включён.", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not _is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.clear()
    await call.message.answer("⚙️ Админ-панель ЭРА\n\nСтабильный режим управления включён.", reply_markup=admin_panel_keyboard())
