from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    PointTransaction,
    User,
)
from app.services.activity_scoring_service import record_verified_activity
from app.utils.constants import PointCategory, RegistrationStatus
from app.utils.validators import clean_text

# Event Activities — proof-of-participation tasks tied to a completed event
# (e.g. "post a story", "write a review"). They stay event-scoped, but final
# approval now enters the same verified-activity scoring pipeline as attendance,
# ordinary Tasks and Projects so metrics/rank/lifecycle cannot drift.

ALLOWED_SUBMISSION_TYPES = {"photo", "link", "text", "file", "manual", "video"}
REVIEWABLE_STATUSES = {"pending", "leader_approved"}
SENT_MARKER = "[ERA_ACTIVITIES_SENT]"
ACTIVE_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
}


def parse_bulk_lines(raw_text: str) -> tuple[list[dict], int]:
    """"Title | points | type | description" per line."""
    parsed: list[dict] = []
    rejected = 0
    for raw_line in (raw_text or "").splitlines():
        parts = [item.strip() for item in raw_line.split("|")]
        if len(parts) < 3:
            if raw_line.strip():
                rejected += 1
            continue
        title = clean_text(parts[0], 255)
        try:
            points = int(parts[1])
        except ValueError:
            rejected += 1
            continue
        submission_type = (clean_text(parts[2], 32) or "").lower()
        description = clean_text(parts[3], 1000) if len(parts) > 3 else title
        if not title or submission_type not in ALLOWED_SUBMISSION_TYPES or not 0 <= points <= 1000:
            rejected += 1
            continue
        parsed.append(
            {
                "title": title,
                "points": points,
                "submission_type": submission_type,
                "description": description or title,
            }
        )
    return parsed, rejected


# -- Admin --


async def create_activities_bulk(session: AsyncSession, event: Event, raw_text: str) -> tuple[int, int]:
    parsed, rejected = parse_bulk_lines(raw_text)
    for item in parsed:
        session.add(
            EventActivity(
                event_id=event.id,
                title=item["title"],
                description=item["description"],
                submission_type=item["submission_type"],
                points=item["points"],
                requires_review=True,
                deadline=datetime.now().astimezone() + timedelta(days=7),
                is_active=True,
            )
        )
    await session.flush()
    return len(parsed), rejected


async def list_activities_admin(session: AsyncSession, event_id: int) -> list[EventActivity]:
    return list(
        (
            await session.scalars(
                select(EventActivity).where(EventActivity.event_id == event_id).order_by(EventActivity.id)
            )
        ).all()
    )


def activities_already_sent(event: Event) -> bool:
    return SENT_MARKER in (event.additional_info or "")


def mark_activities_sent(event: Event) -> None:
    event.additional_info = ((event.additional_info or "") + f"\n{SENT_MARKER}").strip()


