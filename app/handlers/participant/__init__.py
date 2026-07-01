from aiogram import Router

from app.handlers.participant import (
    navigation,
    task_flow,
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
    task_flow.router,
    addons.router,
    cabinet.router,
    events.router,
    projects.router,
    departments.router,
    questions.router,
    growth.router,
    about.router,
)
