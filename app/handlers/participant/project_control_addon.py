from datetime import datetime
from io import BytesIO

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Project, User
from app.keyboards.admin import entity_actions
from app.services.audit_service import audit
from app.services.notification_service import notify_admins, safe_send
from app.services.project_builder import render_project_document
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus

router = Router(name="participant_project_control_addon")


class ProjectTeamPostStates(StatesGroup):
    text = State()


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def _load_owned_project(session: AsyncSession, project_id: int, user: User) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project and project.author_id == user.id else None


def _project_row(project: Project) -> list[list[InlineKeyboardButton]]:
    rows = []
    if project.status in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
        rows.append([InlineKeyboardButton(text=f"Продолжить: {project.title[:32]}", callback_data=f"project:resume:{project.id}")])
    if project.status in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        rows.append([InlineKeyboardButton(text=f"🔍 Найти команду: {project.title[:28]}", callback_data=f"project:team_post:{project.id}")])
    if project.status in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION, ProjectStatus.REJECTED, ProjectStatus.POSTPONED}:
        rows.append([InlineKeyboardButton(text=f"🗑 Удалить: {project.title[:32]}", callback_data=f"project:delete:{project.id}")])
    return rows


@router.callback_query(F.data == "projects:drafts")
async def project_list_with_delete(call: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    projects = (
        await session.scalars(
            select(Project)
            .where(Project.author_id == user.id, Project.status != ProjectStatus.CANCELLED)
            .order_by(desc(Project.updated_at))
        )
    ).all()
    if not projects:
        await call.message.answer("Проектов пока нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")]]))
        return
    rows = []
    for project in projects:
        rows.extend(_project_row(project))
    rows.append([InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")])
    await call.message.answer("📁 Мои проекты\n\nЧерновики можно продолжить или удалить. Для одобренных проектов можно искать команду.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("project:delete:"))
async def project_delete_ask(call: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project:
        await call.message.answer(texts.NO_ACCESS)
        return
    await call.message.answer(
        f"Удалить проект «{project.title}»?\n\nЭто действие нужно подтвердить ещё раз.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Да, удалить проект", callback_data=f"project:delete_confirm:{project.id}")],
                [InlineKeyboardButton(text="Нет, оставить", callback_data="projects:drafts")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("project:delete_confirm:"))
async def project_delete_confirm(call: CallbackQuery, session: AsyncSession, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project:
        await call.message.answer(texts.NO_ACCESS)
        return
    project.status = ProjectStatus.CANCELLED
    await call.message.answer("Проект удалён из активного списка.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Мои проекты", callback_data="projects:drafts")]]))


@router.callback_query(F.data.startswith("project:submit:"))
async def project_submit_with_document(
    call: CallbackQuery,
    session: AsyncSession,
    user: User | None,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if project is None:
        await call.message.answer(texts.NO_ACCESS)
        return
    if project.status not in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
        await call.message.answer("Проект уже отправлен на рассмотрение")
        return
    project.status = ProjectStatus.INITIAL_REVIEW
    project.submitted_at = datetime.now().astimezone()
    author_name = f"{user.first_name} {user.last_name or ''}".strip()
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    document = project.generated_document or render_project_document(project.form_data or {}, author_name, telegram)
    project.generated_document = document
    await audit(session, actor_id=user.id, action="project.submitted", entity_type="project", entity_id=project.id)
    await call.message.answer(texts.PROJECT_SUBMITTED)
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    summary = (
        "💡 Новый проект на рассмотрении\n\n"
        f"{project.title}\n"
        f"Автор: {author_name} ({telegram})\n\n"
        "Полный файл проекта прикреплён ниже."
    )
    for chat_id in recipients:
        file = BufferedInputFile(BytesIO(document.encode("utf-8")).getvalue(), filename=f"ERA_project_{project.id}.txt")
        await safe_send(bot, chat_id, summary, reply_markup=entity_actions("project", project.id))
        await bot.send_document(chat_id, file, caption=f"Полный проект #{project.id}")


@router.callback_query(F.data.startswith("project:team_post:"))
async def project_team_post_start(call: CallbackQuery, session: AsyncSession, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Искать команду можно после одобрения проекта")
        return
    await state.set_state(ProjectTeamPostStates.text)
    await state.update_data(team_project_id=project.id)
    await call.message.answer(
        "Напишите публикацию для поиска единомышленников.\n\n"
        "Укажите: кого ищете, что нужно делать, сколько времени займёт участие и почему это стоит сделать.\n"
        "После отправки текст должен утвердить админ."
    )


@router.message(ProjectTeamPostStates.text)
async def project_team_post_submit(message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot, settings: Settings) -> None:
    data = await state.get_data()
    project = await _load_owned_project(session, int(data["team_project_id"]), user)
    if not project:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text = (message.text or message.caption or "").strip()
    if len(text) < 30:
        await message.answer("Слишком коротко. Добавьте, кого ищете и что нужно делать.")
        return
    form_data = dict(project.form_data or {})
    form_data["team_search_post"] = text
    form_data["team_search_status"] = "pending"
    project.form_data = form_data
    await state.clear()
    await message.answer("Публикация для поиска команды отправлена админу на утверждение.")
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    await notify_admins(
        bot,
        settings,
        f"🔍 Запрос на поиск команды\n\nПроект: {project.title}\nАвтор: {user.first_name} {user.last_name or ''} ({telegram})\n\n{text}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить публикацию", callback_data=f"admin:team_post:approve:{project.id}")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:team_post:reject:{project.id}")],
            ]
        ),
    )
