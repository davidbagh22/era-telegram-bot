"""Monthly goals CRUD — shared by the bot's "🎯 Ежемесячные цели" flow
(app/handlers/admin/management_ready.py) and the Mini App's admin tools.

Extracted so both surfaces parse/validate/mutate goals identically before
the bot's /panel tree is retired (see docs/BOT_VS_MINIAPP_AUDIT.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import MonthlyGoal
from app.database.models import Department, Direction

GOAL_ACTIONS = {"inc", "done", "delete"}


class GoalError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class GoalOut:
    id: int
    month: str
    title: str
    target_value: int
    current_value: int
    status: str
    scope_type: str
    scope_name: str | None


async def _scope_name(session: AsyncSession, scope_type: str, scope_id: int | None) -> str | None:
    if scope_type == "department" and scope_id:
        department = await session.get(Department, scope_id)
        return department.name if department else None
    if scope_type == "direction" and scope_id:
        direction = await session.get(Direction, scope_id)
        return direction.name if direction else None
    return None


async def goal_out(session: AsyncSession, goal: MonthlyGoal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        month=goal.month,
        title=goal.title,
        target_value=goal.target_value,
        current_value=goal.current_value,
        status=goal.status,
        scope_type=goal.scope_type,
        scope_name=await _scope_name(session, goal.scope_type, goal.scope_id),
    )


async def list_goals(session: AsyncSession) -> list[GoalOut]:
    goals = (
        await session.scalars(
            select(MonthlyGoal)
            .where(MonthlyGoal.status != "deleted")
            .order_by(MonthlyGoal.month.desc(), MonthlyGoal.created_at.desc())
            .limit(50)
        )
    ).all()
    return [await goal_out(session, goal) for goal in goals]


async def _resolve_scope(session: AsyncSession, scope_query: str | None) -> tuple[str, int | None]:
    if not scope_query or not scope_query.strip():
        return "global", None
    query = scope_query.strip().casefold()
    department = await session.scalar(select(Department).where(func.lower(Department.name).contains(query)))
    direction = await session.scalar(select(Direction).where(func.lower(Direction.name).contains(query)))
    if direction:
        return "direction", direction.id
    if department:
        return "department", department.id
    return "global", None


async def create_goal(
    session: AsyncSession,
    *,
    title: str,
    target_value: int,
    month: str | None,
    scope_query: str | None,
    timezone: str,
    updated_by: int | None,
) -> MonthlyGoal:
    title = title.strip()[:255]
    if not title:
        raise GoalError("title_required")
    if target_value <= 0:
        raise GoalError("invalid_target")
    resolved_month = month.strip() if month and month.strip() else datetime.now(ZoneInfo(timezone)).strftime("%Y-%m")
    scope_type, scope_id = await _resolve_scope(session, scope_query)
    goal = MonthlyGoal(
        month=resolved_month,
        title=title,
        target_value=target_value,
        scope_type=scope_type,
        scope_id=scope_id,
        updated_by=updated_by,
    )
    session.add(goal)
    await session.flush()
    return goal


async def decide_goal(session: AsyncSession, goal_id: int, action: str, updated_by: int | None) -> MonthlyGoal:
    if action not in GOAL_ACTIONS:
        raise GoalError("invalid_action")
    goal = await session.get(MonthlyGoal, goal_id)
    if goal is None:
        raise GoalError("goal_not_found")
    if action == "inc":
        goal.current_value += 1
    elif action == "done":
        goal.current_value = max(goal.current_value, goal.target_value)
        goal.status = "done"
    else:
        goal.status = "deleted"
    goal.updated_by = updated_by
    await session.flush()
    return goal
