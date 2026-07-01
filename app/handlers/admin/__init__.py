from aiogram import Router

from app.handlers.admin import dashboard_start, dashboard_quick, task_review_clean, task_review, addons, panel

router = Router(name="admin_root")
router.include_router(dashboard_start.router)
router.include_router(dashboard_quick.router)
router.include_router(task_review_clean.router)
router.include_router(task_review.router)
router.include_router(addons.router)
router.include_router(panel.router)

__all__ = ["router"]
