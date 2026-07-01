from aiogram import Router

from app.handlers.leader import addons, open_tasks, panel, task_deadline_buttons

router = Router(name="leader_root")
router.include_router(open_tasks.router)
router.include_router(task_deadline_buttons.router)
router.include_router(addons.router)
router.include_router(panel.router)

__all__ = ["router"]
