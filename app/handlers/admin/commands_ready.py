from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Settings
from app.database.models import User
from app.handlers.admin.management_ready import _guard
from app.keyboards.participant import open_app_button
from app.utils import texts

router = Router(name="admin_commands_ready")
router.message.filter(F.chat.type == "private")

# These six /admin_* shortcuts used to jump straight into a specific branch
# of the bot-native admin menu tree (people, events, projects, partners,
# tasks, rights). That whole tree was removed from live routing — Admin
# Mode in the Mini App covers all of it now (2026-08 master spec,
# docs/SYSTEM_FLOW_MATRIX.md). Kept live only as compatibility redirects,
# not deleted, for anyone who still types one of the old shortcuts.


async def _redirect(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(settings.effective_miniapp_url))


@router.message(Command("admin_users"))
async def admin_users_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_events"))
async def admin_events_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_projects"))
async def admin_projects_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_partners"))
async def admin_partners_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_tasks"))
async def admin_tasks_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)


@router.message(Command("admin_rights"))
async def admin_rights_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await _redirect(message, user, settings, state)
