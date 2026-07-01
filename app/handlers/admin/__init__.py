from aiogram import Router
from app.handlers.admin import task_review_block2, user_profile_block3_safe, panel

router = Router(name="admin_root")
router.include_router(task_review_block2.router)
router.include_router(user_profile_block3_safe.router)
router.include_router(panel.router)

__all__ = ["router"]
