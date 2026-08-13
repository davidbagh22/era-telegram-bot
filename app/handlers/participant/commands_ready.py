from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import Settings
from app.database.models import User
from app.handlers.participant.navigation import _approved, _send_main_menu
from app.keyboards.participant import about_keyboard, contact_keyboard, open_app_button
from app.utils import texts
from app.utils.deep_links import miniapp_events_url, miniapp_opportunities_url, miniapp_profile_url

router = Router(name="participant_commands_ready")

# /profile, /data, /events, /opportunities, /points used to each open their
# own bot-native menu (personal cabinet, a hand-rolled "my data" card, an
# events list, partner/rewards menus, a points/rating menu) — all of it now
# duplicates a Mini App screen. Per the 2026-08 master spec (section 25),
# these are kept live as compatibility redirects, deep-linked to the
# specific screen rather than just the Mini App's home, not deleted.
# /menu, /contact, and /help are unaffected: /menu is itself the Mini-App
# entry point, and /contact ("support") + /help are explicitly allowed to
# stay bot-native (section 19-22).


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
async def help_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.ABOUT_BOT, reply_markup=about_keyboard())
