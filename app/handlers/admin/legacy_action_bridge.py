from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.keyboards.participant import open_app_button
from app.utils import texts
from app.utils.deep_links import miniapp_admin_url

router = Router(name="admin_legacy_action_bridge")


def _admin_url(settings: Settings) -> str:
    return miniapp_admin_url(settings.effective_miniapp_url)


@router.message(Command("panel"))
@router.message(Command("admin"))
async def panel_launcher(message: Message, settings: Settings, state: FSMContext) -> None:
    """Compatibility launcher: old admin commands open the one Command Center."""
    await state.clear()
    await message.answer(
        texts.ADMIN_PANEL_MOVED,
        reply_markup=open_app_button(_admin_url(settings)),
    )


@router.callback_query(F.data.startswith("admin:"))
async def open_admin_miniapp(call: CallbackQuery, settings: Settings) -> None:
    """Every historical admin callback has one safe deterministic destination."""
    await call.answer()
    await call.message.answer(
        texts.ADMIN_PANEL_MOVED,
        reply_markup=open_app_button(_admin_url(settings)),
    )
