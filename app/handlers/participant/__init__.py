from aiogram import Router

from app.handlers.participant import (
    navigation,
    task_lists_addon,
    task_review_addon,
    task_flow,
    project_control_addon,
    addons,
    about,
    cabinet,
    departments,
    events,
    growth,
    projects,
    questions,
)

router = Router(name="participant")
router.include_routers(
    navigation.router,
    task_lists_addon.router,
    task_review_addon.router,
    task_flow.router,
    project_control_addon.router,
    addons.router,
    cabinet.router,
    events.router,
    projects.router,
    departments.router,
    questions.router,
    growth.router,
    about.router,
)
