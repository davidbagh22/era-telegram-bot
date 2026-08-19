from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.config import Settings
from app.keyboards.participant import open_app_button
from app.utils import texts
from app.utils.deep_links import miniapp_admin_url

router = Router(name="admin_legacy_action_bridge")

# These callback values still exist in historical bot keyboards/messages. The
# full operational surface now lives in Admin Mini App, so stale buttons must
# remain useful without reviving a second bot-native admin implementation.
LEGACY_ADMIN_ACTIONS = {
    "admin:maintenance",
    "admin:settings",
    "admin:broadcast",
    "admin:greetings",
    "admin:questions",
    "admin:office:new",
    "admin:permissions",
    "admin:points",
    "admin:portfolio",
    "admin:proposals",
    "admin:rewards",
    "admin:menu:activity",
    "admin:participants",
    "admin:task:new",
    "admin:applications",
    "admin:menu:users",
    "admin:people:ages",
    "admin:people:cities",
    "admin:people:directions",
    "admin:people:list:all:0:0",
    "admin:people:roles",
    "admin:people:search",
}


@router.callback_query(F.data.in_(LEGACY_ADMIN_ACTIONS))
async def open_admin_miniapp(call: CallbackQuery, settings: Settings) -> None:
    """Give every retained legacy button one deterministic safe destination."""
    await call.answer()
    url = miniapp_admin_url(settings.effective_miniapp_url)
    await call.message.answer(
        texts.ADMIN_PANEL_MOVED,
        reply_markup=open_app_button(url),
    )
