from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, UserOffice

# Only verified operational activity belongs in Active Base.  Digital points,
# registration, profile completion, referrals by themselves, manual reputation
# adjustments and passive membership are deliberately absent.
MEANINGFUL_POINT_SOURCE_TYPES = frozenset(
    {
        "event_attendance",
        "event_scoring_volunteer",
        "event_scoring_role",
        "event_activity",
        "task_completion",
        "project_contribution",
        "project_milestone",
        "project_completion",
        "project_lead_result",
    }
)


def meaningful_points_condition():
    """Reusable SQL condition for verified operational point transactions."""
    return PointTransaction.source_type.in_(MEANINGFUL_POINT_SOURCE_TYPES)


async def meaningful_user_ids_since(
    session: AsyncSession,
    cutoff: datetime,
    *,
    include_current_responsibility: bool = True,
) -> set[int]:
    """Return users with recent verified activity or a current responsibility.

    A current office assignment counts because the MASTER lifecycle defines
    ACTIVE as a meaningful action in the recent window *or* a current
    responsibility. Merely belonging to a department/direction never counts.
    """
    ids = set(
        (
            await session.scalars(
                select(PointTransaction.user_id)
                .where(
                    PointTransaction.created_at >= cutoff,
                    meaningful_points_condition(),
                )
                .distinct()
            )
        ).all()
    )
    if include_current_responsibility:
        ids.update(
            (
                await session.scalars(
                    select(UserOffice.user_id)
                    .where(UserOffice.is_active.is_(True))
                    .distinct()
                )
            ).all()
        )
    return {int(user_id) for user_id in ids}


async def meaningful_count_since(
    session: AsyncSession,
    cutoff: datetime,
    *,
    include_current_responsibility: bool = True,
) -> int:
    return len(
        await meaningful_user_ids_since(
            session,
            cutoff,
            include_current_responsibility=include_current_responsibility,
        )
    )


async def last_meaningful_activity_at(
    session: AsyncSession,
    user_id: int,
) -> datetime | None:
    """Last verified operational action; excludes title/membership itself."""
    return await session.scalar(
        select(func.max(PointTransaction.created_at)).where(
            PointTransaction.user_id == user_id,
            meaningful_points_condition(),
        )
    )


async def has_current_responsibility(session: AsyncSession, user_id: int) -> bool:
    return bool(
        await session.scalar(
            select(UserOffice.id).where(
                UserOffice.user_id == user_id,
                UserOffice.is_active.is_(True),
            ).limit(1)
        )
    )
