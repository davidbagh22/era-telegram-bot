"""Verified-activity scoring engine -- Points/Ranks ToR ("ERA Platform —
ранги, баллы, автоматическое начисление и «Возможности»") sections 16-20,
22-23, phase 2.

`record_verified_activity()` is the ToR's single "activity.verified" domain
event (section 22): one confirmed action becomes one PointTransaction and
its ActivityMetric bumps, together, exactly once -- callers never update
points and metrics separately, and a retry (webhook redelivery, admin
re-running an award pass, a double click) never double-pays or double-counts
(section 23).

`score_event_attendance` / `score_event_role_bonus` apply the Event Scoring
Profile (sections 16-20) on top of that: attendance keeps paying exactly
what `Event.points_for_visit` always paid (no value change), it just also
bumps `events_attended` now; any role beyond plain participant additionally
gets its own bonus + whatever activity metrics the event's scoring preset
says it should. Every award is independently idempotent, so calling
`score_event_role_bonus` for someone with no special role, or calling it
twice, is always a safe no-op / no-double-pay.

Wired into the two attendance-confirmation paths that matter for current
usage: `event_registration_service.award_attendance_points` (Mini App admin
bulk award) and `event_attendance_service.confirm_attendance` (the
participant self-service code flow). The legacy /panel handlers
(`app/handlers/admin/panel.py`, `app/handlers/admin/event_registration_block14.py`)
still pay the base attendance amount under the same idempotency key -- so no
double-pay risk either way -- but don't yet call into role/preset scoring;
that's an accepted gap for what's explicitly documented elsewhere as an
emergency fallback, not the primary path.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, PointTransaction, User
from app.services.activity_metrics_service import increment_metric
from app.services.points_service import add_points
from app.utils.constants import (
    EVENT_ROLE_METRIC,
    EVENT_ROLE_POINTS,
    EVENT_SCORING_PRESET_METRICS,
    VOLUNTEER_HOURLY_POINTS,
    VOLUNTEER_HOURS_POINTS_CAP,
    EventParticipantRole,
    PointCategory,
)


async def record_verified_activity(
    session: AsyncSession,
    *,
    user_id: int,
    points: int,
    reason: str,
    category: str,
    source_type: str,
    source_id: int | None,
    idempotency_key: str,
    approved_by: int | None,
    related_event_id: int | None = None,
    related_task_id: int | None = None,
    related_project_id: int | None = None,
    metric_updates: dict[str, int] | None = None,
) -> PointTransaction:
    existing = await session.scalar(
        select(PointTransaction).where(PointTransaction.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    transaction = await add_points(
        session,
        user_id=user_id,
        points=points,
        reason=reason,
        approved_by=approved_by,
        category=category,
        source_type=source_type,
        source_id=source_id,
        idempotency_key=idempotency_key,
        related_event_id=related_event_id,
        related_task_id=related_task_id,
        related_project_id=related_project_id,
    )
    for metric_key, delta in (metric_updates or {}).items():
        await increment_metric(session, user_id=user_id, metric_key=metric_key, delta=delta)
    return transaction


async def score_event_attendance(
    session: AsyncSession, event: Event, registration: EventRegistration, participant: User, *, approved_by_id: int | None
) -> PointTransaction:
    """Base attendance award -- same amount, same idempotency key
    (`event_attendance:{event}:{user}`) every other attendance-award call
    site already uses, so this is a drop-in replacement, not a new payout.
    The only change is it now also bumps `events_attended`."""
    return await record_verified_activity(
        session,
        user_id=participant.id,
        points=event.points_for_visit,
        reason=f"Посещение мероприятия: {event.title}",
        category=PointCategory.EVENT,
        source_type="event_attendance",
        source_id=registration.id,
        idempotency_key=f"event_attendance:{event.id}:{participant.id}",
        approved_by=approved_by_id,
        related_event_id=event.id,
        metric_updates={"events_attended": 1},
    )


async def score_event_role_bonus(
    session: AsyncSession,
    event: Event,
    registration: EventRegistration,
    participant: User,
    *,
    approved_by_id: int | None,
) -> PointTransaction | None:
    """Role bonus on top of attendance (ToR section 19-20). No-op for the
    default PARTICIPANT role. Call this after `score_event_attendance` (or
    any attendance-award path) once a registration has ATTENDED status."""
    role = registration.role or EventParticipantRole.PARTICIPANT
    if role == EventParticipantRole.PARTICIPANT:
        return None

    # dict.fromkeys(..., 1) rather than incrementing on top of it below: a
    # role's own metric can be the same key the preset already lists (e.g.
    # a speaker at a LEADERSHIP-preset event maps to leadership_activities
    # from both sides) -- that's still just one occurrence of the activity,
    # so each key is *set* to 1 once, never stacked to 2.
    #
    # event.scoring_metrics is the per-event, admin-editable checkbox list
    # (ToR section 18); it's prefilled from the preset at creation time, so
    # this only falls back to the preset's own default for events created
    # before this column existed (where it's still the default empty list).
    preset_metrics = event.scoring_metrics or EVENT_SCORING_PRESET_METRICS.get(event.scoring_preset, [])
    metric_updates: dict[str, int] = dict.fromkeys(preset_metrics, 1)
    role_metric = EVENT_ROLE_METRIC.get(role)
    if role_metric:
        metric_updates[role_metric] = 1

    if role == EventParticipantRole.VOLUNTEER:
        hours = max(0, int(registration.volunteer_hours or 0))
        if not hours:
            return None
        points = min(hours * VOLUNTEER_HOURLY_POINTS, VOLUNTEER_HOURS_POINTS_CAP)
        metric_updates["volunteer_hours"] = hours
        metric_updates["volunteer_activities"] = 1
        return await record_verified_activity(
            session,
            user_id=participant.id,
            points=points,
            reason=f"Волонтёрство на мероприятии «{event.title}» ({hours} ч.)",
            category=PointCategory.VOLUNTEERING,
            source_type="event_scoring_volunteer",
            source_id=registration.id,
            idempotency_key=f"event_scoring:{event.id}:user:{participant.id}:volunteer",
            approved_by=approved_by_id,
            related_event_id=event.id,
            metric_updates=metric_updates,
        )

    points = EVENT_ROLE_POINTS.get(role, 0)
    if not points and not metric_updates:
        return None
    return await record_verified_activity(
        session,
        user_id=participant.id,
        points=points,
        reason=f"Роль на мероприятии «{event.title}»: {role}",
        category=PointCategory.EVENT,
        source_type="event_scoring_role",
        source_id=registration.id,
        idempotency_key=f"event_scoring:{event.id}:user:{participant.id}:role:{role}",
        approved_by=approved_by_id,
        related_event_id=event.id,
        metric_updates=metric_updates,
    )


async def score_event_attendance_and_role(
    session: AsyncSession, event: Event, registration: EventRegistration, participant: User, *, approved_by_id: int | None
) -> list[PointTransaction]:
    """Convenience wrapper for the two attendance-confirmation call sites:
    base attendance + role bonus, in one call."""
    awarded = [await score_event_attendance(session, event, registration, participant, approved_by_id=approved_by_id)]
    role_award = await score_event_role_bonus(session, event, registration, participant, approved_by_id=approved_by_id)
    if role_award is not None:
        awarded.append(role_award)
    return awarded
