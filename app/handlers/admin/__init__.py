from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.types import CallbackQuery
from app.handlers.admin import (
    dashboard_block_a,
    applications_flow,
    task_review_block2,
    user_profile_block3_safe,
    projects_block5_list,
    projects_block5_decision,
    projects_block5_team,
    events_block6,
    event_activities_block7,
    questions_flow,
    panel,
)

ADMIN_TOP_LEVEL_CALLBACKS = {
    "admin:panel",
    "admin:attention",
    "admin:applications",
    "admin:participants",
    "admin:roles",
    "admin:departments",
    "admin:projects",
    "admin:events",
    "admin:event_activities",
    "admin:tasks",
    "admin:questions",
    "admin:broadcast",
    "admin:greetings",
    "admin:points",
    "admin:rewards",
    "admin:auctions",
    "admin:portfolio",
    "admin:proposals",
    "admin:offices",
    "admin:analytics",
    "admin:settings",
    "admin:maintenance",
}


class AdminNavigationResetMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        callback = event.data or ""
        if callback.startswith("admin:menu:") or callback in ADMIN_TOP_LEVEL_CALLBACKS:
            state = data.get("state")
            if state is not None:
                await state.clear()
        return await handler(event, data)


router = Router(name="admin_root")\nrouter.message.filter(F.chat.type == "private")\nrouter.callback_query.filter(F.message.chat.type == "private")
router.callback_query.middleware(AdminNavigationResetMiddleware())
router.include_router(dashboard_block_a.router)
router.include_router(applications_flow.router)
router.include_router(task_review_block2.router)
router.include_router(user_profile_block3_safe.router)
router.include_router(projects_block5_list.router)
router.include_router(projects_block5_decision.router)
router.include_router(projects_block5_team.router)
router.include_router(events_block6.router)
router.include_router(event_activities_block7.router)
router.include_router(questions_flow.router)
router.include_router(panel.router)

__all__ = ["router"]
