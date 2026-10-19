from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.notification_service import safe_answer_document
from app.services.project_builder import render_project_document
from app.services.project_review_assignment_service import assigned_project_reviewer, claim_project_review
from app.services.project_workspace_service import can_review_any_projects, can_review_projects
from app.utils import texts
from app.utils.constants import PROJECT_STATUS_LABELS, ProjectStatus

router = Router(name="admin_projects_block5_list")


async def _guard(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> bool:
    await call.answer()
    if not await can_review_any_projects(session, user, settings):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


async def _author(session: AsyncSession, project: Project) -> User | None:
    return await session.get(User, project.author_id)


def _document(project: Project, author: User | None) -> str:
    if project.generated_document:
        return project.generated_document
    name = f"{author.first_name} {author.last_name or ''}".strip() if author else f"ID {project.author_id}"
    telegram = f"@{author.username}" if author and author.username else "без username"
    return render_project_document(project.form_data or {}, name, telegram)


def _keyboard(project: Project) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📄 Полный файл проекта", callback_data=f"admin:project:file:{project.id}")]]
    if project.status in {ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW}:
        rows.append([InlineKeyboardButton(text="✅ Принять в работу", callback_data=f"admin:project:review:initial_accept:{project.id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project.id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:project:review:reject:{project.id}")])
    elif project.status == ProjectStatus.VENUE_REVIEW:
        rows.append([InlineKeyboardButton(text="✅ Одобрить проект", callback_data=f"admin:project:review:venue_approve:{project.id}")])
        rows.append([InlineKeyboardButton(text="⏳ Перенести", callback_data=f"admin:project:review:postpone:{project.id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project.id}")])
    rows.append([InlineKeyboardButton(text="🙋 Взять проверку", callback_data=f"admin:project:claim:{project.id}"),
                 InlineKeyboardButton(text="Вернуть в очередь", callback_data=f"admin:project:release:{project.id}")])
    rows.append([InlineKeyboardButton(text="← Рабочие разделы", callback_data="staff:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:projects")
async def admin_projects(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings, session):
        return
    await show_projects(call.message, user, settings, session)


@router.message(Command("projects_review"))
async def projects_command(message: Message, user: User | None, settings: Settings, session: AsyncSession):
    if not await can_review_any_projects(session, user, settings):
        await message.answer(texts.NO_ACCESS)
        return
    await show_projects(message, user, settings, session)


async def show_projects(message, user, settings, session):
    projects = (await session.scalars(select(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW])).order_by(Project.submitted_at, Project.updated_at))).all()
    projects = [project for project in projects if await can_review_projects(session, user, settings, project)]
    if not projects:
        await message.answer("Проектов на рассмотрении нет")
        return
    for project in projects:
        author = await _author(session, project)
        who = f"{author.first_name} {author.last_name or ''}".strip() if author else f"ID {project.author_id}"
        reviewer_id = await assigned_project_reviewer(session, project.id)
        reviewer = await session.get(User, reviewer_id) if reviewer_id else None
        reviewer_label = reviewer.first_name if reviewer else "общая очередь"
        tg = f"@{author.username}" if author and author.username else "без username"
        await message.answer(
            f"💡 Проект #{project.id}\n\n{project.title}\n\nАвтор: {who} ({tg})\nСтатус: {PROJECT_STATUS_LABELS.get(project.status, project.status)}\nПроверяет: {reviewer_label}\n\nСуть:\n{project.short_description}",
            reply_markup=_keyboard(project),
        )


@router.callback_query(F.data.startswith("admin:project:file:"))
async def project_file(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings, session):
        return
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if not project:
        await call.message.answer("Проект не найден")
        return
    if not await can_review_projects(session, user, settings, project):
        await call.message.answer(texts.NO_ACCESS)
        return
    author = await _author(session, project)
    document = _document(project, author)
    project.generated_document = document
    if not await safe_answer_document(
        call.message,
        BufferedInputFile(BytesIO(document.encode("utf-8")).getvalue(), filename=f"ERA_project_{project.id}.txt"),
        caption=f"Полный проект #{project.id}: {project.title}",
    ):
        await call.message.answer("Файл проекта собран, но Telegram не дал отправить его. Попробуйте ещё раз.")


@router.callback_query(F.data.regexp(r"^admin:project:(claim|release):\d+$"))
async def project_claim(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await _guard(call, user, settings, session):
        return
    parts = call.data.split(":")
    try:
        await claim_project_review(session, int(parts[3]), user, settings, release=parts[2] == "release")
        await session.commit()
    except (PermissionError, ValueError):
        await call.message.answer("Проверка недоступна или уже назначена другому проверяющему. Обновите список.")
        return
    await call.message.answer("Проект возвращён в общую очередь." if parts[2] == "release" else
                              "Вы назначены проверяющим проекта.")
