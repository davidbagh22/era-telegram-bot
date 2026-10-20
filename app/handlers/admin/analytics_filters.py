from __future__ import annotations

from collections.abc import Iterable

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.management_models import AdminSurvey, AdminSurveyResponse, MonthlyGoal, OrganizationContact
from app.database.models import Event, EventActivitySubmission, Project, Task, TaskSubmission, User, UserQuestion
from app.handlers.admin.management_ready import _guard, analytics_excel
from app.handlers.admin.surveys_analytics import survey_excel
from app.services.admin_analytics_service import build_analytics_payload
from app.services.analytics_snapshot_service import build_analytics_snapshot, build_event_analytics, build_project_analytics, delivery_problem_counts
from app.services.analytics_growth_service import build_growth_snapshot
from app.utils.telegram import edit_text_or_answer
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
            [InlineKeyboardButton(text=f"{days} дней", callback_data=f"admin:analytics:period:{days}") for days in (7, 30, 90)],
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
                InlineKeyboardButton(text="📅 Мероприятия", callback_data="admin:analytics:entities:events:30"),
                InlineKeyboardButton(text="💡 Проекты", callback_data="admin:analytics:entities:projects:30"),
            ],
            [InlineKeyboardButton(text="Рост за 90 дней", callback_data="admin:analytics:growth")],
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
@router.callback_query(F.data.regexp(r"^admin:analytics:period:(7|30|90)$"))
async def analytics_overview(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    days = int(call.data.rsplit(":", 1)[-1]) if ":period:" in call.data else 30
    snapshot = await build_analytics_snapshot(session, days=days, timezone_name=settings.timezone)
    lines = [f"📊 Аналитика ЭРА · {days} дней", ""]
    for metric in snapshot.metrics:
        value = "см. Рост за 90 дней" if metric.key == "funnel" else ("нет данных" if metric.value is None else str(metric.value))
        delta = "" if metric.delta is None else f" ({metric.delta:+g})"
        warning = "⚠️ " if metric.key in {"active", "retention"} and metric.delta is not None and metric.delta < 0 else ""
        lines.append(f"{warning}{metric.label}: {value}{delta}")
    lines.extend(["", "Активность — подтверждённые результаты. Должности и цифровые действия считаются отдельно.",
                  f"Изменение — к предыдущим {days} дням. Исторические значения без доказательств не восстанавливаются.",
                  "Определения и ограничения — в Excel, лист «Обзор 2.0»."])
    text = "\n".join(lines)
    keyboard = _analytics_keyboard()
    keyboard.inline_keyboard.insert(1, [InlineKeyboardButton(text=f"Excel · {days} дней", callback_data=f"admin:analytics:download:{days}")])
    if getattr(settings, 'feature_management_reports', 'OFF') != 'OFF':
        from app.services.admin_analytics_service import management_report_recipients
        if call.from_user.id in await management_report_recipients(session, settings):
            keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text='📊 Управленческий отчёт', callback_data='admin:management:refresh')])
    await edit_text_or_answer(call.message, text, reply_markup=keyboard)


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
    pending_users = int(await session.scalar(select(func.count()).select_from(User).where(User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]), User.is_archived.is_(False))) or 0)
    pending_projects = int(await session.scalar(select(func.count()).select_from(Project).where(Project.status.in_([ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW, ProjectStatus.NEEDS_REVISION]))) or 0)
    pending_events = int(await session.scalar(select(func.count()).select_from(Event).where(Event.status == EventStatus.PENDING_APPROVAL)) or 0)
    pending_tasks = int(await session.scalar(select(func.count()).select_from(Task).where(((Task.status == TaskStatus.REVIEW) | select(TaskSubmission.id).where(TaskSubmission.task_id == Task.id, TaskSubmission.status == 'pending').exists()) & (Task.status != TaskStatus.CANCELLED))) or 0)
    from datetime import datetime, timezone
    from app.services.analytics_snapshot_service import task_attention_condition
    tasks_attention = int(await session.scalar(select(func.count()).select_from(Task).where(task_attention_condition(datetime.now(timezone.utc)))) or 0)
    pending_activities = int(await session.scalar(select(func.count()).select_from(EventActivitySubmission).where(EventActivitySubmission.status.in_(["pending", "leader_approved"]))) or 0)
    pending_questions = int(await session.scalar(select(func.count()).select_from(UserQuestion).where(UserQuestion.status.in_(['new', 'open', 'thread_waiting', 'answer_failed', 'answer_review']))) or 0)
    delivery = await delivery_problem_counts(session)
    project_metrics = await build_project_analytics(session, timezone_name=settings.timezone)
    without_results = next(metric.value for metric in project_metrics.metrics if metric.key == 'without_results')
    active_goals = int(await session.scalar(select(func.count()).select_from(MonthlyGoal).where(MonthlyGoal.status == "active")) or 0)
    active_contacts = int(await session.scalar(select(func.count()).select_from(OrganizationContact).where(OrganizationContact.is_active.is_(True))) or 0)
    text = (
        "🚦 Что где ждёт\n\n"
        f"👥 Заявки участников: {pending_users}\n"
        f"💡 Незавершённые согласования проектов: {pending_projects}\n"
        f"📅 Мероприятия на согласовании: {pending_events}\n"
        f"✅ Задачи на проверке: {pending_tasks}\n"
        f"Задачи требуют внимания: {tasks_attention}\n"
        f"✨ Активности после мероприятий: {pending_activities}\n"
        f"💬 Вопросы пользователей: {pending_questions}\n"
        f"🎯 Активные цели месяца: {active_goals}\n"
        f"🤝 Организаций в базе: {active_contacts}\n"
        f"Проекты без подтверждённых результатов за 30 дней: {without_results}\n"
        f"Проблемные доставки рассылок за 30 дней: {delivery['broadcasts']}\n"
        f"Проблемные доставки отчётов за 30 дней: {delivery['reports']}\n\n"
        "Откройте очередь кнопкой ниже. Показатели разных очередей не суммируются в число людей."
    )
    actions = []
    for count, label, callback in (
        (pending_users, "Заявки участников", "admin:applications"),
        (pending_projects, "Решения по проектам", "admin:projects"),
        (pending_events, "Согласовать мероприятия", "admin:events"),
        (pending_tasks, "Проверить результаты задач", "admin:task_submissions"),
        (tasks_attention, "Разобрать задачи", "admin:taskattention:page:0"),
        (pending_questions, "Ответить на обращения", "admin:questions"),
        (pending_activities, "Проверить активности", "admin:event_activities:review"),
    ):
        if count:
            actions.append([InlineKeyboardButton(text=f"{label}: {count}", callback_data=callback)])
    if without_results:
        actions.append([InlineKeyboardButton(text='Проверить результаты проектов', callback_data='admin:analytics:entities:projects:30')])
    if delivery['broadcasts']:
        actions.append([InlineKeyboardButton(text='Проверить историю рассылок', callback_data='lc:history')])
    if delivery['reports'] and getattr(settings, 'feature_management_reports', 'OFF') != 'OFF':
        actions.append([InlineKeyboardButton(text='Проверить управленческий отчёт', callback_data='admin:management:refresh')])
    actions.append([InlineKeyboardButton(text="Назад", callback_data="admin:analytics"), InlineKeyboardButton(text="Главная", callback_data="admin:panel")])
    await edit_text_or_answer(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=actions))


