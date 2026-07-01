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
from app.keyboards.participant import project_menu_keyboard
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.services.project_builder import render_project_document
from app.utils import texts
from app.utils.constants import ApplicationStatus, PROJECT_STATUS_LABELS, ProjectStatus
from app.utils.validators import clean_text

router = Router(name="participant_projects_block5")


class ProjectTeamStates(StatesGroup):
    text = State()


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def _load_owned(session: AsyncSession, project_id: int, user: User) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project and project.author_id == user.id else None


def _project_document(project: Project, author: User) -> str:
    if project.generated_document:
        return project.generated_document
    author_name = f"{author.first_name} {author.last_name or ''}".strip()
    telegram = f"@{author.username}" if author.username else str(author.telegram_id)
    return render_project_document(project.form_data or {}, author_name, telegram)


def _admin_project_keyboard(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Полный файл проекта", callback_data=f"admin:project:file:{project_id}")],
        [InlineKeyboardButton(text="✅ Принять в работу", callback_data=f"admin:project:review:initial_accept:{project_id}")],
        [InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:project:review:revise:{project_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:project:review:reject:{project_id}")],
    ])


def _projects_keyboard(projects: list[Project]) -> InlineKeyboardMarkup:
    rows = []
    for project in projects:
        if project.status in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
            rows.append([InlineKeyboardButton(text=f"✏️ Продолжить: {project.title[:30]}", callback_data=f"project:resume:{project.id}")])
            rows.append([InlineKeyboardButton(text=f"🗑 Удалить: {project.title[:34]}", callback_data=f"project:delete:{project.id}")])
        elif project.status in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
            rows.append([InlineKeyboardButton(text=f"📅 Оформить мероприятие: {project.title[:24]}", callback_data=f"project:event:{project.id}")])
            rows.append([InlineKeyboardButton(text=f"🔍 Найти команду: {project.title[:28]}", callback_data=f"project:team:{project.id}")])
        else:
            rows.append([InlineKeyboardButton(text=f"👁 {project.title[:38]} · {PROJECT_STATUS_LABELS.get(project.status, project.status)}", callback_data=f"project:status:{project.id}")])
    rows.append([InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.in_({"cabinet:projects", "projects:drafts"}))
async def my_projects(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    projects = (await session.scalars(select(Project).where(Project.author_id == user.id, Project.status != ProjectStatus.CANCELLED).order_by(desc(Project.updated_at)))).all()
    if not projects:
        await call.message.answer("Проектов пока нет", reply_markup=project_menu_keyboard())
        return
    lines = "\n".join(f"• {project.title} — {PROJECT_STATUS_LABELS.get(project.status, project.status)}" for project in projects)
    await call.message.answer(f"📁 Мои проекты\n\n{lines}\n\nВыберите действие:", reply_markup=_projects_keyboard(list(projects)))


@router.callback_query(F.data.startswith("project:status:"))
async def project_status(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project:
        await call.message.answer(texts.NO_ACCESS)
        return
    await call.message.answer(
        f"💡 {project.title}\n\nСтатус: {PROJECT_STATUS_LABELS.get(project.status, project.status)}\nКомментарий команды:\n{project.admin_comment or project.venue_comment or 'пока нет комментария'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Мои проекты", callback_data="cabinet:projects")]]),
    )


@router.callback_query(F.data.startswith("project:delete:"))
async def project_delete_first(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION, ProjectStatus.REJECTED, ProjectStatus.POSTPONED}:
        await call.message.answer("Удалить можно только черновик, доработку, отклонённый или перенесённый проект")
        return
    await call.message.answer(
        f"Удалить проект «{project.title}»?\n\nЭто первое подтверждение.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить удаление", callback_data=f"project:delete_step2:{project.id}")],
            [InlineKeyboardButton(text="Отмена", callback_data="cabinet:projects")],
        ]),
    )


