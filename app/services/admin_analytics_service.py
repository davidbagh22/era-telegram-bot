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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import (
    Department,
    Direction,
    Event,
    PointTransaction,
    Project,
    User,
    UserDepartment,
    UserDirection,
)


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
