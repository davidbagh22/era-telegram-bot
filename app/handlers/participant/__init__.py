from aiogram import F, Router

from app.handlers.participant import (
    navigation,
    achievements_block4,
    task_block2,
    projects_block5,
    event_activities_block7,
    event_plans_changed,
    about,
    cabinet,
    departments,
    events,
    growth,
    projects,
    questions,
)

router = Router(name="participant")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.include_routers(
    navigation.router,
    achievements_block4.router,
    task_block2.router,
    projects_block5.router,
    event_activities_block7.router,
    event_plans_changed.router,
    cabinet.router,
    events.router,
    projects.router,
    departments.router,
    questions.router,
    growth.router,
    about.router,
)
