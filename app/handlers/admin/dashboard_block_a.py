from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.models import User
from app.keyboards.participant import open_app_button
from app.services.admin_dashboard_service import has_dashboard_access
from app.utils import texts

router = Router(name="admin_dashboard_block_a")


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not has_dashboard_access(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_dashboard(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    # The bot-native admin dashboard (metrics + full menu tree) was removed
    # from live routing — Admin Mode in the Mini App is the only admin
    # surface now (2026-08 master spec, docs/SYSTEM_FLOW_MATRIX.md). Kept
    # live only as a compatibility redirect for anyone who still types
    # /admin or has the old "⚙️ Управление" reply-keyboard button cached.
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(settings.effective_miniapp_url))


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(settings.effective_miniapp_url))


# admin:attention (the "🧭 Что где ждёт" breakdown) was only reachable from
# the removed dashboard menu keyboard below — it has no other entry point
# (verified: `rg '"admin:attention"'` across app/ only ever matched this
# router's own decorator), so it's been dropped rather than left orphaned.
# The Mini App's AdminOverviewScreen already covers this with clickable
# "Требует внимания" items that navigate straight to the object.
