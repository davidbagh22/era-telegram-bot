from aiogram import Router
from app.handlers.admin import task_review_block2, user_profile_block3_safe, projects_block5_list, projects_block5_decision, projects_block5_team, panel

router = Router(name="admin_root")
router.include_router(task_review_block2.router)
router.include_router(user_profile_block3_safe.router)
router.include_router(projects_block5_list.router)
router.include_router(projects_block5_decision.router)
router.include_router(projects_block5_team.router)
router.include_router(panel.router)

__all__ = ["router"]
