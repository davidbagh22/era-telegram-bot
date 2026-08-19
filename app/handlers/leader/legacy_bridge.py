from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.keyboards.participant import open_app_button
from app.utils import texts
from app.utils.deep_links import miniapp_leader_url

router = Router(name="leader_legacy_bridge")


def _leader_url(settings: Settings) -> str:
    return miniapp_leader_url(settings.effective_miniapp_url)


@router.message(Command("leader"))
@router.message(F.text == "🧭 Панель лидера")
async def leader_launcher(message: Message, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        texts.LEADER_PANEL_MOVED,
        reply_markup=open_app_button(_leader_url(settings)),
    )


@router.callback_query(F.data.startswith("leader:"))
async def legacy_leader_action(call: CallbackQuery, settings: Settings) -> None:
    """Fallback for old leader buttons after current handlers had first chance."""
    await call.answer()
    await call.message.answer(
        texts.LEADER_PANEL_MOVED,
        reply_markup=open_app_button(_leader_url(settings)),
    )
