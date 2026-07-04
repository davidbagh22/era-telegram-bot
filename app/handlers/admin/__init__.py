from aiogram import F, Router
from app.handlers.admin import management_v3, dashboard_block_a, task_review_block2, user_profile_block3_safe, projects_block5_list, projects_block5_decision, projects_block5_team, events_block6, event_activities_block7, panel

router = Router(name="admin_root")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.include_router(management_v3.router)
router.include_router(dashboard_block_a.router)
router.include_router(task_review_block2.router)
router.include_router(user_profile_block3_safe.router)
router.include_router(projects_block5_list.router)
router.include_router(projects_block5_decision.router)
router.include_router(projects_block5_team.router)
router.include_router(events_block6.router)
router.include_router(event_activities_block7.router)
router.include_router(panel.router)

__all__ = ["router"]
