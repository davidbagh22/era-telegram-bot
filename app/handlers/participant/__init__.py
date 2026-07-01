from aiogram import Router
from app.handlers.participant import navigation, task_block2, task_flow, about, cabinet, departments, events, growth, projects, questions
router = Router(name="participant")
router.include_routers(navigation.router, task_block2.router, task_flow.router, cabinet.router, events.router, projects.router, departments.router, questions.router, growth.router, about.router)
