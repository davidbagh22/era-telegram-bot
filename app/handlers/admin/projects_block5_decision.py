from datetime import datetime, timedelta

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points, add_portfolio_item
from app.utils import texts
from app.utils.constants import ProjectStatus, Role
from app.utils.validators import clean_text

router = Router(name="admin_projects_block5_decision")


class ProjectDecisionStates(StatesGroup):
    comment = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and not user.is_archived and any(
            g.is_active and g.permission == "projects.review" for g in (user.permission_grants or [])
        ))
    )


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.callback_query(F.data.startswith("admin:project:review:"))
async def decision_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
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
    if not await _guard(message, user, settings):
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
    old_status = project.status
    project.admin_comment = comment
    if action == "initial_accept":
        project.status = ProjectStatus.VENUE_REVIEW
        project.venue_status = "pending"
        project.venue_comment = comment
        project.venue_reminder_count = 0
        project.venue_remind_at = datetime.now().astimezone() + timedelta(days=1)
        notice = "Проект прошёл первичную проверку и перешёл к следующему этапу"
    elif action == "venue_approve":
        project.status = ProjectStatus.APPROVED
        project.venue_status = "approved"
        project.venue_comment = comment
        project.venue_remind_at = None
        if old_status != ProjectStatus.APPROVED:
            await add_points(session, user_id=project.author_id, points=30, reason=f"Одобренный проект: {project.title}", approved_by=user.id if user else None, related_project_id=project.id)
            await add_portfolio_item(session, user_id=project.author_id, title=f"Автор проекта: {project.title}", item_type="project", description=project.short_description, issued_by=user.id if user else None, related_project_id=project.id)
        notice = "Проект одобрен. Следующий шаг — оформить мероприятие или найти команду"
    elif action == "revise":
        project.status = ProjectStatus.NEEDS_REVISION
        project.venue_remind_at = None
        notice = "Проект возвращён на доработку"
    elif action == "postpone":
        project.status = ProjectStatus.POSTPONED
        project.venue_remind_at = None
        notice = "Проект перенесён"
    else:
        project.status = ProjectStatus.REJECTED
        project.venue_remind_at = None
        notice = "Проект отклонён"
    author = await session.get(User, project.author_id)
    if author:
        rows = []
        if project.status == ProjectStatus.APPROVED:
            rows.append([InlineKeyboardButton(text="📅 Оформить мероприятие", callback_data=f"project:event:{project.id}")])
            rows.append([InlineKeyboardButton(text="🔍 Найти команду", callback_data=f"project:team:{project.id}")])
        await safe_send(bot, author.telegram_id, f"💡 {notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{comment}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await state.clear()
    await message.answer("Решение сохранено и отправлено автору")
