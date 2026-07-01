from io import BytesIO

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.services.project_builder import render_project_document
from app.utils import texts
from app.utils.constants import PROJECT_STATUS_LABELS, ProjectStatus, Role

router = Router(name="admin_projects_block5_list")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


async def _guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not _is_admin(user, settings, call.from_user.id):
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
    rows.append([InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:projects")
async def admin_projects(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    projects = (await session.scalars(select(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW])).order_by(Project.submitted_at, Project.updated_at))).all()
    if not projects:
        await call.message.answer("Проектов на рассмотрении нет")
        return
    for project in projects:
        author = await _author(session, project)
        who = f"{author.first_name} {author.last_name or ''}".strip() if author else f"ID {project.author_id}"
        tg = f"@{author.username}" if author and author.username else "без username"
        await call.message.answer(
            f"💡 Проект #{project.id}\n\n{project.title}\n\nАвтор: {who} ({tg})\nСтатус: {PROJECT_STATUS_LABELS.get(project.status, project.status)}\n\nСуть:\n{project.short_description}",
            reply_markup=_keyboard(project),
        )


@router.callback_query(F.data.startswith("admin:project:file:"))
async def project_file(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    project = await session.get(Project, int(call.data.rsplit(":", 1)[-1]))
    if not project:
        await call.message.answer("Проект не найден")
        return
    author = await _author(session, project)
    document = _document(project, author)
    project.generated_document = document
    await call.message.answer_document(BufferedInputFile(BytesIO(document.encode("utf-8")).getvalue(), filename=f"ERA_project_{project.id}.txt"), caption=f"Полный проект #{project.id}: {project.title}")
