from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    DepartmentApplication,
    Event,
    EventActivitySubmission,
    PortfolioItem,
    Project,
    Report,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    UserQuestion,
)
from app.keyboards.admin import admin_panel_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, Role, TaskStatus

router = Router(name="admin_dashboard_block_a")


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


async def _count(session: AsyncSession, model, *conditions) -> int:
    query = select(func.count()).select_from(model)
    for condition in conditions:
        query = query.where(condition)
    return int(await session.scalar(query) or 0)


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧭 Что где ждёт", callback_data="admin:attention")]]
    rows.extend(admin_panel_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _metrics(session: AsyncSession) -> dict[str, int]:
    return {
        "users_total": await _count(session, User, User.is_archived.is_(False)),
        "users_approved": await _count(session, User, User.application_status == ApplicationStatus.APPROVED, User.is_archived.is_(False)),
        "users_pending": await _count(session, User, User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]), User.is_archived.is_(False)),
        "activists": await _count(session, User, User.role == Role.ACTIVIST, User.is_archived.is_(False)),
        "leaders": await _count(session, User, User.role.in_([Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]), User.is_archived.is_(False)),
        "projects_review": await _count(session, Project, Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW])),
        "projects_active": await _count(session, Project, Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS])),
        "events_pending": await _count(session, Event, Event.status == EventStatus.PENDING_APPROVAL),
        "events_live": await _count(session, Event, Event.status.in_([EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN, EventStatus.ACTIVE])),
        "tasks_open": await _count(session, Task, Task.status.in_([TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW])),
        "task_results": await _count(session, TaskSubmission, TaskSubmission.status == "pending"),
        "activity_results": await _count(session, EventActivitySubmission, EventActivitySubmission.status.in_(["pending", "leader_approved"])),
        "rewards": await _count(session, RewardRedemption, RewardRedemption.status.in_(["pending", "reserved", "answered"])),
        "portfolio": await _count(session, PortfolioItem, PortfolioItem.status == "pending"),
        "reports": await _count(session, Report, Report.status.in_(["pending", "submitted", "needs_revision"])),
        "questions": await _count(session, UserQuestion, UserQuestion.status.in_(["new", "open"])),
        "departments": await _count(session, DepartmentApplication, DepartmentApplication.status == "pending"),
    }


def _dashboard_text(m: dict[str, int]) -> str:
    attention = m["users_pending"] + m["projects_review"] + m["events_pending"] + m["task_results"] + m["activity_results"] + m["rewards"] + m["portfolio"] + m["reports"] + m["questions"] + m["departments"]
    return (
        "⚙️ Админ-панель ЭРА\n\n"
        "Организация сейчас:\n"
        f"👥 Участники всего: {m['users_total']}\n"
        f"✅ Одобрены: {m['users_approved']}\n"
        f"📝 Новые заявки: {m['users_pending']}\n"
        f"🔥 Активисты: {m['activists']}\n"
        f"🧭 Лидеры / совет / админы: {m['leaders']}\n\n"
        "Проекты и события:\n"
        f"💡 Проекты на проверке: {m['projects_review']}\n"
        f"🚀 Активные проекты: {m['projects_active']}\n"
        f"📅 Мероприятия на согласовании: {m['events_pending']}\n"
        f"📣 Мероприятия в работе / опубликованы: {m['events_live']}\n\n"
        "Что ждёт решения:\n"
        f"✅ Итоги заданий: {m['task_results']}\n"
        f"✨ Активности после мероприятий: {m['activity_results']}\n"
        f"🎁 Заявки на возможности: {m['rewards']}\n"
        f"🎓 Портфолио: {m['portfolio']}\n"
        f"📄 Отчёты: {m['reports']}\n"
        f"💬 Вопросы: {m['questions']}\n"
        f"🏛 Заявки по направлениям: {m['departments']}\n\n"
        f"Итого требует внимания: {attention}\n"
        f"Открытых задач в системе: {m['tasks_open']}"
    )


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_dashboard(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    metrics = await _metrics(session)
    await message.answer(_dashboard_text(metrics), reply_markup=_dashboard_keyboard())


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    metrics = await _metrics(session)
    await call.message.answer(_dashboard_text(metrics), reply_markup=_dashboard_keyboard())


@router.callback_query(F.data == "admin:attention")
async def admin_attention(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    m = await _metrics(session)
    items = [
        ("📝 Новые заявки", "admin:applications", m["users_pending"]),
        ("💡 Проекты", "admin:projects", m["projects_review"]),
        ("📅 Мероприятия", "admin:events", m["events_pending"]),
        ("✅ Итоги заданий", "admin:task_submissions", m["task_results"]),
        ("✨ Активности", "admin:event_activities:review", m["activity_results"]),
        ("🎁 Возможности", "admin:reward:redemptions", m["rewards"]),
        ("🎓 Портфолио", "admin:portfolio", m["portfolio"]),
        ("📄 Отчёты", "admin:reports", m["reports"]),
        ("💬 Вопросы", "admin:questions", m["questions"]),
        ("🏛 Направления", "admin:departments", m["departments"]),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    lines = ["🧭 Что где ждёт\n"]
    for label, callback, amount in items:
        lines.append(f"{label}: {amount}")
        if amount:
            rows.append([InlineKeyboardButton(text=f"{label} · {amount}", callback_data=callback)])
    rows.append([InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")])
    await call.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
