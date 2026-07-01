from aiogram import Router

from app.handlers.admin import addons, panel

router = Router(name="admin_root")
router.include_router(addons.router)
router.include_router(panel.router)

__all__ = ["router"]