@router.callback_query(F.data.startswith("admin:analytics:slice:"))
async def analytics_slice(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    kind = call.data.rsplit(":", 1)[-1]
    data = await build_analytics_payload(session)
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
        for participant in data.users:
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
            f"• {item.name}: {item.members} участников, целей активных {item.active_goals}, выполнено {item.done_goals}"
            for item in data.department_stats
        ) or "департаменты пока не заполнены"
        title = "🏛 Работа департаментов"
    elif kind == "directions":
        body = "\n".join(
            f"• {item.department} / {item.name}: {item.members} участников"
            for item in data.direction_stats
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


@router.callback_query(F.data == "admin:analytics:growth")
async def analytics_growth(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    growth = await build_growth_snapshot(session)
    lines = ["Рост · когорта регистраций за 90 дней", ""]
    rows = []
    for stage in growth.stages:
        conversion = "—" if stage.conversion is None else f"{stage.conversion:g}%"
        duration = "—" if stage.median_days is None else f"{stage.median_days:g} дн."
        lines.append(f"{stage.label}: {stage.count} · {conversion} · срок {duration}")
        if stage.lost_user_ids:
            rows.append([InlineKeyboardButton(text=f"{stage.label}: ещё не наблюдалось у {len(stage.lost_user_ids)}", callback_data=f"admin:analytics:gaps:{stage.key}:0")])
    lines.extend(["", f"Одобрены без истории одобрения: {growth.approval_history_missing}.", growth.note])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:analytics"), InlineKeyboardButton(text="Главная", callback_data="admin:panel")])
    await edit_text_or_answer(call.message, "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.regexp(r"^admin:analytics:gaps:(approved|first|repeat|active|leader):[0-9]{1,6}$"))
async def analytics_growth_gaps(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, key, raw_page = call.data.split(":")
    page = int(raw_page)
    growth = await build_growth_snapshot(session)
    stage = next(item for item in growth.stages if item.key == key)
    ids = stage.lost_user_ids[page * 10:(page + 1) * 10]
    people = (await session.scalars(select(User).where(User.id.in_(ids)).order_by(User.first_name))).all() if ids else []
    lines = [f"{stage.label} · пока нет наблюдаемого перехода", "Не означает, что участник ушёл.", ""]
    lines.extend(" ".join(part for part in [person.first_name, person.last_name] if part) for person in people)
    if not people:
        lines.append("В этом срезе участников нет.")
    rows = []
    if page:
        rows.append([InlineKeyboardButton(text="Предыдущие", callback_data=f"admin:analytics:gaps:{key}:{page-1}")])
    if (page + 1) * 10 < len(stage.lost_user_ids):
        rows.append([InlineKeyboardButton(text="Следующие", callback_data=f"admin:analytics:gaps:{key}:{page+1}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:analytics:growth"), InlineKeyboardButton(text="Главная", callback_data="admin:panel")])
    await edit_text_or_answer(call.message, "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# Reuse the existing guarded exporters, mounting only their exact routes.
# The historical management/survey routers remain unmounted.
@router.callback_query(F.data.in_({
    "admin:analytics:excel", "admin:analytics:excel:all", "admin:analytics:excel:users",
    "admin:analytics:excel:departments", "admin:analytics:excel:events", "admin:analytics:excel:projects",
}))
async def analytics_legacy_excel(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await analytics_excel(call, user, settings, session)


@router.callback_query(F.data == "admin:analytics:excel:surveys")
async def analytics_survey_excel(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await survey_excel(call, user, settings, session)


@router.callback_query(F.data.regexp(r"^admin:analytics:download:(7|30|90)$"))
async def analytics_period_excel(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await analytics_excel(call, user, settings, session, days=int(call.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.regexp(r"^admin:analytics:entities:(events|projects):(7|30|90)$"))
async def analytics_entities(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, kind, raw_days = call.data.split(":")
    days = int(raw_days)
    builder = build_event_analytics if kind == 'events' else build_project_analytics
    data = await builder(session, days=days, timezone_name=settings.timezone)
    lines = [f'{"Мероприятия" if kind == "events" else "Проекты"} · {days} дней', '']
    for metric in data.metrics:
        value = 'нет данных' if metric.value is None else str(metric.value)
        delta = '' if metric.delta is None else f' ({metric.delta:+g})'
        lines.append(f'{metric.label}: {value}{delta}')
    lines.extend(['', 'Скобки — изменение к предыдущему сопоставимому периоду. Текущие статусы без исторического снимка не имеют выдуманной динамики.',
                  'Определения и ограничения — в Excel.'])
    rows = [[InlineKeyboardButton(text=f'{period} дней', callback_data=f'admin:analytics:entities:{kind}:{period}') for period in (7,30,90)],
            [InlineKeyboardButton(text=f'Excel · {days} дней', callback_data=f'admin:analytics:download:{days}')],
            [InlineKeyboardButton(text='Открыть управление', callback_data='admin:events' if kind == 'events' else 'admin:projects')],
            [InlineKeyboardButton(text='Назад', callback_data='admin:analytics'), InlineKeyboardButton(text='Главная', callback_data='admin:panel')]]
    await edit_text_or_answer(call.message, '\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
