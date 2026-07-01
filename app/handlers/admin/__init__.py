from aiogram import Router

from app.handlers.admin import task_review
from app.handlers.admin import addons
from app.handlers.admin import panel

router = Router(name="admin_root")
router.include_router(task_review.router)
router.include_router(addons.router)
router.include_router(panel.router)

__all__ = ["router"]
