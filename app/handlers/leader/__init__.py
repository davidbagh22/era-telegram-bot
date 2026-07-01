from aiogram import Router
from app.handlers.leader import open_tasks, panel, task_deadline_buttons
router = Router(name="leader_root")
router.include_router(open_tasks.router)
router.include_router(task_deadline_buttons.router)
router.include_router(panel.router)
