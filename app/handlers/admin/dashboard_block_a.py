from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and not user.is_archived and any(g.is_active for g in (user.permission_grants or [])))
    )


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


def _attention_total(m: dict[str, int]) -> int:
    keys = (
        "users_pending",
        "projects_review",
        "events_pending",
        "task_results",
        "activity_results",
        "rewards",
        "portfolio",
        "reports",
        "questions",
        "departments",
    )
    return sum(m[key] for key in keys)


def _dashboard_keyboard(m: dict[str, int]) -> InlineKeyboardMarkup:
    attention = _attention_total(m)
    label = f"🔔 Требует решения · {attention}" if attention else "✅ Очередь чиста"
    rows = [[InlineKeyboardButton(text=label, callback_data="admin:attention")]]
    rows.extend(admin_panel_keyboard().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _replace_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


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
    attention = _attention_total(m)
    queue = (
        f"🔔 Требует решения: {attention}\n"
        "Откройте очередь — там показаны только актуальные запросы"
        if attention
        else "✅ Очередь чиста\nНовых запросов на проверку сейчас нет"
    )
    return (
        "⚙️ Центр управления ЭРА\n\n"
        "👥 Люди\n"
        f"Всего: {m['users_total']} · одобрено: {m['users_approved']}\n"
        f"Активисты: {m['activists']} · лидерский состав: {m['leaders']}\n\n"
        "🚀 Работа сообщества\n"
        f"Проекты: {m['projects_active']} активных · {m['projects_review']} ждут решения\n"
        f"Мероприятия: {m['events_live']} в работе · {m['events_pending']} ждут решения\n"
        f"Открытые задачи: {m['tasks_open']}\n\n"
        f"{queue}"
    )


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_dashboard(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    metrics = await _metrics(session)
    await message.answer(_dashboard_text(metrics), reply_markup=_dashboard_keyboard(metrics))


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    metrics = await _metrics(session)
    await _replace_message(call.message, _dashboard_text(metrics), _dashboard_keyboard(metrics))


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
    active = [(label, callback, amount) for label, callback, amount in items if amount]
    rows = [
        [InlineKeyboardButton(text=f"{label} · {amount}", callback_data=callback)]
        for label, callback, amount in active
    ]
    rows.append([InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")])
    if active:
        lines = ["🔔 Что требует решения", "", "Выберите очередь:"]
        lines.extend(f"{label}: {amount}" for label, _, amount in active)
    else:
        lines = ["✅ Очередь чиста", "", "Новых запросов на проверку сейчас нет"]
    await _replace_message(
        call.message,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )
