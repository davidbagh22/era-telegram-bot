from __future__ import annotations

from collections.abc import Iterable

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.management_models import AdminSurvey, AdminSurveyResponse, MonthlyGoal, OrganizationContact
from app.database.models import Event, EventActivitySubmission, Project, Task, User, UserQuestion
from app.handlers.admin.management_ready import _analytics_payload, _guard
from app.utils.constants import (
    APPLICATION_STATUS_LABELS,
    EVENT_STATUS_LABELS,
    PROJECT_STATUS_LABELS,
    ROLE_LABELS,
    TASK_STATUS_LABELS,
    ApplicationStatus,
    EventStatus,
    ProjectStatus,
    Role,
    TaskStatus,
)

router = Router(name="admin_analytics_filters")


def _analytics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚦 Что где ждёт", callback_data="admin:analytics:waiting"),
                InlineKeyboardButton(text="🔎 Фильтры", callback_data="admin:analytics:filters"),
            ],
            [
                InlineKeyboardButton(text="📘 Базовый Excel", callback_data="admin:analytics:excel:all"),
                InlineKeyboardButton(text="🗳 Excel опросов", callback_data="admin:analytics:excel:surveys"),
            ],
            [
                InlineKeyboardButton(text="👥 Участники", callback_data="admin:analytics:slice:users"),
                InlineKeyboardButton(text="🏛 Департаменты", callback_data="admin:analytics:slice:departments"),
            ],
            [
                InlineKeyboardButton(text="📅 События", callback_data="admin:analytics:slice:events"),
                InlineKeyboardButton(text="💡 Проекты", callback_data="admin:analytics:slice:projects"),
            ],
            [InlineKeyboardButton(text="🗳 Управленческие опросы", callback_data="admin:surveys")],
            [InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")],
        ]
    )


def _analytics_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 По статусу заявки", callback_data="admin:analytics:slice:user_status"),
                InlineKeyboardButton(text="🧩 По роли", callback_data="admin:analytics:slice:roles"),
            ],
            [
                InlineKeyboardButton(text="🎂 По возрасту", callback_data="admin:analytics:slice:age"),
                InlineKeyboardButton(text="🏛 Департаменты", callback_data="admin:analytics:slice:departments"),
            ],
            [
                InlineKeyboardButton(text="🧭 Направления", callback_data="admin:analytics:slice:directions"),
                InlineKeyboardButton(text="✅ Задачи", callback_data="admin:analytics:slice:tasks"),
            ],
            [
                InlineKeyboardButton(text="📅 Статусы событий", callback_data="admin:analytics:slice:events"),
                InlineKeyboardButton(text="💡 Статусы проектов", callback_data="admin:analytics:slice:projects"),
            ],
            [InlineKeyboardButton(text="🗳 Опросы и ответы", callback_data="admin:analytics:slice:surveys")],
            [InlineKeyboardButton(text="← Аналитика", callback_data="admin:analytics")],
        ]
    )


def _system_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Аналитика", callback_data="admin:analytics"),
                InlineKeyboardButton(text="🚦 Что ждёт", callback_data="admin:analytics:waiting"),
            ],
            [
                InlineKeyboardButton(text="🗳 Опросы", callback_data="admin:surveys"),
                InlineKeyboardButton(text="🎯 Цели месяца", callback_data="admin:goals"),
            ],
            [
                InlineKeyboardButton(text="🤝 Организации", callback_data="admin:contacts"),
                InlineKeyboardButton(text="🏛 Структура", callback_data="admin:structure"),
            ],
            [
                InlineKeyboardButton(text="👥 Должности и права", callback_data="admin:offices"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings"),
            ],
            [InlineKeyboardButton(text="🧹 Очистка тестовых данных", callback_data="admin:maintenance")],
            [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
        ]
    )


