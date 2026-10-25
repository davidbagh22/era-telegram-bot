from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LeadershipGoal
from app.services.audit_service import audit
from app.utils.constants import LeadershipGoalStatus

# Leadership OS ToR sections 32-33: organization-level and leader-level
# goals share this one table (LeadershipGoal), told apart by scope_type
# ("global" for org goals, "club"/"direction"/etc for a leader's own).


async def create_goal(
    session: AsyncSession,
    *,
    owner_id: int,
    created_by: int,
    title: str,
    period_start: date,
    period_end: date,
    scope_type: str = "global",
    scope_id: int | None = None,
    period_type: str = "month",
    metric: str | None = None,
    target: float | None = None,
    office_assignment_id: int | None = None,
) -> LeadershipGoal:
    goal = LeadershipGoal(
        owner_id=owner_id,
        created_by=created_by,
        office_assignment_id=office_assignment_id,
        scope_type=scope_type,
        scope_id=scope_id,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        title=title.strip()[:255],
        metric=(metric or "").strip()[:150] or None,
        target=target,
    )
    session.add(goal)
    await session.flush()
    await audit(
        session,
        actor_id=created_by,
        action="leadership_goal.created",
        entity_type="leadership_goal",
        entity_id=goal.id,
        old_value=None,
        new_value={"owner_id": owner_id, "title": goal.title},
    )
    return goal


async def list_goals(
    session: AsyncSession,
    *,
    owner_id: int | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
    active_only: bool = False,
) -> list[LeadershipGoal]:
    conditions = []
    if owner_id is not None:
        conditions.append(LeadershipGoal.owner_id == owner_id)
    if scope_type is not None:
        conditions.append(LeadershipGoal.scope_type == scope_type)
    if scope_id is not None:
        conditions.append(LeadershipGoal.scope_id == scope_id)
    if active_only:
        conditions.append(LeadershipGoal.status == LeadershipGoalStatus.ACTIVE)
    return list(
        (
            await session.scalars(
                select(LeadershipGoal)
                .where(*conditions)
                .order_by(LeadershipGoal.period_start.desc())
            )
        ).all()
    )


def _recompute_status(goal: LeadershipGoal, *, today: date) -> None:
    if goal.status == LeadershipGoalStatus.CANCELLED:
        return
    if goal.target is not None and goal.progress >= goal.target:
        goal.status = LeadershipGoalStatus.COMPLETED
        return
    if goal.status == LeadershipGoalStatus.COMPLETED:
        return
    goal.status = (
        LeadershipGoalStatus.OVERDUE if goal.period_end < today else LeadershipGoalStatus.ACTIVE
    )


async def update_progress(
    session: AsyncSession, goal: LeadershipGoal, *, progress: float, today: date | None = None
) -> LeadershipGoal:
    goal.progress = progress
    _recompute_status(goal, today=today or date.today())
    return goal


async def set_status(session: AsyncSession, goal: LeadershipGoal, *, status: str) -> LeadershipGoal:
    goal.status = status
    return goal


def progress_ratio(goal: LeadershipGoal) -> float | None:
    if not goal.target:
        return None
    return round(min(goal.progress / goal.target, 1.0) * 100, 1)
