from io import BytesIO
from datetime import datetime, timedelta

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.services.portfolio_service import add_portfolio_item
from app.services.project_builder import render_project_document
from app.utils import texts
from app.utils.constants import PROJECT_STATUS_LABELS, ProjectStatus, Role

router = Router(name="admin_project_full_review")


class ProjectDecisionStates(StatesGroup):
    comment = State()


def is_admin(u: User | None, s: Settings, tg_id: int) -> bool:
    return bool(tg_id in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))


async def guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def actions(project_id: int, status: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📄 Полный файл проекта", callback_data=f"admin:project:file:{project_id}")]]
    if status == ProjectStatus.INITIAL_REVIEW:
        rows.append([InlineKeyboardButton(text="✅ Принять в работу", callback_data=f"admin:project:review:initial_accept:{project_id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project_id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:project:review:reject:{project_id}")])
    elif status == ProjectStatus.VENUE_REVIEW:
        rows.append([InlineKeyboardButton(text="✅ Одобрить проект", callback_data=f"admin:project:review:venue_approve:{project_id}")])
        rows.append([InlineKeyboardButton(text="⏳ Перенести", callback_data=f"admin:project:review:postpone:{project_id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project_id}")])
    else:
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project_id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:project:review:reject:{project_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def doc(project: Project, author: User | None) -> str:
    if project.generated_document:
        return project.generated_document
    name = f"{author.first_name} {author.last_name or ''}".strip() if author else f"ID {project.author_id}"
    tg = f"@{author.username}" if author and author.username else "без username"
    return render_project_document(project.form_data or {}, name, tg)


@router.callback_query(F.data == "admin:projects")
async def projects_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    projects = (await session.scalars(select(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW])).order_by(Project.submitted_at, Project.created_at))).all()
    if not projects:
        await call.message.answer("Проектов на рассмотрении нет")
        return
    for p in projects:
        author = await session.get(User, p.author_id)
        who = f"{author.first_name} {author.last_name or ''}".strip() if author else f"ID {p.author_id}"
        tg = f"@{author.username}" if author and author.username else "без username"
        await call.message.answer(
            f"💡 Проект #{p.id}\n\n{p.title}\n\nАвтор: {who} ({tg})\nСтатус: {PROJECT_STATUS_LABELS.get(p.status, p.status)}\n\nСуть:\n{p.short_description}",
            reply_markup=actions(p.id, p.status),
        )


@router.callback_query(F.data.startswith("admin:project:file:"))
async def project_file(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    p = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if not p:
        await call.message.answer("Проект не найден")
        return
    author = await session.get(User, p.author_id)
    text = await doc(p, author)
    p.generated_document = text
    file = BufferedInputFile(BytesIO(text.encode("utf-8")).getvalue(), filename=f"ERA_project_{p.id}.txt")
    await call.message.answer_document(file, caption=f"Полный проект #{p.id}: {p.title}")


@router.callback_query(F.data.regexp(r"^admin:project:review:[a-z_]+:\d+$"))
async def project_decision_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    _, _, _, action, raw_id = call.data.split(":")
    await state.set_state(ProjectDecisionStates.comment)
    await state.update_data(project_action=action, project_id=int(raw_id))
    prompt = {
        "initial_accept": "Что принято в работу и что уточняем дальше?",
        "venue_approve": "Итоговое сообщение автору: проект одобрен, что дальше?",
        "postpone": "Почему переносим и когда вернуться?",
        "revise": "Что конкретно доработать?",
        "reject": "Почему проект отклонён?",
    }.get(action, "Комментарий автору")
    await call.message.answer(prompt)


@router.message(ProjectDecisionStates.comment)
async def project_decision_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not is_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    data = await state.get_data()
    p = await session.get(Project, int(data["project_id"]))
    if not p:
        await state.clear()
        await message.answer("Проект не найден")
        return
    action = data["project_action"]
    comment = (message.text or "").strip()[:2000]
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    old_status = p.status
    p.admin_comment = comment
    if action == "initial_accept":
        p.status = ProjectStatus.VENUE_REVIEW
        p.venue_status = "pending"
        p.venue_comment = comment
        p.venue_reminder_count = 0
        p.venue_remind_at = datetime.now().astimezone() + timedelta(days=1)
        notice = "Проект прошёл первичную проверку и перешёл к согласованию деталей"
    elif action == "venue_approve":
        p.status = ProjectStatus.APPROVED
        p.venue_status = "approved"
        p.venue_comment = comment
        p.venue_remind_at = None
        if old_status != ProjectStatus.APPROVED:
            await add_points(session, user_id=p.author_id, points=30, reason=f"Одобренный проект: {p.title}", approved_by=user.id if user else None, related_project_id=p.id)
            await add_portfolio_item(session, user_id=p.author_id, title=f"Автор проекта: {p.title}", item_type="project", description=p.short_description, issued_by=user.id if user else None, related_project_id=p.id)
        notice = "Проект одобрен. Следующий шаг — оформить мероприятие и анонс"
    elif action == "postpone":
        p.status = ProjectStatus.POSTPONED
        p.venue_remind_at = None
        notice = "Проект перенесён"
    elif action == "reject":
        p.status = ProjectStatus.REJECTED
        p.venue_remind_at = None
        notice = "Проект отклонён"
    else:
        p.status = ProjectStatus.NEEDS_REVISION
        p.venue_remind_at = None
        notice = "Проект возвращён на доработку"
    owner = await session.get(User, p.author_id)
    if owner:
        rows = []
        if p.status == ProjectStatus.APPROVED:
            rows.append([InlineKeyboardButton(text="📅 Оформить мероприятие", callback_data=f"project:event:{p.id}")])
        await safe_send(
            bot,
            owner.telegram_id,
            f"💡 {notice}\n\nПроект: {p.title}\n\nКомментарий команды ЭРА:\n{comment}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        )
    await state.clear()
    await message.answer("Решение сохранено и отправлено автору")
