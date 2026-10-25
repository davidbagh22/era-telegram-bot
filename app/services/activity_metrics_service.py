"""Per-user activity counters (ActivityMetric) -- Points/Ranks ToR sections
18, 22, 24-26, phase 2. These back rank progression and Opportunity
eligibility checks in later phases; this module only reads/writes the
counters themselves. Always go through increment_metric to change a value
-- never set ActivityMetric.value directly -- so every change stays
traceable to whichever verified activity caused it
(app.services.activity_scoring_service is the only caller in practice)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ActivityMetric


async def increment_metric(
    session: AsyncSession, *, user_id: int, metric_key: str, delta: int
) -> ActivityMetric:
    if delta == 0:
        return await _get_or_create(session, user_id=user_id, metric_key=metric_key)
    row = await _get_or_create(session, user_id=user_id, metric_key=metric_key)
    row.value += delta
    await session.flush()
    return row


async def _get_or_create(session: AsyncSession, *, user_id: int, metric_key: str) -> ActivityMetric:
    row = await session.scalar(
        select(ActivityMetric).where(
            ActivityMetric.user_id == user_id, ActivityMetric.metric_key == metric_key
        )
    )
    if row is None:
        row = ActivityMetric(user_id=user_id, metric_key=metric_key, value=0)
        session.add(row)
        await session.flush()
    return row


async def get_metric(session: AsyncSession, *, user_id: int, metric_key: str) -> int:
    value = await session.scalar(
        select(ActivityMetric.value).where(
            ActivityMetric.user_id == user_id, ActivityMetric.metric_key == metric_key
        )
    )
    return int(value or 0)


async def get_all_metrics(session: AsyncSession, *, user_id: int) -> dict[str, int]:
    rows = await session.scalars(select(ActivityMetric).where(ActivityMetric.user_id == user_id))
    return {row.metric_key: row.value for row in rows}
