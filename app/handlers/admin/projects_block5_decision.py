from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.services.project_workspace_service import can_review_projects
from app.services.project_workflow_service import decide_project
from app.utils import texts
from app.utils.constants import ProjectStatus
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
    if not await can_review_projects(session, user, settings):
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
    await state.set_state(ProjectDecisionStates.comment)
    await state.update_data(project_decision_action=action, project_decision_id=int(parts[4]))
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
    action = data["project_decision_action"]
    result = await decide_project(session, project, action=action, comment=comment, actor=user)
    notice = result.notice
    author = await session.get(User, project.author_id)
    if author:
        rows = []
        if project.status == ProjectStatus.APPROVED:
            rows.append([InlineKeyboardButton(text="📅 Оформить мероприятие", callback_data=f"project:event:{project.id}")])
            rows.append([InlineKeyboardButton(text="🔍 Найти команду", callback_data=f"project:team:{project.id}")])
        await safe_send(bot, author.telegram_id, f"💡 {notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{comment}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await state.clear()
    await message.answer("Решение сохранено и отправлено автору")
