from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, Project, TaskSubmission, User
from app.keyboards.admin import admin_panel_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus, Role

router = Router(name="admin_dashboard_start")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
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


def _keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧭 Что где ждёт", callback_data="admin:help")]]
    rows.extend(admin_panel_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _text(session: AsyncSession) -> str:
    total_users = await session.scalar(select(func.count(User.id)).where(User.is_archived.is_(False))) or 0
    approved = await session.scalar(select(func.count(User.id)).where(User.application_status == ApplicationStatus.APPROVED, User.is_archived.is_(False))) or 0
    pending = await session.scalar(select(func.count(User.id)).where(User.application_status == ApplicationStatus.PENDING)) or 0
    projects_review = await session.scalar(select(func.count(Project.id)).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW]))) or 0
    projects_active = await session.scalar(select(func.count(Project.id)).where(Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS]))) or 0
    events = await session.scalar(select(func.count(Event.id))) or 0
    task_results = await session.scalar(select(func.count(TaskSubmission.id)).where(TaskSubmission.status == "pending")) or 0
    return (
        "⚙️ Админ-панель ЭРА\n\n"
        "Главные показатели:\n"
        f"👥 Участники: {total_users}\n"
        f"✅ Одобрены: {approved}\n"
        f"📝 Новые заявки: {pending}\n"
        f"💡 Проекты на проверке: {projects_review}\n"
        f"🚀 Активные проекты: {projects_active}\n"
        f"📅 Мероприятий: {events}\n"
        f"📥 Итоги заданий: {task_results}\n\n"
        "Ниже — управление системой."
    )


@router.message(F.text.in_({"/admin", "⚙️ Управление"}))
async def admin_dashboard(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(await _text(session), reply_markup=_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(await _text(session), reply_markup=_keyboard())
