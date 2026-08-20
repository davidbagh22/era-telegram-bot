from aiogram import F, Router
from app.handlers.leader import (
    open_tasks,
    events_block6,
    event_activities_block7,
    task_deadline_buttons,
    legacy_bridge,
)

router = Router(name="leader_root")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.include_router(open_tasks.router)
router.include_router(task_deadline_buttons.router)
router.include_router(events_block6.router)
router.include_router(event_activities_block7.router)
# Last: legacy leader callbacks that no current workflow owns open Leader Mini App.
router.include_router(legacy_bridge.router)