def _count_lines(rows: Iterable[tuple[object, int]], labels: dict | None = None) -> str:
    lines = []
    for raw_key, count in rows:
        key = raw_key or "не указано"
        label = labels.get(key, key) if labels else key
        lines.append(f"• {label}: {count}")
    return "\n".join(lines) or "данных пока нет"


def _enum_labels(enum_type, labels: dict) -> dict[str, str]:
    return {item.value: labels.get(item, item.value) for item in enum_type}


async def _count_by(session: AsyncSession, model, column, *where) -> list[tuple[object, int]]:
    statement = select(column, func.count()).select_from(model)
    if where:
        statement = statement.where(*where)
    return list((await session.execute(statement.group_by(column).order_by(func.count().desc()))).all())


@router.callback_query(F.data == "admin:menu:system")
async def system_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "⚙️ Управление ЭРА\n\n"
        "Быстрые разделы для контроля организации: аналитика, ожидания, опросы, цели, структура, права и настройки",
        reply_markup=_system_keyboard(),
    )


@router.callback_query(F.data == "admin:analytics")
async def analytics_overview(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    data = await _analytics_payload(session)
    survey_count = int(await session.scalar(select(func.count()).select_from(AdminSurvey)) or 0)
    response_count = int(await session.scalar(select(func.count()).select_from(AdminSurveyResponse)) or 0)
    approved = sum(1 for item in data["users"] if item.application_status == ApplicationStatus.APPROVED)
    pending = sum(1 for item in data["users"] if item.application_status == ApplicationStatus.PENDING)
    text = (
        "📊 Аналитика ЭРА\n\n"
        f"Участников в базе: {len(data['users'])}\n"
        f"Одобрены: {approved}\n"
        f"Новые заявки: {pending}\n"
        f"Мероприятий: {len(data['events'])}\n"
        f"Проектов: {len(data['projects'])}\n"
        f"Опросов: {survey_count}\n"
        f"Ответов на опросы: {response_count}\n"
        f"Целей месяца: {len(data['goals'])}\n"
        f"Организаций в базе: {len(data['contacts'])}\n\n"
        "Выберите готовый срез или скачайте Excel"
    )
    await call.message.answer(text, reply_markup=_analytics_keyboard())


@router.callback_query(F.data == "admin:analytics:filters")
async def analytics_filters(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "🔎 Фильтры аналитики\n\nВыберите срез — бот покажет короткую управленческую сводку прямо здесь",
        reply_markup=_analytics_filter_keyboard(),
    )


@router.callback_query(F.data == "admin:analytics:waiting")
async def analytics_waiting(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    pending_users = int(await session.scalar(select(func.count()).select_from(User).where(User.application_status == ApplicationStatus.PENDING, User.is_archived.is_(False))) or 0)
    pending_projects = int(await session.scalar(select(func.count()).select_from(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW, ProjectStatus.NEEDS_REVISION]))) or 0)
    pending_events = int(await session.scalar(select(func.count()).select_from(Event).where(Event.status == EventStatus.PENDING_APPROVAL)) or 0)
    pending_tasks = int(await session.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.REVIEW)) or 0)
    pending_activities = int(await session.scalar(select(func.count()).select_from(EventActivitySubmission).where(EventActivitySubmission.status.in_(["pending", "leader_approved"]))) or 0)
    pending_questions = int(await session.scalar(select(func.count()).select_from(UserQuestion).where(UserQuestion.status == "new")) or 0)
    active_goals = int(await session.scalar(select(func.count()).select_from(MonthlyGoal).where(MonthlyGoal.status == "active")) or 0)
    active_contacts = int(await session.scalar(select(func.count()).select_from(OrganizationContact).where(OrganizationContact.is_active.is_(True))) or 0)
    text = (
        "🚦 Что где ждёт\n\n"
        f"👥 Заявки участников: {pending_users}\n"
        f"💡 Проекты на решении: {pending_projects}\n"
        f"📅 Мероприятия на согласовании: {pending_events}\n"
        f"✅ Задачи на проверке: {pending_tasks}\n"
        f"✨ Активности после мероприятий: {pending_activities}\n"
        f"💬 Вопросы пользователей: {pending_questions}\n"
        f"🎯 Активные цели месяца: {active_goals}\n"
        f"🤝 Организаций в базе: {active_contacts}\n\n"
        "Если число больше нуля — откройте соответствующий раздел из админ-панели"
    )
    await call.message.answer(text, reply_markup=_analytics_keyboard())


