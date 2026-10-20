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

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import (
    AuditLog,
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
    TaskSubmission,
    User,
    UserDepartment,
    UserDirection,
    UserOffice,
)
from app.services.analytics_snapshot_service import roster_conditions
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
                select(Event).order_by(Event.event_date.desc(), Event.event_time)
            )
        ).all()
    )
    projects = list(
        (await session.scalars(select(Project).order_by(Project.created_at.desc()))).all()
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
            select(Department.id, Department.name, func.count(UserDepartment.id).filter(UserDepartment.user_id.in_(select(User.id).where(*roster_conditions()))))
            .join(UserDepartment, Department.id == UserDepartment.department_id, isouter=True)
            .group_by(Department.id, Department.name)
            .order_by(Department.name)
        )
    ).all()
    dir_rows = (
        await session.execute(
            select(Department.name, Direction.id, Direction.name, func.count(UserDirection.id).filter(UserDirection.user_id.in_(select(User.id).where(*roster_conditions()))))
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


async def _management_period_facts(session, start, end, timezone_name):
    """Comparable flows only; current stocks never masquerade as history."""
    from zoneinfo import ZoneInfo
    from app.database.models import EventRegistration
    from app.database.system_models import NotificationDelivery
    from app.services.analytics_snapshot_service import count_new_members, count_verified_users, held_events_between

    def count(model, *conditions):
        return select(func.count()).select_from(model).where(*conditions).scalar_subquery()

    accepted = select(func.count(func.distinct(TaskSubmission.id))).join(AuditLog,
        (AuditLog.entity_type == 'task_submission') & (AuditLog.entity_id == TaskSubmission.id)
    ).where(AuditLog.action == 'task.submission_approve', TaskSubmission.status == 'approved',
            AuditLog.created_at >= start, AuditLog.created_at < end).scalar_subquery()
    zone = ZoneInfo(timezone_name)
    queries = {
        'profiles_new': count(User, User.created_at >= start, User.created_at < end, User.is_archived.is_(False)),
        'events_held': select(func.count()).select_from(held_events_between(start.astimezone(zone), end.astimezone(zone)).subquery()).scalar_subquery(),
        'registrations_new': count(EventRegistration, EventRegistration.created_at >= start, EventRegistration.created_at < end),
        'attended': count(EventRegistration, EventRegistration.status == 'attended', EventRegistration.last_confirmation_at >= start, EventRegistration.last_confirmation_at < end),
        'task_results': accepted,
        'delivered': count(NotificationDelivery, NotificationDelivery.status == 'sent', NotificationDelivery.sent_at >= start, NotificationDelivery.sent_at < end),
        'delivery_errors': count(NotificationDelivery, NotificationDelivery.status.in_(['failed', 'uncertain', 'blocked', 'unreachable', 'conflict']),
                                 NotificationDelivery.last_attempt_at >= start, NotificationDelivery.last_attempt_at < end),
    }
    row = (await session.execute(select(*queries.values()))).one()
    result = dict(zip(queries, map(int, row)))
    result['new_members'] = await count_new_members(session, start, end)
    result['active_period'] = await count_verified_users(session, start, end)
    return result


async def build_management_report(session: AsyncSession, *, now: datetime, days: int = 1, period_start: datetime | None = None, period_end: datetime | None = None, timezone_name: str = "Asia/Yerevan") -> dict:
    """Aggregate operational facts; unavailable measurements stay None, never fake zero."""
    import json
    from zoneinfo import ZoneInfo
    from sqlalchemy import or_
    from app.database.models import AppSetting, UserQuestion
    from app.database.system_models import BackupHistory, SystemDiagnosticRun
    from app.services.admin_dashboard_service import dashboard_metrics, _count
    from app.services.analytics_snapshot_service import count_verified_users, task_attention_condition
    from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus

    end = period_end or now
    since = period_start or end - timedelta(days=days)
    if any(value.tzinfo is None for value in (now, since, end)) or since >= end:
        raise ValueError('Report window must be timezone-aware with start before end')
    now, since, end = (value.astimezone(timezone.utc) for value in (now, since, end))
    local_date = end.astimezone(ZoneInfo(timezone_name)).date()
    dashboard = (await dashboard_metrics(session)).values
    result = {key: dashboard[key] for key in ('users_total', 'users_pending', 'projects_review', 'tasks_open', 'questions')}
    result.update(await _management_period_facts(session, since, end, timezone_name))
    result['comparison'] = await _management_period_facts(session, since-(end-since), since, timezone_name)
    result['applications_rejected'] = await _count(session, User, User.application_status == ApplicationStatus.REJECTED, User.is_archived.is_(False))
    result['applications_approved'] = dashboard['users_approved']
    result['projects_active'] = dashboard['projects_active']
    for window in (1, 7, 30):
        result[f'active_{window}'] = await count_verified_users(session, end-timedelta(days=window), end)
    result['events_upcoming'] = await _count(session, Event, Event.event_date >= local_date,
        Event.event_date <= local_date + timedelta(days=7), Event.status.not_in((EventStatus.DRAFT, EventStatus.CANCELLED, EventStatus.PENDING_APPROVAL)))
    review = (ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW)
    result['projects_overdue'] = await _count(session, Project, Project.status.in_(review), Project.submitted_at <= now - timedelta(hours=72))
    result['tasks_open'] = await _count(session, Task, Task.status.in_((TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.OVERDUE)))
    result['tasks_overdue'] = await _count(session, Task, Task.status.in_((TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.OVERDUE)),
                                           or_(Task.deadline < now, Task.status == TaskStatus.OVERDUE))
    result['tasks_attention'] = await _count(session, Task, task_attention_condition(now))
    result['questions'] = await _count(session, UserQuestion, UserQuestion.status.in_(['new', 'open', 'thread_waiting', 'answer_failed', 'answer_review']))
    result['questions_overdue'] = await _count(session, UserQuestion, or_(
        UserQuestion.status.in_(('new', 'open')) & (UserQuestion.created_at <= now - timedelta(hours=24)),
        (UserQuestion.status == 'thread_waiting') & (UserQuestion.waiting_since <= now - timedelta(hours=24))))
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
    latest = await session.scalar(select(SystemDiagnosticRun).order_by(SystemDiagnosticRun.created_at.desc(), SystemDiagnosticRun.id.desc()).limit(1))
    heartbeat = await session.scalar(select(SystemDiagnosticRun).where(SystemDiagnosticRun.run_type == 'heartbeat')
                                    .order_by(SystemDiagnosticRun.created_at.desc(), SystemDiagnosticRun.id.desc()).limit(1))
    def observed_at(value):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    health_at = observed_at(latest.created_at) if latest else None
    heartbeat_at = observed_at(heartbeat.created_at) if heartbeat else None
    result['health'] = latest.status if latest else 'нет данных'
    result['health_score'] = latest.score if latest else None
    result['health_checked_at'] = health_at.isoformat() if health_at else None
    result['health_fresh'] = bool(health_at and timedelta(0) <= now - health_at <= timedelta(minutes=30))
    result['scheduler_checked_at'] = heartbeat_at.isoformat() if heartbeat_at else None
    result['scheduler'] = ('работает' if timedelta(0) <= now - heartbeat_at <= timedelta(minutes=30)
                           else 'нет свежего heartbeat') if heartbeat_at else 'нет данных'
    backup = await session.scalar(select(BackupHistory).where(BackupHistory.status == 'success', BackupHistory.restore_verified_at.is_not(None))
                                  .order_by(BackupHistory.restore_verified_at.desc(), BackupHistory.id.desc()).limit(1))
    latest_backup = await session.scalar(select(BackupHistory).order_by(BackupHistory.created_at.desc(), BackupHistory.id.desc()).limit(1))
    verified = observed_at(backup.restore_verified_at) if backup else None
    result['backup'] = ('восстановление проверено' if timedelta(0) <= now - verified <= timedelta(hours=24)
                        else 'проверенная копия старше 24 ч') if verified else 'нет проверенных данных'
    result['backup_verified_at'] = verified.isoformat() if verified else None
    copied_at = observed_at(backup.completed_at) if backup else None
    result['backup_completed_at'] = copied_at.isoformat() if copied_at else None
    result['backup_size_bytes'] = backup.size_bytes if backup else None
    result['backup_last_status'] = latest_backup.status if latest_backup else None
    last_attempt_at = observed_at(latest_backup.completed_at or latest_backup.created_at) if latest_backup else None
    result['backup_last_attempt_at'] = last_attempt_at.isoformat() if last_attempt_at else None
    from app.services.book_club_service import literature_stats
    literature = await literature_stats(session)
    result.update(literature_subscribers=literature['subscribed'], literature_active=literature['active'],
                  literature_reads_total=literature['read_marks'], literature_tasks_total=literature['task_marks'])
    result['as_of'] = now.isoformat()
    result['period_days'] = days
    result['period_start'] = since.isoformat()
    result['period_end'] = end.isoformat()
    return result


def management_report_attention(metrics: dict) -> list[str]:
    """Keep every actionable warning; healthy diagnostics belong in details."""
    warnings = []
    for key, label in (
        ('tasks_overdue', 'Разобрать просроченные задачи'),
        ('questions_overdue', 'Ответить на обращения'),
        ('users_pending', 'Рассмотреть заявки'),
        ('projects_overdue', 'Рассмотреть проекты'),
        ('delivery_errors', 'Проверить ошибки доставки'),
    ):
        if metrics.get(key):
            warnings.append(f'{label}: {int(metrics[key])}')
    if not metrics.get('health_fresh') or metrics.get('health') not in {'ok', 'healthy'}:
        warnings.append('Проверить состояние сервиса: нет свежей успешной проверки')
    if metrics.get('scheduler') != 'работает':
        warnings.append('Проверить работу планировщика')
    if metrics.get('backup') != 'восстановление проверено' or metrics.get('backup_last_status') not in {None, 'success', 'pending', 'running'}:
        warnings.append('Проверить резервное копирование')
    return warnings


def management_report_text(metrics: dict, *, title: str = 'Итоги за сутки', previous: dict | None = None) -> str:
    """Comparable flows use an equal SQL window, never a prior stock snapshot."""
    from html import escape
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('Europe/Moscow')
    end = datetime.fromisoformat(metrics['period_end']).astimezone(zone)
    start = datetime.fromisoformat(metrics['period_start']).astimezone(zone)
    comparison = metrics.get('comparison', {})

    def flow(key):
        current = metrics.get(key)
        if current is None:
            return 'нет данных'
        old = comparison.get(key)
        return str(current) if old is None else f'{current} ({current-old:+d})'

    attention = management_report_attention(metrics)
    text = (f'📊 <b>ЭРА · {escape(title)}</b>\n'
            f'{start:%d.%m %H:%M} — {end:%d.%m %H:%M} МСК\n\n'
            '<b>Требует решения</b>\n'
            + ('\n'.join('• ' + line for line in attention) or 'Срочных отклонений по измеряемым показателям нет.')
            + '\n\n<b>Участники</b>\n'
            f"Действующих сейчас: {metrics['users_total']}\n"
            f"Новых одобрено: {flow('new_members')}\n"
            f"С подтверждённым результатом: {flow('active_period')}\n\n"
            '<b>Результаты за период</b>\n'
            f"Проведено мероприятий: {flow('events_held')}\n"
            f"Подтверждено посещений: {flow('attended')}\n"
            f"Принято заданий: {flow('task_results')}\n"
            f"Проектов в работе сейчас: {metrics.get('projects_active', 'нет данных')}\n"
            f"Открытых задач сейчас: {metrics['tasks_open']}\n\n")
    return text + ('<i>В скобках — изменение к предыдущему равному периоду. '
                   'Мероприятия — за полные локальные дни; активность — по подтверждённым результатам.</i>'
                   if comparison else '<i>Сравнение с предыдущим периодом: нет данных.</i>')


def management_report_details_text(metrics: dict, *, title: str = 'Все показатели', previous: dict | None = None) -> str:
    from html import escape
    from zoneinfo import ZoneInfo

    def value(key):
        return 'не измеряется' if metrics.get(key) is None else escape(str(metrics[key]))

    def local_time(raw):
        if not raw:
            return 'нет данных'
        moment = datetime.fromisoformat(raw)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M МСК')

    health_names = {'healthy': 'в норме', 'ok': 'в норме', 'warning': 'требует внимания',
                    'error': 'ошибка', 'critical': 'критично', 'failed': 'ошибка'}
    fresh = metrics.get('health_fresh', False)
    healthy = fresh and metrics.get('health') in {'healthy', 'ok'}
    health = health_names.get(metrics.get('health'), 'нет данных')
    if not fresh:
        health = 'нет свежей проверки' if metrics.get('health_checked_at') else 'нет данных'
    health_icon = '🟢' if healthy else '🔴' if fresh and metrics.get('health') in {'critical', 'error', 'failed'} else '🟡'
    scheduler_ok = metrics.get('scheduler') == 'работает'
    backup_ok = metrics.get('backup') == 'восстановление проверено'
    backup_last_bad = metrics.get('backup_last_status') not in {None, 'success', 'pending', 'running'}
    backup_in_progress = metrics.get('backup_last_status') in {'pending', 'running'}
    window = ' — '.join(
        datetime.fromisoformat(metrics[key]).astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m %H:%M')
        for key in ('period_start', 'period_end')
    )
    text = (f'📊 <b>ЭРА · {escape(title)}</b>\n'
        f'<i>Данные на {local_time(metrics["as_of"])}</i>\n'
        f'Период: {window} МСК\n\n'
        '<b>👥 Участники и заявки</b>\n'
        f"Участников: {value('users_total')} · новых профилей: {value('profiles_new')}\n"
        f"Заявки: ожидают {value('users_pending')} · одобрено {value('applications_approved')} · отклонено {value('applications_rejected')}\n"
        f"Подтверждённо активны за 24 ч / 7 д / 30 д: {value('active_1')} / {value('active_7')} / {value('active_30')}\n"
        f"Первых одобрений за период: {value('new_members')} · активных за период: {value('active_period')}\n\n"
        '<b>📅 Мероприятия и работа команды</b>\n'
        f"Мероприятий на 7 дней: {value('events_upcoming')} · регистраций за период: {value('registrations_new')} · посещений: {value('attended')}\n"
        f"Проекты: на рассмотрении {value('projects_review')} · дольше 72 ч {value('projects_overdue')} · в работе {value('projects_active')}\n"
        f"Проведено мероприятий: {value('events_held')} · принято заданий: {value('task_results')}\n"
        f"Задачи: открыто {value('tasks_open')} · просрочено {value('tasks_overdue')}\n"
        f"Обращения: ждут {value('questions')} · дольше 24 ч {value('questions_overdue')}\n\n"
        '<b>🎮 Досуг и уведомления</b>\n'
        f"Игры за период: игроков {value('game_players')} · завершено {value('games_completed')}\n"
        f"Литература: подписчиков сейчас {value('literature_subscribers')} · участников с отметками за всё время {value('literature_active')}\n"
        f"Отметок чтения: {value('literature_reads_total')} · выполненных заданий: {value('literature_tasks_total')}\n"
        f"Автоуведомления: доставлено {value('delivered')} · ошибок {value('delivery_errors')}\n\n"
        '<b>🩺 Здоровье бота</b>\n'
        f'{health_icon} Состояние: {health}\n'
        f"Проверка: {local_time(metrics.get('health_checked_at'))}\n"
        f"{'🟢' if scheduler_ok else '🟡'} Планировщик: {value('scheduler')}\n"
        f"Последний сигнал: {local_time(metrics.get('scheduler_checked_at'))}\n\n"
        '<b>💾 Резервная копия</b>\n'
        f"{'🟢' if backup_ok and not backup_last_bad and not backup_in_progress else '🟡'} {value('backup')}\n"
        f"Копия создана: {local_time(metrics.get('backup_completed_at'))}\n"
        f"Восстановление проверено: {local_time(metrics.get('backup_verified_at'))}\n")
    if metrics.get('backup_size_bytes') is not None:
        text += f"Размер копии: {metrics['backup_size_bytes'] / (1024 * 1024):.2f} МБ\n"
    if backup_last_bad or backup_in_progress:
        backup_status = {'failed': 'ошибка', 'pending': 'выполняется', 'running': 'выполняется'}.get(metrics['backup_last_status'], 'не подтверждена')
        text += f"Последняя попытка: {backup_status} · {local_time(metrics.get('backup_last_attempt_at'))}\n"
    if metrics.get('game_coverage_since'):
        text += '\nИгровая статистика ведётся с ' + datetime.fromisoformat(metrics['game_coverage_since']).strftime('%d.%m.%Y') + '.\n'
    text += '\nМероприятия считаются за полные локальные календарные дни; посещения — по времени подтверждения.\n'
    if metrics.get('comparison'):
        text += '\n<b>К предыдущему равному периоду</b>\n'
        for key, label in (('new_members', 'Новые одобрения'), ('active_period', 'Подтверждённо активные'), ('events_held', 'Мероприятия'), ('attended', 'Посещения'), ('task_results', 'Принятые задания')):
            text += f"{label}: {metrics[key] - metrics['comparison'][key]:+d}\n"
    text += '\n<b>Требует внимания</b>\n' + ('\n'.join(management_report_attention(metrics)) or 'Срочных действий нет.')
    return text


def management_report_markup(miniapp_url: str = '', *, days: int = 1, details: bool = False):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    def button(text, action):
        return InlineKeyboardButton(text=text, callback_data=action)
    rows = [
        [button('Заявки', 'admin:applications'), button('Обращения', 'admin:questions')],
        [button('Задачи требуют внимания', 'admin:taskattention:page:0'), button('Проекты', 'admin:projects')],
        [button('Сутки', 'admin:management:view:1:overview'), button('7 дней', 'admin:management:view:7:overview'), button('30 дней', 'admin:management:view:30:overview')],
        [button('Кратко' if details else 'Все показатели и диагностика', f"admin:management:view:{days}:{'overview' if details else 'details'}")],
        [button('Excel', f'admin:management:view:{days}:excel'), button('Обновить', f"admin:management:view:{days}:{'details' if details else 'overview'}")],
    ]
    if miniapp_url:
        rows.append([InlineKeyboardButton(text='Открыть ЭРА', web_app=WebAppInfo(url=miniapp_url))])
    rows.append([button('← Управление', 'admin:panel')])
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
    """One automatic daily issue; weekly/monthly summaries stay on demand."""
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
    stamp = local.date().isoformat()
    key = f'management-report:daily:{stamp}'
    async with session_factory() as session:
        recipients = await management_report_recipients(session, settings)
    if not recipients:
        return
    async with session_factory() as session:
        if session.bind.dialect.name == 'postgresql':
            lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
        row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
        if row:
            payload = json.loads(row.value) if isinstance(row.value, str) else row.value
        else:
            metrics = await build_management_report(session, now=now, timezone_name=settings.timezone)
            previous_stamp = (local.date() - timedelta(days=1)).isoformat()
            previous_row = await session.scalar(select(AppSetting).where(AppSetting.key == f'management-report:daily:{previous_stamp}'))
            previous_payload = (json.loads(previous_row.value) if isinstance(previous_row.value, str) else previous_row.value) if previous_row else None
            previous = previous_payload.get('metrics') if previous_payload else None
            payload = {'metrics': metrics, 'text': management_report_text(metrics, previous=previous)}
            session.add(AppSetting(key=key, value=json.dumps(payload, ensure_ascii=False)))
            await session.commit()
    for recipient in sorted(recipients):
        await safe_send_once(bot, settings, recipient, payload['text'], delivery_key=f'daily:{stamp}:{recipient}',
                             notification_type='management_report', parse_mode='HTML',
                             reply_markup=management_report_markup(settings.effective_miniapp_url))


@dataclass(frozen=True)
class ScopedLeaderOperations:
    active_tasks: int
    completed_tasks: int
    overdue_tasks: int
    awaiting_review: int
    verified_results: int
    previous_results: int
    workload: tuple[tuple[str, int], ...]
    month_goals: tuple[tuple[str, int | float, int | float | None], ...]


async def build_scoped_leader_operations(session: AsyncSession, actor: User, settings, *, now=None) -> ScopedLeaderOperations:
    """Current task-management authority bounds every query, never role alone."""
    from app.services import leaders_access_service as access
    if actor is None:
        raise PermissionError('Нет полномочий руководителя')
    await session.refresh(actor, attribute_names=['role', 'is_archived', 'is_blocked', 'permission_grants'])
    scopes = await access.scopes(session, actor, settings, 'tasks.manage')
    if not scopes:
        raise PermissionError('Нет полномочий руководителя')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    departments = [ident for kind, ident in scopes if kind == 'department']
    directions = [ident for kind, ident in scopes if kind == 'direction']
    global_access = ('global', 0) in scopes
    zone = True if global_access else or_(Task.department_id.in_(departments), Task.direction_id.in_(directions))
    active = Task.status.in_(['new', 'published', 'in_progress', 'review', 'overdue'])
    pending = select(TaskSubmission.id).where(TaskSubmission.task_id == Task.id, TaskSubmission.status == 'pending').exists()
    counts = (await session.execute(select(
        func.count().filter(active),
        func.count().filter(Task.status == 'completed'),
        func.count().filter(active & or_(Task.status == 'overdue', Task.deadline < now)),
        func.count().filter(active & or_(Task.status == 'review', pending)),
    ).select_from(Task).where(zone))).one()

    async def results(start, end):
        return int(await session.scalar(select(func.count(func.distinct(TaskSubmission.id)))
            .join(Task, Task.id == TaskSubmission.task_id)
            .join(AuditLog, and_(AuditLog.entity_type == 'task_submission', AuditLog.entity_id == TaskSubmission.id))
            .where(zone, TaskSubmission.status == 'approved', AuditLog.action == 'task.submission_approve',
                   AuditLog.created_at >= start, AuditLog.created_at < end)) or 0)

    grouped = (await session.execute(select(Task.assignee_id, func.count()).where(zone, active)
                                     .group_by(Task.assignee_id))).all()
    ids = [ident for ident, _ in grouped if ident is not None]
    people = (await session.scalars(select(User).where(User.id.in_(ids), *roster_conditions()))).all() if ids else []
    names = {person.id: ' '.join(part for part in [person.first_name, person.last_name] if part) for person in people}
    workload = tuple(sorted(((names.get(ident, 'Без исполнителя' if ident is None else 'Недоступный участник'), count)
                             for ident, count in grouped), key=lambda row: row[0]))
    from zoneinfo import ZoneInfo
    month = now.astimezone(ZoneInfo(settings.timezone)).strftime('%Y-%m')
    goal_scope = True if global_access else or_(
        and_(MonthlyGoal.scope_type == 'department', MonthlyGoal.scope_id.in_(departments)),
        and_(MonthlyGoal.scope_type == 'direction', MonthlyGoal.scope_id.in_(directions)),
    )
    goals = tuple((await session.execute(select(MonthlyGoal.title, MonthlyGoal.current_value, MonthlyGoal.target_value)
        .where(goal_scope, MonthlyGoal.month == month, MonthlyGoal.status != 'deleted').order_by(MonthlyGoal.title))).all())
    leadership_scope = True if global_access else or_(
        and_(LeadershipGoal.scope_type == 'department', LeadershipGoal.scope_id.in_(departments)),
        and_(LeadershipGoal.scope_type == 'direction', LeadershipGoal.scope_id.in_(directions)),
    )
    local_today = now.astimezone(ZoneInfo(settings.timezone)).date()
    leadership_goals = (await session.execute(select(LeadershipGoal.title, LeadershipGoal.progress, LeadershipGoal.target)
        .where(leadership_scope, LeadershipGoal.period_type == 'month',
               LeadershipGoal.period_start <= local_today, LeadershipGoal.period_end >= local_today,
               LeadershipGoal.status != 'deleted').order_by(LeadershipGoal.title))).all()
    goals += tuple(leadership_goals)
    return ScopedLeaderOperations(*map(int, counts), await results(now-timedelta(days=30), now),
                                  await results(now-timedelta(days=60), now-timedelta(days=30)), workload, goals)
