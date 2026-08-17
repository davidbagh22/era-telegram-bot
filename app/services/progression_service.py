from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.services.activity_metrics_service import get_all_metrics
from app.services.audit_service import audit
from app.utils.constants import ParticipationStatus

# Automatic progression deliberately uses the existing ParticipationStatus
# enum. There is no second rank table/enum: rank is a derived summary of
# verified real activity, while Office/UserOffice continues to represent a
# person's current responsibility and permissions.
RANK_ORDER = (
    ParticipationStatus.NEW_MEMBER,
    ParticipationStatus.INVOLVED_MEMBER,
    ParticipationStatus.ACTIVE_MEMBER,
    ParticipationStatus.TEAM_MEMBER,
    ParticipationStatus.PROJECT_CURATOR,
    ParticipationStatus.COMMUNITY_LEADER,
)

_REAL_ACTIVITY_KEYS = (
    "events_attended",
    "tasks_completed",
    "project_activities",
    "volunteer_activities",
    "social_activities",
    "media_activities",
    "culture_activities",
    "partner_activities",
    "leadership_activities",
    "mentorship_activities",
)


def _value(metrics: dict[str, int], key: str) -> int:
    return max(0, int(metrics.get(key, 0) or 0))


def _real_activity_total(metrics: dict[str, int]) -> int:
    return sum(_value(metrics, key) for key in _REAL_ACTIVITY_KEYS)


def _real_activity_categories(metrics: dict[str, int]) -> int:
    return sum(1 for key in _REAL_ACTIVITY_KEYS if _value(metrics, key) > 0)


def target_participation_status(metrics: dict[str, int]) -> ParticipationStatus:
    """Return the highest status justified by verified activity.

    The thresholds intentionally encode the product meaning from the master
    ToR rather than a points ladder: clicks can add reputation points, but
    they can never by themselves promote somebody to team/curator/leader.
    """
    leadership = _value(metrics, "leadership_activities")
    mentorship_outcomes = max(
        _value(metrics, "mentorship_outcomes"),
        _value(metrics, "people_mentored_active"),
        _value(metrics, "mentees_with_responsibility"),
    )
    projects_led = _value(metrics, "projects_led")
    coordinated = _value(metrics, "events_coordinated")

    if (
        leadership >= 5
        and mentorship_outcomes >= 1
        and (projects_led >= 1 or coordinated >= 2)
    ):
        return ParticipationStatus.COMMUNITY_LEADER

    if projects_led >= 1 or _value(metrics, "project_milestones") >= 2 or coordinated >= 2:
        return ParticipationStatus.PROJECT_CURATOR

    team_evidence = (
        _value(metrics, "project_activities") >= 2
        or _value(metrics, "media_activities") >= 3
        or _value(metrics, "social_activities") >= 2
        or _value(metrics, "events_organized") >= 1
        or _value(metrics, "projects_completed") >= 1
    )
    if _value(metrics, "tasks_completed") >= 3 and team_evidence:
        return ParticipationStatus.TEAM_MEMBER
    if _value(metrics, "projects_completed") >= 1 and _value(metrics, "project_activities") >= 3:
        return ParticipationStatus.TEAM_MEMBER

    real_total = _real_activity_total(metrics)
    if real_total >= 4 and _real_activity_categories(metrics) >= 2:
        return ParticipationStatus.ACTIVE_MEMBER
    if _value(metrics, "events_attended") >= 3 or _value(metrics, "tasks_completed") >= 2:
        return ParticipationStatus.ACTIVE_MEMBER

    if real_total >= 1:
        return ParticipationStatus.INVOLVED_MEMBER
    return ParticipationStatus.NEW_MEMBER


def _rank_index(status: str) -> int:
    try:
        return RANK_ORDER.index(ParticipationStatus(status))
    except (ValueError, TypeError):
        return 0


async def promote_participation_status(session: AsyncSession, *, user_id: int) -> str | None:
    """Promote (never silently demote) a user from verified metrics.

    Returns the new status when a promotion happened, otherwise ``None``.
    Demotion, if ever needed, must remain an explicit reviewed action because
    losing historical status due to a changed formula would be destructive.
    """
    user = await session.get(User, user_id)
    if user is None:
        return None
    metrics = await get_all_metrics(session, user_id=user_id)
    target = target_participation_status(metrics)
    current = user.participation_status or ParticipationStatus.NEW_MEMBER
    if _rank_index(target) <= _rank_index(current):
        return None

    old = str(current)
    user.participation_status = target
    await audit(
        session,
        actor_id=None,
        action="participation_status.promoted",
        entity_type="user",
        entity_id=user.id,
        old_value={"participation_status": old},
        new_value={"participation_status": str(target), "source": "verified_activity"},
    )
    await session.flush()
    return str(target)