@router.callback_query(F.data.startswith("project:delete_step2:"))
async def project_delete_second(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project:
        await call.message.answer(texts.NO_ACCESS)
        return
    await call.message.answer(
        f"Точно удалить «{project.title}»?\n\nПосле этого проект уйдёт в архив и не будет отображаться в списке.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить окончательно", callback_data=f"project:delete_confirm:{project.id}")],
            [InlineKeyboardButton(text="Нет, оставить", callback_data="cabinet:projects")],
        ]),
    )


@router.callback_query(F.data.startswith("project:delete_confirm:"))
async def project_delete_confirm(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project:
        await call.message.answer(texts.NO_ACCESS)
        return
    project.status = ProjectStatus.CANCELLED
    await call.message.answer("Проект удалён из активного списка.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Мои проекты", callback_data="cabinet:projects")]]))


@router.callback_query(F.data.startswith("project:submit:"))
async def project_submit_full(call: CallbackQuery, session: AsyncSession, user: User, bot: Bot, settings: Settings) -> None:
    await call.answer()
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if project is None:
        await call.message.answer(texts.NO_ACCESS)
        return
    if project.status not in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
        await call.message.answer("Проект уже отправлен на рассмотрение")
        return
    project.status = ProjectStatus.INITIAL_REVIEW
    project.submitted_at = datetime.now().astimezone()
    document = _project_document(project, user)
    project.generated_document = document
    await audit(session, actor_id=user.id, action="project.submitted", entity_type="project", entity_id=project.id)
    await call.message.answer(texts.PROJECT_SUBMITTED)
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    summary = f"💡 Новый проект на рассмотрении\n\n{project.title}\nАвтор: {user.first_name} {user.last_name or ''} ({telegram})\n\nПолный файл проекта прикреплён ниже."
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    for chat_id in recipients:
        await safe_send(bot, chat_id, summary, reply_markup=_admin_project_keyboard(project.id))
        await bot.send_document(chat_id, BufferedInputFile(BytesIO(document.encode("utf-8")).getvalue(), filename=f"ERA_project_{project.id}.txt"), caption=f"Полный проект #{project.id}")


@router.callback_query(F.data.startswith("project:event:"))
async def project_event_next(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Оформить мероприятие можно после одобрения проекта")
        return
    await call.message.answer(
        f"📅 Следующий этап: мероприятие по проекту «{project.title}»\n\nВ следующем блоке здесь будет открываться конструктор мероприятия. Сейчас можно передать проект лидеру/админу для оформления через панель.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Найти команду", callback_data=f"project:team:{project.id}")], [InlineKeyboardButton(text="← Мои проекты", callback_data="cabinet:projects")]]),
    )


@router.callback_query(F.data.startswith("project:team:"))
async def team_start(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()
    if not _approved(user):
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Искать команду можно после одобрения проекта")
        return
    await state.set_state(ProjectTeamStates.text)
    await state.update_data(team_project_id=project.id)
    await call.message.answer("Напишите текст для поиска команды.\n\nСтруктура: кого ищем, что нужно делать, сколько времени займёт участие и почему это стоит сделать.\nПосле отправки текст уйдёт админу на модерацию.")


@router.message(ProjectTeamStates.text)
async def team_submit(message: Message, user: User, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    data = await state.get_data()
    project = await _load_owned(session, int(data["team_project_id"]), user)
    if not project:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text = clean_text(message.text or message.caption or "", 2000)
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
    admin_text = f"🔍 Поиск команды на модерации\n\nПроект: {project.title}\nАвтор: {user.first_name} {user.last_name or ''} ({telegram})\n\nПредпросмотр:\n{text}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data=f"admin:team_post:preview:{project.id}")],
        [InlineKeyboardButton(text="✅ Одобрить 1/2", callback_data=f"admin:team_post:prepare:{project.id}")],
        [InlineKeyboardButton(text="✏️ Отредактировать", callback_data=f"admin:team_post:edit:{project.id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:team_post:reject:{project.id}")],
    ])
    for chat_id in set(settings.admin_ids):
        await safe_send(bot, chat_id, admin_text, reply_markup=keyboard)
