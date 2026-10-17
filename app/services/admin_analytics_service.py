"""Aggregates the data behind the Excel/analytics export and the Mini App's
admin analytics summary — extracted from what was previously inline in
app/handlers/admin/management_ready.py's ``_analytics_payload`` so both the
bot's own "📊 Аналитика и Excel" flow and the new Mini App equivalent
(app/api/v1/admin.py) share one implementation instead of drifting apart.

Part of porting the legacy /panel admin tree to the Mini App — see
docs/BOT_VS_MINIAPP_AUDIT.md for the overall plan and which pieces
(chat-binding, the full data-wipe tool) are handled separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import (
    Department,
    Direction,
    Event,
    LeadershipAttentionItem,
    LeadershipGoal,
    LeadershipReport,
    Office,
    PointTransaction,
    PositionApplication,
    Project,
    Task,
    User,
    UserDepartment,
    UserDirection,
    UserOffice,
)
from app.utils.constants import AttentionItemStatus, LeadershipGoalStatus, TaskStatus


@dataclass(frozen=True)
class DepartmentStat:
    id: int
    name: str
    members: int
    active_goals: int
    done_goals: int


@dataclass(frozen=True)
class DirectionStat:
    department: str
    id: int
    name: str
    members: int


@dataclass(frozen=True)
class GoalRow:
    id: int
    month: str
    scope_type: str
    scope_name: str
    title: str
    target_value: int
    current_value: int
    status: str
    due_date: object | None


@dataclass(frozen=True)
class AnalyticsPayload:
    users: list[User]
    events: list[Event]
    projects: list[Project]
    totals: dict[int, int]
    department_stats: list[DepartmentStat]
    direction_stats: list[DirectionStat]
    goals: list[GoalRow]
    contacts: list[OrganizationContact]
    summary: dict[str, int] = field(default_factory=dict)


async def build_analytics_payload(session: AsyncSession) -> AnalyticsPayload:
    users = list(
        (
            await session.scalars(
                select(User).where(User.is_archived.is_(False)).order_by(User.first_name)
            )
        ).all()
    )
    events = list(
        (
            await session.scalars(
                select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(500)
            )
        ).all()
    )
    projects = list(
        (await session.scalars(select(Project).order_by(Project.created_at.desc()).limit(500))).all()
    )
    totals = dict(
        (
            await session.execute(
                select(PointTransaction.user_id, func.coalesce(func.sum(PointTransaction.points), 0)).group_by(
                    PointTransaction.user_id
                )
            )
        ).all()
    )

    dep_rows = (
        await session.execute(
            select(Department.id, Department.name, func.count(UserDepartment.id))
            .join(UserDepartment, Department.id == UserDepartment.department_id, isouter=True)
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )
    ).all()
    dir_rows = (
        await session.execute(
            select(Department.name, Direction.id, Direction.name, func.count(UserDirection.id))
            .join(Direction, Direction.department_id == Department.id)
            .join(UserDirection, UserDirection.direction_id == Direction.id, isouter=True)
            .group_by(Department.name, Direction.id, Direction.name)
            .order_by(Department.name, Direction.name)
        )
    ).all()
    goals = list(
        (
            await session.scalars(
                select(MonthlyGoal)
                .where(MonthlyGoal.status != "deleted")
                .order_by(MonthlyGoal.month.desc(), MonthlyGoal.created_at.desc())
                .limit(200)
            )
        ).all()
    )
    contacts = list(
        (
            await session.scalars(
                select(OrganizationContact)
                .where(OrganizationContact.is_active.is_(True))
                .order_by(OrganizationContact.organization_name)
            )
        ).all()
    )

    goals_by_department: dict[int, dict[str, int]] = {row[0]: {"active": 0, "done": 0} for row in dep_rows}
    for goal in goals:
        if goal.scope_type == "department" and goal.scope_id in goals_by_department:
            key = "done" if goal.status == "done" else "active"
            goals_by_department[goal.scope_id][key] += 1

    department_stats = [
        DepartmentStat(
            id=dep_id,
            name=name,
            members=members,
            active_goals=goals_by_department.get(dep_id, {}).get("active", 0),
            done_goals=goals_by_department.get(dep_id, {}).get("done", 0),
        )
        for dep_id, name, members in dep_rows
    ]
    direction_stats = [
        DirectionStat(department=dep_name, id=direction_id, name=direction_name, members=members)
        for dep_name, direction_id, direction_name, members in dir_rows
    ]

    goal_rows: list[GoalRow] = []
    for goal in goals:
        scope_name = "Вся организация"
        if goal.scope_type == "department" and goal.scope_id:
            found = next((item.name for item in department_stats if item.id == goal.scope_id), None)
            scope_name = found or scope_name
        elif goal.scope_type == "direction" and goal.scope_id:
            found = next((item.name for item in direction_stats if item.id == goal.scope_id), None)
            scope_name = found or scope_name
        goal_rows.append(
            GoalRow(
                id=goal.id,
                month=goal.month,
                scope_type=goal.scope_type,
                scope_name=scope_name,
                title=goal.title,
                target_value=goal.target_value,
                current_value=goal.current_value,
                status=goal.status,
                due_date=goal.due_date,
            )
        )

    approved = sum(1 for item in users if item.application_status == "approved")
    pending = sum(1 for item in users if item.application_status == "pending")
    summary = {
        "total_users": len(users),
        "approved_users": approved,
        "pending_users": pending,
        "events": len(events),
        "projects": len(projects),
        "contacts": len(contacts),
        "goals": len(goal_rows),
    }

    return AnalyticsPayload(
        users=users,
        events=events,
        projects=projects,
        totals=totals,
        department_stats=department_stats,
        direction_stats=direction_stats,
        goals=goal_rows,
        contacts=contacts,
        summary=summary,
    )


# Mirrors app/handlers/admin/management_ready.py::analytics_excel's section
# map, so the Mini App's export offers the exact same slices the bot did.
EXCEL_SECTION_MAP: dict[str, set[str] | None] = {
    "users": {"summary", "users"},
    "departments": {"summary", "departments", "directions", "goals"},
    "events": {"summary", "events"},
    "projects": {"summary", "projects"},
    "all": None,
}


# ---------------------------------------------------------------------------
# Leadership OS (2026-08 ToR section 43: "не создавать заново — расширять
# существующие"). MonthlyGoal above already covers org/department/direction
# KPI tracking (ToR section 32); this section is net-new metric groups for
# the Leadership OS layer specifically -- vacancies/applications, leader
# workload/effectiveness, open blockers, and one composite "Leadership
# Health" score (section 74: a measure of the management system, not of any
# individual).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeadershipAnalytics:
    vacancies_open: int
    applications_by_status: dict[str, int]
    active_leaders: int
    open_blockers: int
    avg_blocker_resolution_hours: float | None
    goals_active: int
    goals_completed: int
    goals_overdue: int
    goal_completion_rate: float | None
    reports_expected: int
    reports_submitted: int
    reporting_discipline_rate: float | None
    leadership_health_score: float | None


async def _active_leader_assignments(session: AsyncSession) -> list[UserOffice]:
    rows = (
        await session.execute(
            select(UserOffice, Office)
            .join(Office, Office.id == UserOffice.office_id)
            .where(UserOffice.is_active.is_(True))
        )
    ).all()
    return [a for a, o in rows if o.permission_template]


async def build_leadership_analytics(session: AsyncSession) -> LeadershipAnalytics:
    vacancies_open = int(
        await session.scalar(
            select(func.count())
            .select_from(Office)
            .where(
                Office.is_active.is_(True),
                Office.application_enabled.is_(True),
            )
        )
        or 0
    )

    application_rows = (
        await session.execute(
            select(PositionApplication.status, func.count()).group_by(PositionApplication.status)
        )
    ).all()
    applications_by_status = {status: count for status, count in application_rows}

    leader_assignments = await _active_leader_assignments(session)
    active_leaders = len({a.user_id for a in leader_assignments})

    open_blockers = int(
        await session.scalar(
            select(func.count())
            .select_from(LeadershipAttentionItem)
            .where(LeadershipAttentionItem.status == AttentionItemStatus.OPEN)
        )
        or 0
    )
    resolved_rows = list(
        (
            await session.scalars(
                select(LeadershipAttentionItem).where(
                    LeadershipAttentionItem.status == AttentionItemStatus.RESOLVED,
                    LeadershipAttentionItem.resolved_at.is_not(None),
                )
            )
        ).all()
    )
    resolution_hours = [
        (item.resolved_at - item.created_at).total_seconds() / 3600
        for item in resolved_rows
        if item.resolved_at and item.created_at
    ]
    avg_blocker_resolution_hours = (
        round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else None
    )

    goals = list((await session.scalars(select(LeadershipGoal))).all())
    goals_active = sum(1 for g in goals if g.status == LeadershipGoalStatus.ACTIVE)
    goals_completed = sum(1 for g in goals if g.status == LeadershipGoalStatus.COMPLETED)
    goals_overdue = sum(1 for g in goals if g.status == LeadershipGoalStatus.OVERDUE)
    concluded = goals_completed + goals_overdue
    goal_completion_rate = round(goals_completed / concluded * 100, 1) if concluded else None

    reports_expected = active_leaders
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    reports_submitted = int(
        await session.scalar(
            select(func.count(func.distinct(LeadershipReport.owner_id))).where(
                LeadershipReport.period_start >= week_start
            )
        )
        or 0
    )
    reporting_discipline_rate = (
        round(min(reports_submitted / reports_expected, 1.0) * 100, 1) if reports_expected else None
    )

    # Composite score (ToR section 74): equal-weighted average of the three
    # signals that have enough data to compute; each is already a 0-100
    # rate, so no extra normalization is invented here. None when there's
    # nothing to measure yet (no fabricated baseline score).
    signals = [
        rate
        for rate in (goal_completion_rate, reporting_discipline_rate)
        if rate is not None
    ]
    if open_blockers or resolved_rows:
        total_blockers = open_blockers + len(resolved_rows)
        blocker_health = round((1 - open_blockers / total_blockers) * 100, 1) if total_blockers else None
        if blocker_health is not None:
            signals.append(blocker_health)
    leadership_health_score = round(sum(signals) / len(signals), 1) if signals else None

    return LeadershipAnalytics(
        vacancies_open=vacancies_open,
        applications_by_status=applications_by_status,
        active_leaders=active_leaders,
        open_blockers=open_blockers,
        avg_blocker_resolution_hours=avg_blocker_resolution_hours,
        goals_active=goals_active,
        goals_completed=goals_completed,
        goals_overdue=goals_overdue,
        goal_completion_rate=goal_completion_rate,
        reports_expected=reports_expected,
        reports_submitted=reports_submitted,
        reporting_discipline_rate=reporting_discipline_rate,
        leadership_health_score=leadership_health_score,
    )


@dataclass(frozen=True)
class LeaderWorkload:
    assignments: int
    open_tasks: int
    overdue_tasks: int
    open_blockers: int


async def build_leader_workload(session: AsyncSession, user_id: int) -> LeaderWorkload:
    assignments = int(
        await session.scalar(
            select(func.count())
            .select_from(UserOffice)
            .where(UserOffice.user_id == user_id, UserOffice.is_active.is_(True))
        )
        or 0
    )
    open_tasks = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.assignee_id == user_id, Task.status != TaskStatus.COMPLETED)
        )
        or 0
    )
    overdue_tasks = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assignee_id == user_id,
                Task.status != TaskStatus.COMPLETED,
                Task.deadline < datetime.now(timezone.utc),
            )
        )
        or 0
    )
    open_blockers = int(
        await session.scalar(
            select(func.count())
            .select_from(LeadershipAttentionItem)
            .where(
                LeadershipAttentionItem.owner_id == user_id,
                LeadershipAttentionItem.status == AttentionItemStatus.OPEN,
            )
        )
        or 0
    )
    return LeaderWorkload(
        assignments=assignments,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        open_blockers=open_blockers,
    )


@dataclass(frozen=True)
class LeaderEffectiveness:
    goals_completed: int
    goals_total: int
    goal_completion_rate: float | None
    tasks_completed: int
    tasks_total: int
    task_completion_rate: float | None
    overdue_rate: float | None


async def build_leader_effectiveness(session: AsyncSession, user_id: int) -> LeaderEffectiveness:
    goals = list((await session.scalars(select(LeadershipGoal).where(LeadershipGoal.owner_id == user_id))).all())
    goals_completed = sum(1 for g in goals if g.status == LeadershipGoalStatus.COMPLETED)
    goal_completion_rate = round(goals_completed / len(goals) * 100, 1) if goals else None

    tasks_total = int(
        await session.scalar(
            select(func.count()).select_from(Task).where(Task.assignee_id == user_id)
        )
        or 0
    )
    tasks_completed = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.assignee_id == user_id, Task.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assignee_id == user_id,
                Task.status != TaskStatus.COMPLETED,
                Task.deadline < datetime.now(timezone.utc),
            )
        )
        or 0
    )
    return LeaderEffectiveness(
        goals_completed=goals_completed,
        goals_total=len(goals),
        goal_completion_rate=goal_completion_rate,
        tasks_completed=tasks_completed,
        tasks_total=tasks_total,
        task_completion_rate=round(tasks_completed / tasks_total * 100, 1) if tasks_total else None,
        overdue_rate=round(overdue / tasks_total * 100, 1) if tasks_total else None,
    )


async def build_management_report(session: AsyncSession, *, now: datetime, days: int = 1, period_start: datetime | None = None, period_end: datetime | None = None) -> dict:
    """Aggregate operational facts; unavailable measurements stay None, never fake zero."""
    import json
    from zoneinfo import ZoneInfo
    from sqlalchemy import or_
    from app.database.models import AppSetting, EventRegistration, UserQuestion
    from app.database.system_models import BackupHistory, NotificationDelivery, SystemDiagnosticRun
    from app.services.admin_dashboard_service import dashboard_metrics, _count
    from app.services.meaningful_activity_service import meaningful_user_ids_since
    from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, RegistrationStatus

    end = period_end or now
    since = period_start or end - timedelta(days=days)
    local_date = now.astimezone(ZoneInfo('Europe/Moscow')).date()
    dashboard = (await dashboard_metrics(session)).values
    result = {key: dashboard[key] for key in ('users_total', 'users_pending', 'projects_review', 'tasks_open', 'questions')}
    result['profiles_new'] = await _count(session, User, User.created_at >= since, User.created_at < end, User.is_archived.is_(False))
    result['applications_rejected'] = await _count(session, User, User.application_status == ApplicationStatus.REJECTED, User.is_archived.is_(False))
    result['applications_approved'] = dashboard['users_approved']
    for window in (1, 7, 30):
        ids = await meaningful_user_ids_since(session, now - timedelta(days=window), include_current_responsibility=False)
        result[f'active_{window}'] = await _count(session, User, User.id.in_(ids), User.is_archived.is_(False),
                                                  User.is_blocked.is_(False), User.application_status == ApplicationStatus.APPROVED)
    result['events_upcoming'] = await _count(session, Event, Event.event_date >= local_date,
        Event.event_date <= local_date + timedelta(days=7), Event.status.not_in((EventStatus.DRAFT, EventStatus.CANCELLED, EventStatus.PENDING_APPROVAL)))
    result['registrations_new'] = await _count(session, EventRegistration, EventRegistration.created_at >= since, EventRegistration.created_at < end)
    result['attended'] = await _count(session, EventRegistration, EventRegistration.status == RegistrationStatus.ATTENDED,
                                     EventRegistration.last_confirmation_at >= since, EventRegistration.last_confirmation_at < end)
    review = (ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW)
    result['projects_overdue'] = await _count(session, Project, Project.status.in_(review), Project.submitted_at <= now - timedelta(hours=72))
    result['tasks_open'] = await _count(session, Task, Task.status.in_((TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.OVERDUE)))
    result['tasks_overdue'] = await _count(session, Task, Task.status.in_((TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.OVERDUE)),
                                           or_(Task.deadline < now, Task.status == TaskStatus.OVERDUE))
    result['questions_overdue'] = await _count(session, UserQuestion, UserQuestion.status.in_(('new', 'open')), UserQuestion.created_at <= now - timedelta(hours=24))
    result['delivered'] = await _count(session, NotificationDelivery, NotificationDelivery.status == 'sent', NotificationDelivery.sent_at >= since, NotificationDelivery.sent_at < end)
    result['delivery_errors'] = await _count(session, NotificationDelivery, NotificationDelivery.status.in_(('failed', 'uncertain', 'blocked', 'unreachable')),
                                            NotificationDelivery.last_attempt_at >= since, NotificationDelivery.last_attempt_at < end)
    # Room slots are overwritten. Only immutable completed-result entries count as measured history.
    rows = (await session.scalars(select(AppSetting).where(AppSetting.key.like('game-result:%')))).all()
    completed, players, starts = 0, set(), []
    for row in rows:
        item = json.loads(row.value) if isinstance(row.value, str) else row.value
        finished = datetime.fromisoformat(item['finished_at'])
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        starts.append(finished)
        if since <= finished < end:
            completed += 1
            players.update(item.get('participants', []))
    measured_in_period = bool(starts) and min(starts) < end
    result['games_completed'] = completed if measured_in_period else None
    result['game_players'] = len(players) if measured_in_period else None
    result['game_coverage_since'] = min(starts).isoformat() if starts else None
    latest = await session.scalar(select(SystemDiagnosticRun).order_by(SystemDiagnosticRun.created_at.desc()).limit(1))
    result['health'] = latest.status if latest else 'нет данных'
    heartbeat_at = latest.created_at if latest else None
    if heartbeat_at and heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
    result['scheduler'] = ('работает' if now - heartbeat_at <= timedelta(minutes=30) else 'нет свежего heartbeat') if heartbeat_at else 'нет данных'
    backup = await session.scalar(select(BackupHistory).where(BackupHistory.status == 'success', BackupHistory.restore_verified_at.is_not(None)).order_by(BackupHistory.restore_verified_at.desc()).limit(1))
    verified = backup.restore_verified_at if backup else None
    if verified and verified.tzinfo is None:
        verified = verified.replace(tzinfo=timezone.utc)
    result['backup'] = ('восстановление проверено' if now - verified <= timedelta(hours=24) else 'проверенная копия старше 24 ч') if verified else 'нет проверенных данных'
    result['as_of'] = now.isoformat()
    result['period_days'] = days
    result['period_start'] = since.isoformat()
    result['period_end'] = end.isoformat()
    return result


def management_report_text(metrics: dict, *, title: str = 'Ежедневный отчёт', previous: dict | None = None) -> str:
    from datetime import datetime
    from html import escape
    from zoneinfo import ZoneInfo
    def value(key):
        return 'не измеряется' if metrics.get(key) is None else escape(str(metrics[key]))
    as_of = datetime.fromisoformat(metrics['as_of']).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M МСК')
    window = ' — '.join(datetime.fromisoformat(metrics[k]).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m %H:%M') for k in ('period_start', 'period_end'))
    health = {'healthy': 'в норме', 'ok': 'в норме', 'warning': 'требует внимания',
              'error': 'ошибка', 'critical': 'критично', 'failed': 'ошибка'}.get(metrics.get('health'), value('health'))
    text = (f'📊 <b>ЭРА · {escape(title)}</b>\n<i>{as_of}</i>\n'
        f'Операции за {window} МСК\n\n'
        '<b>👥 Участники и заявки</b>\n'
        f"Участников: {value('users_total')} · новых профилей: {value('profiles_new')}\n"
        f"Заявки: ожидают {value('users_pending')} · одобрено {value('applications_approved')} · отклонено {value('applications_rejected')}\n"
        f"Активность, 24 ч / 7 д / 30 д: {value('active_1')} / {value('active_7')} / {value('active_30')}\n\n"
        '<b>📅 События и работа команды</b>\n'
        f"Мероприятия на 7 дней: {value('events_upcoming')} · новых регистраций: {value('registrations_new')} · посещений: {value('attended')}\n"
        f"Проекты: на рассмотрении {value('projects_review')} · дольше 72 ч {value('projects_overdue')}\n"
        f"Задачи: открыто {value('tasks_open')} · просрочено {value('tasks_overdue')}\n"
        f"Обращения: ждут {value('questions')} · дольше 24 ч {value('questions_overdue')}\n\n"
        '<b>🎮 Игры и доставка</b>\n'
        f"Игры, новый учёт: игроков {value('game_players')} · завершено {value('games_completed')}\n"
        f"Автоуведомления: доставлено {value('delivered')} · ошибок {value('delivery_errors')}\n\n"
        '<b>🛠 Состояние системы</b>\n'
        f"Система: {health} · планировщик: {value('scheduler')}\nБэкап: {value('backup')}\n")
    if metrics.get('game_coverage_since'):
        text += 'Игровая статистика ведётся с ' + datetime.fromisoformat(metrics['game_coverage_since']).strftime('%d.%m.%Y') + '.\n'
    if previous:
        delta = metrics['users_total'] - previous['users_total']
        text += f'Участников к предыдущему отчёту: {delta:+d}.\n'
    else:
        text += 'Сравнение с предыдущим периодом: нет данных.\n'
    attention = []
    for key, label in (('projects_overdue', 'Рассмотреть проекты'), ('tasks_overdue', 'Разобрать просроченные задачи'), ('questions_overdue', 'Ответить на обращения'), ('users_pending', 'Рассмотреть заявки')):
        if metrics.get(key):
            attention.append(f'{label}: {metrics[key]}')
    if metrics.get('backup') != 'восстановление проверено':
        attention.insert(0, 'Проверить резервное копирование')
    if metrics.get('scheduler') != 'работает':
        attention.insert(0, 'Проверить работу планировщика')
    if metrics.get('health') not in {'healthy', 'ok'}:
        attention.insert(0, 'Проверить состояние сервиса')
    return text + '\n<b>📌 Требует внимания</b>\n' + ('\n'.join(f'{i}. {line}' for i, line in enumerate(attention[:3], 1)) or 'Нет просроченных действий по измеряемым показателям.')


def management_report_markup(miniapp_url: str = ''):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    rows = [
        [InlineKeyboardButton(text='📥 Заявки', callback_data='admin:applications'),
         InlineKeyboardButton(text='📅 Мероприятия', callback_data='admin:events')],
        [InlineKeyboardButton(text='✅ Задачи', callback_data='admin:tasks'),
         InlineKeyboardButton(text='🔄 Обновить', callback_data='admin:management:refresh')],
        [InlineKeyboardButton(text='📈 Неделя', callback_data='admin:management:period:weekly'),
         InlineKeyboardButton(text='🗓 Месяц', callback_data='admin:management:period:monthly')],
        [InlineKeyboardButton(text='📄 Excel', callback_data='admin:management:excel')],
    ]
    if miniapp_url:
        rows.append([InlineKeyboardButton(text='🔥 Открыть ЭРА', web_app=WebAppInfo(url=miniapp_url))])
    rows.append([InlineKeyboardButton(text='← Управление', callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def management_report_recipients(session: AsyncSession, settings) -> set[int]:
    from app.database.models import PermissionGrant
    from app.utils.constants import Role
    grants = select(PermissionGrant.user_id).where(PermissionGrant.permission == 'analytics.view',
        PermissionGrant.is_active.is_(True), PermissionGrant.scope_type == 'global')
    query = select(User.telegram_id).where(User.is_blocked.is_(False), User.is_archived.is_(False),
        (User.role == Role.ADMIN) | User.telegram_id.in_(settings.admin_ids) | User.id.in_(grants))
    recipients = set((await session.scalars(query)).all())
    if settings.management_report_recipient_ids:
        recipients &= set(settings.management_report_recipient_ids)
    if settings.feature_management_reports == 'TESTERS':
        recipients &= set(settings.management_report_recipient_ids or settings.feature_tester_ids)
    return recipients


async def send_management_reports(bot, settings, session_factory, *, now=None) -> None:
    import hashlib
    import json
    from zoneinfo import ZoneInfo
    from sqlalchemy import text
    from app.database.models import AppSetting
    from app.services.notification_service import safe_send_once
    if settings.feature_management_reports == 'OFF':
        return
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo('Europe/Moscow'))
    if (local.hour, local.minute) < (settings.management_report_hour, settings.management_report_minute):
        return
    week_boundary = local.date() - timedelta(days=local.weekday())
    month_boundary = local.date().replace(day=1)
    month_days = (month_boundary - (month_boundary - timedelta(days=1)).replace(day=1)).days
    # Evaluate the latest due boundary even after Monday / day 1 has passed.
    # Frozen period keys and the common delivery ledger make this bounded recovery.
    periods = [('daily', local.date().isoformat(), 1, 'Ежедневный отчёт'),
               ('weekly', week_boundary.isoformat(), 7, 'Еженедельный отчёт'),
               ('monthly', month_boundary.isoformat(), month_days, 'Ежемесячный отчёт')]
    async with session_factory() as session:
        recipients = await management_report_recipients(session, settings)
    if not recipients:
        return
    for period, stamp, days, title in periods:
        key = f'management-report:{period}:{stamp}'
        async with session_factory() as session:
            if session.bind.dialect.name == 'postgresql':
                lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
                await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            if row:
                payload = json.loads(row.value) if isinstance(row.value, str) else row.value
            else:
                month_end = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                month_start = (month_end - timedelta(days=1)).replace(day=1)
                week_end = (local - timedelta(days=local.weekday())).replace(hour=settings.management_report_hour,
                    minute=settings.management_report_minute, second=0, microsecond=0)
                period_end = month_end if period == 'monthly' else week_end if period == 'weekly' else None
                period_start = month_start if period == 'monthly' else week_end-timedelta(days=7) if period == 'weekly' else None
                metrics = await build_management_report(session, now=now, days=days,
                    period_start=period_start.astimezone(timezone.utc) if period_start else None,
                    period_end=period_end.astimezone(timezone.utc) if period_end else None)
                previous_key = f'management-report:{period}:{(datetime.fromisoformat(stamp).date()-timedelta(days=days)).isoformat()}'
                previous_row = await session.scalar(select(AppSetting).where(AppSetting.key == previous_key))
                previous = json.loads(previous_row.value)['metrics'] if previous_row and isinstance(previous_row.value, str) else None
                payload = {'metrics': metrics, 'text': management_report_text(metrics, title=title, previous=previous)}
                session.add(AppSetting(key=key, value=json.dumps(payload, ensure_ascii=False)))
                await session.commit()
        for recipient in sorted(recipients):
            await safe_send_once(bot, settings, recipient, payload['text'], delivery_key=f'{period}:{stamp}:{recipient}',
                                 notification_type='management_report', parse_mode='HTML',
                                 reply_markup=management_report_markup(settings.effective_miniapp_url))
