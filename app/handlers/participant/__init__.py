from aiogram import Router

from app.handlers.participant import (
    navigation,
    achievements_block4,
    task_block2,
    task_flow,
    projects_block5,
    event_activities_block7,
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
    achievements_block4.router,
    task_block2.router,
    task_flow.router,
    projects_block5.router,
    event_activities_block7.router,
    cabinet.router,
    events.router,
    projects.router,
    departments.router,
    questions.router,
    growth.router,
    about.router,
)
