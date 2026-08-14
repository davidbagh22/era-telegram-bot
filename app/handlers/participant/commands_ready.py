from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Settings
from app.database.models import User
from app.handlers.participant.navigation import _approved, _send_main_menu, _send_navigation_guide
from app.keyboards.participant import contact_keyboard, open_app_button
from app.utils import texts
from app.utils.deep_links import (
    miniapp_events_url,
    miniapp_opportunities_url,
    miniapp_profile_url,
    miniapp_tasks_url,
)

router = Router(name="participant_commands_ready")

# /profile, /data, /events, /tasks, /opportunities, /points used to each
# open their own bot-native menu (personal cabinet, a hand-rolled "my
# data" card, an events list, a task menu, partner/rewards menus, a
# points/rating menu) — all of it now duplicates a Mini App screen. Per
# the 2026-08 bot cleanup, these are kept live as compatibility
# redirects, deep-linked to the specific screen rather than just the Mini
# App's home, not deleted. None of them are advertised in the / menu
# anymore (see app/webapp.py's USER_COMMANDS) — only /start,
# /navigation, and /contact are.
# /menu is unaffected: it's itself the Mini-App entry point (not a
# duplicate screen). /help is folded into the same "🧭 Навигация"
# explainer /navigation uses, rather than the old about_keyboard() menu
# of bot-native shortcuts — see _send_navigation_guide.


@router.message(Command("menu"), F.chat.type == "private")
async def menu_command(
    message: Message, user: User | None, state: FSMContext, settings: Settings
) -> None:
    await state.clear()
    await _send_main_menu(message, user, settings)


@router.message(Command("profile"), F.chat.type == "private")
async def profile_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.PROFILE_MOVED,
        reply_markup=open_app_button(miniapp_profile_url(settings.effective_miniapp_url)),
    )


@router.message(Command("data"), F.chat.type == "private")
async def data_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.PROFILE_MOVED,
        reply_markup=open_app_button(miniapp_profile_url(settings.effective_miniapp_url)),
    )


@router.message(Command("events"), F.chat.type == "private")
async def events_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.EVENTS_MOVED,
        reply_markup=open_app_button(miniapp_events_url(settings.effective_miniapp_url)),
    )


@router.message(Command("tasks"), F.chat.type == "private")
async def tasks_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    # Registered before task_reply.py's own /tasks handler in
    # app/handlers/participant/__init__.py's include_routers() order, so
    # this compatibility redirect wins over that file's old bot-native
    # _task_menu() (2026-08 bot cleanup — that handler is now unreachable
    # dead code, kept in place rather than deleted in this pass).
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.TASKS_MOVED,
        reply_markup=open_app_button(miniapp_tasks_url(settings.effective_miniapp_url)),
    )


@router.message(Command("opportunities"), F.chat.type == "private")
async def opportunities_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.OPPORTUNITIES_MOVED,
        reply_markup=open_app_button(miniapp_opportunities_url(settings.effective_miniapp_url)),
    )


@router.message(Command("points"), F.chat.type == "private")
async def points_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.PROFILE_MOVED,
        reply_markup=open_app_button(miniapp_profile_url(settings.effective_miniapp_url)),
    )


@router.message(Command("contact"), F.chat.type == "private")
async def contact_command(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer("💬 Связь\n\nВыберите, что Вам нужно.", reply_markup=contact_keyboard())


@router.message(Command("help"), F.chat.type == "private")
async def help_command(
    message: Message, user: User | None, settings: Settings, state: FSMContext
) -> None:
    # 2026-08 bot cleanup: /help used to open about_keyboard() -- a
    # 6-button bot-native menu (Личный кабинет/Афиша/Задачи/Проекты/
    # Возможности/Связь) duplicating the Mini App. Folded into the same
    # "🧭 Навигация" explainer /navigation uses instead, per the brief's
    # "предпочтительно объединить help в navigation".
    await state.clear()
    await _send_navigation_guide(message, user, settings)
