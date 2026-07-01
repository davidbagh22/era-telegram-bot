from aiogram import Router

from app.handlers.admin import dashboard_start, user_reward_direct, reward_exchange, event_flow, dashboard_quick, task_review_clean, task_review, project_team_review, addons, panel

router = Router(name="admin_root")
router.include_router(dashboard_start.router)
router.include_router(user_reward_direct.router)
router.include_router(reward_exchange.router)
router.include_router(event_flow.router)
router.include_router(dashboard_quick.router)
router.include_router(task_review_clean.router)
router.include_router(task_review.router)
router.include_router(project_team_review.router)
router.include_router(addons.router)
router.include_router(panel.router)

__all__ = ["router"]
