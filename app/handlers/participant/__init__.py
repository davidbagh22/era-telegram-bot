from aiogram import Router

from app.handlers.participant import cabinet, departments, events, projects, questions

router = Router(name="participant")
router.include_routers(
    cabinet.router,
    events.router,
    projects.router,
    departments.router,
    questions.router,
)
