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