@router.callback_query(F.data.startswith("admin:analytics:slice:"))
async def analytics_slice(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    kind = call.data.rsplit(":", 1)[-1]
    data = await _analytics_payload(session)
    if kind == "users":
        rows = await _count_by(session, User, User.application_status, User.is_archived.is_(False))
        body = _count_lines(rows, _enum_labels(ApplicationStatus, APPLICATION_STATUS_LABELS))
        title = "👥 Участники по статусу"
    elif kind == "user_status":
        rows = await _count_by(session, User, User.application_status, User.is_archived.is_(False))
        body = _count_lines(rows, _enum_labels(ApplicationStatus, APPLICATION_STATUS_LABELS))
        title = "👥 Статусы заявок"
    elif kind == "roles":
        rows = await _count_by(session, User, User.role, User.is_archived.is_(False))
        body = _count_lines(rows, _enum_labels(Role, ROLE_LABELS))
        title = "🧩 Роли участников"
    elif kind == "age":
        buckets = {"14–17": 0, "18–24": 0, "25–34": 0, "35+": 0, "не указан": 0}
        for participant in data["users"]:
            age = participant.age
            if age is None:
                buckets["не указан"] += 1
            elif age < 18:
                buckets["14–17"] += 1
            elif age < 25:
                buckets["18–24"] += 1
            elif age < 35:
                buckets["25–34"] += 1
            else:
                buckets["35+"] += 1
        body = "\n".join(f"• {label}: {count}" for label, count in buckets.items())
        title = "🎂 Возраст участников"
    elif kind == "departments":
        body = "\n".join(
            f"• {item['name']}: {item['members']} участников, целей активных {item['active_goals']}, выполнено {item['done_goals']}"
            for item in data["department_stats"]
        ) or "департаменты пока не заполнены"
        title = "🏛 Работа департаментов"
    elif kind == "directions":
        body = "\n".join(
            f"• {item['department']} / {item['name']}: {item['members']} участников"
            for item in data["direction_stats"]
        ) or "направления пока не заполнены"
        title = "🧭 Активность направлений"
    elif kind == "events":
        rows = await _count_by(session, Event, Event.status)
        body = _count_lines(rows, _enum_labels(EventStatus, EVENT_STATUS_LABELS))
        title = "📅 Статусы мероприятий"
    elif kind == "projects":
        rows = await _count_by(session, Project, Project.status)
        body = _count_lines(rows, _enum_labels(ProjectStatus, PROJECT_STATUS_LABELS))
        title = "💡 Статусы проектов"
    elif kind == "tasks":
        rows = await _count_by(session, Task, Task.status)
        body = _count_lines(rows, _enum_labels(TaskStatus, TASK_STATUS_LABELS))
        title = "✅ Статусы задач"
    elif kind == "surveys":
        rows = await _count_by(session, AdminSurvey, AdminSurvey.status)
        responses = int(await session.scalar(select(func.count()).select_from(AdminSurveyResponse)) or 0)
        body = f"Опросы:\n{_count_lines(rows)}\n\nОтветов всего: {responses}"
        title = "🗳 Опросы и обратная связь"
    else:
        title = "🔎 Срез аналитики"
        body = "Такой срез не найден"
    await call.message.answer(
        f"{title}\n\n{body}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="← Фильтры", callback_data="admin:analytics:filters")],
                [InlineKeyboardButton(text="← Аналитика", callback_data="admin:analytics")],
            ]
        ),
    )
