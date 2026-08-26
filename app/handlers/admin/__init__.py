from aiogram import F, Router

from app.handlers.admin import legacy_action_bridge
from app.middlewares.admin_bot_access import AdminBotAccessFilter

router = Router(name="admin_root")

# Admin operations have one authoritative UI: the Admin Mini App. Telegram is
# only a gateway/notification surface. Keep this root filter so historical
# admin callbacks remain inaccessible to ordinary participants, then mount one
# compatibility bridge that redirects stale buttons and commands into the app.
router.message.filter(F.chat.type == "private", AdminBotAccessFilter())
router.callback_query.filter(
    F.message.chat.type == "private",
    AdminBotAccessFilter(),
)

# Legacy operational routers deliberately stay unmounted. Their files remain in
# repository history for migration/reference, but they no longer form a second
# admin system alongside Admin Command Center.
router.include_router(legacy_action_bridge.router)

__all__ = ["router"]