async def send_recipients(session: AsyncSession, event_id: int) -> list[User]:
    registrations = (
        await session.scalars(
            select(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
    ).all()
    users: list[User] = []
    for registration in registrations:
        target = await session.get(User, registration.user_id)
        if target:
            users.append(target)
    return users


async def list_reviewable_submissions(
    session: AsyncSession,
) -> list[tuple[EventActivitySubmission, EventActivity, Event, User]]:
    result = await session.execute(
        select(EventActivitySubmission, EventActivity, Event, User)
        .join(EventActivity, EventActivity.id == EventActivitySubmission.activity_id)
        .join(Event, Event.id == EventActivity.event_id)
        .join(User, User.id == EventActivitySubmission.user_id)
        .where(EventActivitySubmission.status.in_(REVIEWABLE_STATUSES))
        .order_by(EventActivitySubmission.created_at)
        .limit(50)
    )
    return list(result.all())


async def admin_decide(
    session: AsyncSession,
    submission: EventActivitySubmission,
    *,
    approve: bool,
    reviewer_id: int | None,
) -> EventActivity | None:
    """Final review. Verified approval is scored exactly once through the core pipeline."""
    if submission.status not in REVIEWABLE_STATUSES:
        return None
    activity = await session.get(EventActivity, submission.activity_id)
    if activity is None:
        return None
    submission.status = "approved" if approve else "rejected"
    submission.reviewed_by = reviewer_id
    if not approve:
        await session.flush()
        return activity

    # Preserve compatibility with historical rows that pre-date the current
    # idempotency key: do not create a second award if an old matching point
    # transaction already exists.
    existing = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == submission.user_id,
            PointTransaction.related_event_id == activity.event_id,
            PointTransaction.reason.ilike(f"%{activity.title}%"),
            PointTransaction.points > 0,
        )
    )
    if existing or submission.points_awarded > 0:
        await session.flush()
        return activity

    submission.points_awarded = activity.points
    await record_verified_activity(
        session,
        user_id=submission.user_id,
        points=activity.points,
        reason=f"Активность после мероприятия: {activity.title}",
        approved_by=reviewer_id,
        category=PointCategory.EVENT,
        related_event_id=activity.event_id,
        source_type="event_activity",
        source_id=submission.id,
        idempotency_key=f"event_activity:{submission.id}:approval",
        metric_updates={"event_activities": 1},
    )
    return activity


# -- Leader --


async def list_leader_pending(
    session: AsyncSession, leader_id: int
) -> list[tuple[EventActivitySubmission, EventActivity, Event, User]]:
    event_ids = list((await session.scalars(select(Event.id).where(Event.responsible_id == leader_id))).all())
    if not event_ids:
        return []
    activity_ids = list(
        (await session.scalars(select(EventActivity.id).where(EventActivity.event_id.in_(event_ids)))).all()
    )
    if not activity_ids:
        return []
    result = await session.execute(
        select(EventActivitySubmission, EventActivity, Event, User)
        .join(EventActivity, EventActivity.id == EventActivitySubmission.activity_id)
        .join(Event, Event.id == EventActivity.event_id)
        .join(User, User.id == EventActivitySubmission.user_id)
        .where(
            EventActivitySubmission.activity_id.in_(activity_ids),
            EventActivitySubmission.status == "pending",
        )
        .order_by(EventActivitySubmission.created_at)
        .limit(50)
    )
    return list(result.all())


async def leader_decide(
    session: AsyncSession,
    submission: EventActivitySubmission,
    *,
    approve: bool,
    reviewer_id: int,
) -> EventActivity | None:
    if submission.status != "pending":
        return None
    activity = await session.get(EventActivity, submission.activity_id)
    submission.status = "leader_approved" if approve else "rejected"
    submission.reviewed_by = reviewer_id
    await session.flush()
    return activity


# -- Participant --


async def _active_registration(
    session: AsyncSession, event_id: int, user_id: int
) -> EventRegistration | None:
    return await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
            EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )


async def list_activities_for_participant(
    session: AsyncSession, event: Event, user: User
) -> list[EventActivity] | None:
    if not await _active_registration(session, event.id, user.id):
        return None
    return list(
        (
            await session.scalars(
                select(EventActivity)
                .where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True))
                .order_by(EventActivity.id)
            )
        ).all()
    )


async def get_submission(
    session: AsyncSession, activity_id: int, user_id: int
) -> EventActivitySubmission | None:
    return await session.scalar(
        select(EventActivitySubmission).where(
            EventActivitySubmission.activity_id == activity_id,
            EventActivitySubmission.user_id == user_id,
        )
    )


async def submit_manual(
    session: AsyncSession, activity: EventActivity, user: User
) -> EventActivitySubmission:
    existing = await get_submission(session, activity.id, user.id)
    submission = existing or EventActivitySubmission(activity_id=activity.id, user_id=user.id)
    submission.text = "Заявка на ручную проверку"
    submission.file_id = None
    submission.file_type = "manual"
    submission.status = "pending"
    submission.reviewed_by = None
    submission.admin_comment = None
    if existing is None:
        session.add(submission)
    await session.flush()
    return submission
