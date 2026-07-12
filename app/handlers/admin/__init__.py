from aiogram import F, Router
from app.handlers.admin import (
    management_ready,
    commands_ready,
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
    event_activities_stability,
    event_activities_block15,
    event_activities_block7,
    auction_block17,
    partner_offers_block16,
    partners_admin,
    approval_bonus_fix,
    chat_binding_stability,
    panel,
)

router = Router(name="admin_root")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.include_router(management_ready.router)
router.include_router(commands_ready.router)
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
router.include_router(event_activities_stability.router)
router.include_router(event_activities_block15.router)
router.include_router(event_activities_block7.router)
router.include_router(auction_block17.router)
router.include_router(partner_offers_block16.router)
router.include_router(partners_admin.router)
router.include_router(approval_bonus_fix.router)
router.include_router(chat_binding_stability.router)
router.include_router(panel.router)

__all__ = ["router"]
