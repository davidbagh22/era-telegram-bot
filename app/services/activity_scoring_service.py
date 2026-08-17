"""Single verified-activity scoring pipeline for ERA Platform.

Every real verified action enters through ``record_verified_activity`` so a
single idempotency key drives points, ActivityMetric counters and the existing
ParticipationStatus progression. Event, task and project helpers are adapters
onto that one pipeline; none of them creates a second points/rank engine.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    Project,
    ProjectMember,
    ProjectMilestone,
    Task,
    User,
)
from app.services.activity_metrics_service import increment_metric
from app.services.points_service import add_points
from app.services.progression_service import promote_participation_status
from app.utils.constants import (
    EVENT_ROLE_METRIC,
    EVENT_ROLE_POINTS,
    EVENT_SCORING_PRESET_METRICS,
    VOLUNTEER_HOURLY_POINTS,
    VOLUNTEER_HOURS_POINTS_CAP,
    EventParticipantRole,
    PointCategory,
    Role,
)

TASK_ACTIVITY_METRICS = {
    "project": "project_activities",
    "media": "media_activities",
    "volunteering": "volunteer_activities",
    "volunteer": "volunteer_activities",
    "social": "social_activities",
    "culture": "culture_activities",
    "leadership": "leadership_activities",
    "partner": "partner_activities",
    "representation": "representation_activities",
    "mentorship": "mentorship_activities",
}

# The multiplier applies only when the task itself is explicitly marked as
# role-scoped. Ordinary attendance, ordinary tasks and unrelated actions never
# receive a leadership multiplier merely because the user has a title.
ROLE_SCOPED_MULTIPLIERS = {
    Role.PARTICIPANT: 1.00,
    Role.ACTIVIST: 1.00,
    Role.LEADER: 1.10,
    Role.HEAD: 1.15,
    Role.COUNCIL: 1.15,
    Role.ADMIN: 1.15,
}

PROJECT_FIRST_CONTRIBUTION_POINTS = 50
PROJECT_MILESTONE_POINTS = 120
PROJECT_COMPLETION_POINTS = 250
PROJECT_LEAD_RESULT_POINTS = 150


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
        select(PointTransaction).where(
            PointTransaction.idempotency_key == idempotency_key
        )
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
        if delta:
            await increment_metric(
                session, user_id=user_id, metric_key=metric_key, delta=delta
            )
    await promote_participation_status(session, user_id=user_id)
    return transaction


async def score_event_attendance(
    session: AsyncSession,
    event: Event,
    registration: EventRegistration,
    participant: User,
    *,
    approved_by_id: int | None,
) -> PointTransaction:
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
    role = registration.role or EventParticipantRole.PARTICIPANT
    if role == EventParticipantRole.PARTICIPANT:
        return None

    preset_metrics = event.scoring_metrics or EVENT_SCORING_PRESET_METRICS.get(
        event.scoring_preset, []
    )
    metric_updates: dict[str, int] = dict.fromkeys(preset_metrics, 1)
    role_metric = EVENT_ROLE_METRIC.get(role)
    if role_metric:
        metric_updates[role_metric] = 1

    if role == EventParticipantRole.VOLUNTEER:
        hours = max(0, int(registration.volunteer_hours or 0))
        if not hours:
            return None
        points = min(
            hours * VOLUNTEER_HOURLY_POINTS, VOLUNTEER_HOURS_POINTS_CAP
        )
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
            idempotency_key=(
                f"event_scoring:{event.id}:user:{participant.id}:volunteer"
            ),
            approved_by=approved_by_id,
            related_event_id=event.id,
            metric_updates=metric_updates,
        )

    points = EVENT_ROLE_POINTS.get(role, 0)
    if not points and not metric_updates:
        return None
    category = PointCategory.MEDIA if role in {
        EventParticipantRole.MEDIA,
        EventParticipantRole.PHOTOGRAPHER,
        EventParticipantRole.VIDEOGRAPHER,
    } else PointCategory.EVENT
    return await record_verified_activity(
        session,
        user_id=participant.id,
        points=points,
        reason=f"Роль на мероприятии «{event.title}»: {role}",
        category=category,
        source_type="event_scoring_role",
        source_id=registration.id,
        idempotency_key=(
            f"event_scoring:{event.id}:user:{participant.id}:role:{role}"
        ),
        approved_by=approved_by_id,
        related_event_id=event.id,
        metric_updates=metric_updates,
    )


async def score_event_attendance_and_role(
    session: AsyncSession,
    event: Event,
    registration: EventRegistration,
    participant: User,
    *,
    approved_by_id: int | None,
) -> list[PointTransaction]:
    awarded = [
        await score_event_attendance(
            session,
            event,
            registration,
            participant,
            approved_by_id=approved_by_id,
        )
    ]
    role_award = await score_event_role_bonus(
        session,
        event,
        registration,
        participant,
        approved_by_id=approved_by_id,
    )
    if role_award is not None:
        awarded.append(role_award)
    return awarded


def _task_metric_updates(task: Task) -> dict[str, int]:
    updates: dict[str, int] = {"tasks_completed": 1}
    reward = task.reward_json or {}
    for raw in reward.get("counts_toward", []) or []:
        key = str(raw).strip().casefold()
        metric = TASK_ACTIVITY_METRICS.get(key)
        if metric:
            updates[metric] = 1
        elif key.endswith("_activities") and len(key) <= 64:
            updates[key] = 1
    if task.project_id:
        updates["project_activities"] = 1
    return updates


def _task_category(task: Task) -> PointCategory:
    values = {str(item).casefold() for item in (task.reward_json or {}).get("counts_toward", [])}
    if "media" in values:
        return PointCategory.MEDIA
    if "volunteering" in values or "volunteer" in values:
        return PointCategory.VOLUNTEERING
    if "project" in values and task.project_id:
        return PointCategory.PROJECT
    return PointCategory.TASK


def scoped_task_points(task: Task, participant: User) -> int:
    base = max(0, int(task.points or 0))
    if not (task.reward_json or {}).get("role_scoped"):
        return base
    multiplier = ROLE_SCOPED_MULTIPLIERS.get(participant.role, 1.0)
    return int(round(base * multiplier))


async def score_task_completion(
    session: AsyncSession,
    task: Task,
    participant: User,
    *,
    submission_id: int | None,
    approved_by_id: int | None,
) -> PointTransaction:
    """Verified Task completion -> points + metrics + rank, exactly once."""
    return await record_verified_activity(
        session,
        user_id=participant.id,
        points=scoped_task_points(task, participant),
        reason=f"Выполнение задания: {task.title}",
        category=_task_category(task),
        source_type="task_completion",
        source_id=submission_id or task.id,
        idempotency_key=f"task:{task.id}:user:{participant.id}:verified",
        approved_by=approved_by_id,
        related_task_id=task.id,
        related_project_id=task.project_id,
        metric_updates=_task_metric_updates(task),
    )


async def score_project_contribution(
    session: AsyncSession,
    project: Project,
    member: ProjectMember,
    *,
    approved_by_id: int | None,
) -> PointTransaction | None:
    if member.contribution_status != "confirmed":
        return None
    return await record_verified_activity(
        session,
        user_id=member.user_id,
        points=PROJECT_FIRST_CONTRIBUTION_POINTS,
        reason=f"Подтверждённый вклад в проект: {project.title}",
        category=PointCategory.PROJECT,
        source_type="project_contribution",
        source_id=member.id,
        idempotency_key=f"project:{project.id}:member:{member.id}:first_contribution",
        approved_by=approved_by_id,
        related_project_id=project.id,
        metric_updates={
            "project_activities": 1,
            "project_contributions": 1,
        },
    )


async def score_project_milestone(
    session: AsyncSession,
    project: Project,
    milestone: ProjectMilestone,
    *,
    approved_by_id: int | None,
) -> PointTransaction | None:
    if milestone.status != "completed" or milestone.responsible_id is None:
        return None
    return await record_verified_activity(
        session,
        user_id=milestone.responsible_id,
        points=PROJECT_MILESTONE_POINTS,
        reason=f"Этап проекта завершён: {milestone.title}",
        category=PointCategory.PROJECT,
        source_type="project_milestone",
        source_id=milestone.id,
        idempotency_key=f"project:{project.id}:milestone:{milestone.id}:completed",
        approved_by=approved_by_id,
        related_project_id=project.id,
        metric_updates={"project_milestones": 1, "project_activities": 1},
    )


async def score_project_completion(
    session: AsyncSession,
    project: Project,
    *,
    approved_by_id: int | None,
) -> list[PointTransaction]:
    """Award only people with a confirmed project contribution plus author.

    The author is treated as Project Lead for the +150 result bonus. This is
    deliberately based on real project data, not a global role multiplier.
    """
    members = list(
        (
            await session.scalars(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.status.in_(["accepted", "active", "completed"]),
                    ProjectMember.contribution_status == "confirmed",
                )
            )
        ).all()
    )
    participant_ids = {member.user_id for member in members}
    participant_ids.add(project.author_id)
    awarded: list[PointTransaction] = []
    for user_id in sorted(participant_ids):
        transaction = await record_verified_activity(
            session,
            user_id=user_id,
            points=PROJECT_COMPLETION_POINTS,
            reason=f"Завершённый проект: {project.title}",
            category=PointCategory.PROJECT,
            source_type="project_completion",
            source_id=project.id,
            idempotency_key=f"project:{project.id}:user:{user_id}:completed",
            approved_by=approved_by_id,
            related_project_id=project.id,
            metric_updates={"projects_completed": 1, "project_activities": 1},
        )
        awarded.append(transaction)

    lead = await record_verified_activity(
        session,
        user_id=project.author_id,
        points=PROJECT_LEAD_RESULT_POINTS,
        reason=f"Результат Project Lead: {project.title}",
        category=PointCategory.PROJECT,
        source_type="project_lead_result",
        source_id=project.id,
        idempotency_key=f"project:{project.id}:lead:{project.author_id}:result",
        approved_by=approved_by_id,
        related_project_id=project.id,
        metric_updates={"projects_led": 1, "leadership_activities": 1},
    )
    awarded.append(lead)
    return awarded
