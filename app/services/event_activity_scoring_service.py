from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EventActivity, EventActivitySubmission, PointTransaction, User
from app.services.activity_scoring_service import record_verified_activity
from app.utils.constants import PointCategory


async def score_event_activity_completion(
    session: AsyncSession,
    *,
    activity: EventActivity,
    submission: EventActivitySubmission,
    participant: User,
    approved_by_id: int | None,
) -> PointTransaction:
    """Verified post-event activity -> one canonical scoring transaction.

    Post-event proofs used to call ``add_points`` directly. That updated the
    ledger but skipped the verified-activity side effects used by the rest of
    ERA Platform: activity metrics, rank recalculation and participation
    lifecycle/reactivation. Keep the source idempotent on the submission id.
    """
    return await record_verified_activity(
        session,
        user_id=participant.id,
        points=max(0, int(activity.points or 0)),
        reason=f"Активность после мероприятия: {activity.title}",
        category=PointCategory.EVENT,
        source_type="event_activity",
        source_id=submission.id,
        idempotency_key=f"event_activity:{submission.id}:approval",
        approved_by=approved_by_id,
        related_event_id=activity.event_id,
        metric_updates={"event_activities": 1},
    )
