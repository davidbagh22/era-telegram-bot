from aiogram import F, Router

from app.handlers.admin import (
    analytics_filters,
    commands_ready,
    version_command,
    dashboard_block_a,
    task_review_block2,
    rights_block6,
    rights_block6_block_menu,
    user_profile_block3_safe,
    projects_block5_list,
    projects_block5_decision,
    projects_block5_team,
    events_block6,
    event_registration_block14,
    event_activities_block7,
    auction_block17,
    partner_offers_block16,
    partners_admin,
    approval_bonus_fix,
    chat_binding_stability,
    offices_management,
    legacy_action_bridge,
)
from app.middlewares.admin_bot_access import AdminBotAccessFilter

router = Router(name="admin_root")

# Root filters are intentionally used here instead of an outer middleware.
# A middleware on admin_root runs before child-handler matching and would
# intercept every private participant callback because this router is ordered
# before participant_router. A false root filter safely skips this router and
# lets the update continue to its real owner while keeping all legacy admin
# handlers inaccessible to non-admin users.
router.message.filter(F.chat.type == "private", AdminBotAccessFilter())
router.callback_query.filter(
    F.message.chat.type == "private",
    AdminBotAccessFilter(),
)

# Keep one bot-native owner per operational callback. Analytics uses the
# current filtered implementation; event-activity review uses block7. The old
# surveys_analytics / management_ready / event-activity duplicate routers stay
# in history for migration reference but are deliberately not mounted.
router.include_router(analytics_filters.router)
router.include_router(commands_ready.router)
router.include_router(version_command.router)
router.include_router(dashboard_block_a.router)
router.include_router(task_review_block2.router)
router.include_router(rights_block6.router)
router.include_router(rights_block6_block_menu.router)
router.include_router(user_profile_block3_safe.router)
router.include_router(projects_block5_list.router)
router.include_router(projects_block5_decision.router)
router.include_router(projects_block5_team.router)
router.include_router(events_block6.router)
router.include_router(event_registration_block14.router)
router.include_router(event_activities_block7.router)
router.include_router(auction_block17.router)
router.include_router(partner_offers_block16.router)
router.include_router(partners_admin.router)
router.include_router(approval_bonus_fix.router)
router.include_router(chat_binding_stability.router)
router.include_router(offices_management.router)
# Last on purpose: only retained legacy callbacks without a current owner reach
# this bridge, which opens the authoritative Admin Mini App.
router.include_router(legacy_action_bridge.router)

__all__ = ["router"]
