from aiogram import Router
from app.handlers.admin import task_review_block2, panel

router = Router(name="admin_root")
router.include_router(task_review_block2.router)
router.include_router(panel.router)

__all__ = ["router"]
