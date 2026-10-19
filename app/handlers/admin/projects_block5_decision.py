from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.project_workspace_service import can_review_any_projects, can_review_projects
from app.services.project_workflow_service import (
    PROJECT_DECISION_ACTIONS, ProjectDecisionConflict, decide_project, project_review_version,
)
from app.utils import texts
from app.utils.validators import clean_text

router = Router(name="admin_projects_block5_decision")


class ProjectDecisionStates(StatesGroup):
    comment = State()


async def _guard(
    event: CallbackQuery | Message, user: User | None, settings: Settings, session: AsyncSession
) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    if not await can_review_any_projects(session, user, settings):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.callback_query(F.data.startswith("admin:project:review:"))
async def decision_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings, session):
        return
    parts = call.data.split(":")
    if len(parts) != 5 or not parts[4].isdigit():
        return
    action = parts[3]
    project = await session.get(Project, int(parts[4]))
    if action not in PROJECT_DECISION_ACTIONS or project is None:
        await call.message.answer("Проект или действие не найдены")
        return
    if not await can_review_projects(session, user, settings, project):
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.set_state(ProjectDecisionStates.comment)
    await state.update_data(project_decision_action=action, project_decision_id=int(parts[4]),
                            project_decision_version=project_review_version(project))
    prompts = {
        "initial_accept": "Комментарий автору: что принято в работу и что уточняем дальше?",
        "venue_approve": "Комментарий автору: проект одобрен, что делать дальше?",
        "revise": "Что нужно доработать в проекте?",
        "reject": "Почему проект отклонён?",
        "postpone": "Почему проект переносится и когда к нему вернуться?",
    }
    await call.message.answer(prompts.get(action, "Комментарий автору"))


@router.message(ProjectDecisionStates.comment)
async def decision_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings, session):
        return
    comment = clean_text(message.text or "", 2000)
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    data = await state.get_data()
    project = await session.get(Project, int(data["project_decision_id"]))
    if not project:
        await state.clear()
        await message.answer("Проект не найден")
        return
    if not await can_review_projects(session, user, settings, project):
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    action = data["project_decision_action"]
    try:
        await decide_project(session, project, action=action, comment=comment, actor=user,
                                      settings=settings, expected_version=data.get("project_decision_version", ""))
    except (ProjectDecisionConflict, PermissionError):
        await state.clear()
        await message.answer("Проект изменился или уже рассмотрен. Откройте свежую карточку проекта.")
        return
    await session.commit()
    await state.clear()
    await message.answer("Решение сохранено. Уведомление автору поставлено в очередь.")
