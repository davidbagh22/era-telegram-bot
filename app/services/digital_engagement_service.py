"""Digital engagement points -- Points/Ranks ToR ("ERA Platform — ранги,
баллы, автоматическое начисление и «Возможности»") sections 5, 6, 47
phase 1.

Small, capped points for using the app itself, so the app stays worth
opening daily without clicks alone ever buying real recognition (ToR
section 4: "клики дают прогресс, а реальные действия дают статус"). Real
activity (events/tasks/projects/etc., ToR sections 7-14) is scored
separately via app.services.points_service.add_points directly and isn't
touched here.

Every award below is idempotent through add_points()'s idempotency_key, so
calling these functions repeatedly (retries, re-renders, concurrent
requests, a user reopening the app many times a day) never double-pays --
callers don't need to guard against that themselves.

Two of the ToR's digital caps aren't wired up here because the feature
they'd hook into doesn't exist in this codebase yet: full profile
completion (registration already collects every profile field up front --
there is no separate profile-edit surface to "complete" later) and
"acknowledged an important update" (no such content type exists). Adding
them once those features land is additive, not a rework of this module.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, User
from app.services.points_service import add_points
from app.utils.constants import (
    DIGITAL_ENGAGEMENT_POINTS,
    ApplicationStatus,
    PointCategory,
)

DAILY_OPEN_SOURCE = "digital_daily_open"
STREAK_SOURCE = "digital_streak_7day"
EVENT_REGISTRATION_SOURCE = "digital_event_registration"
VECTOR_CHECKIN_SOURCE = "digital_vector_checkin"
VECTOR_PULSE_SOURCE = "digital_vector_pulse"
GOAL_SET_SOURCE = "digital_goal_set"
GOAL_COMPLETED_SOURCE = "digital_goal_completed"

# ToR section 5 monthly caps for awards that don't already have a natural
# 1/period idempotency key (vector pulse, goal set/complete can each occur
# more than once a month).
VECTOR_PULSE_MONTHLY_CAP = 4
GOAL_SET_MONTHLY_CAP = 2
GOAL_COMPLETED_MONTHLY_CAP = 2


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _to_local_date(value: datetime) -> date:
    return value.astimezone().date() if value.tzinfo else value.date()


def is_digitally_engaged(user: User) -> bool:
    """Digital engagement points are for people already inside ERA -- not
    pending applicants and not blocked/archived accounts."""
    return (
        user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _existing_transaction(
    session: AsyncSession, idempotency_key: str
) -> PointTransaction | None:
    return await session.scalar(
        select(PointTransaction).where(PointTransaction.idempotency_key == idempotency_key)
    )


async def _month_award_count(
    session: AsyncSession, user_id: int, source_type: str, month: str
) -> int:
    year, month_num = (int(part) for part in month.split("-"))
    start = date(year, month_num, 1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return int(
        await session.scalar(
            select(func.count(PointTransaction.id)).where(
                PointTransaction.user_id == user_id,
                PointTransaction.source_type == source_type,
                PointTransaction.created_at >= datetime.combine(start, datetime.min.time()).astimezone(),
                PointTransaction.created_at < datetime.combine(next_month, datetime.min.time()).astimezone(),
            )
        )
        or 0
    )


# --- App usage -------------------------------------------------------------


async def award_daily_open(session: AsyncSession, user: User) -> PointTransaction | None:
    """+5, once per calendar day -- ToR section 5 row 1 ("Первый
    содержательный вход в приложение за день"). Also checks/awards the
    7-day streak bonus, since a streak can only ever complete on a day the
    user opened the app."""
    if not is_digitally_engaged(user):
        return None
    today = datetime.now().astimezone().date()
    transaction = await add_points(
        session,
        user_id=user.id,
        points=DIGITAL_ENGAGEMENT_POINTS["daily_open"],
        reason="Активность в приложении за день",
        approved_by=user.id,
        source_type=DAILY_OPEN_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=f"digital:daily_open:{user.id}:{today.isoformat()}",
    )
    await _maybe_award_streak(session, user, today)
    return transaction


async def _current_streak_length(session: AsyncSession, user_id: int, today: date) -> int:
    """Consecutive calendar days up to and including `today` that have a
    daily_open transaction, stopping at the first gap."""
    since = today - timedelta(days=60)
    rows = await session.scalars(
        select(PointTransaction.created_at).where(
            PointTransaction.user_id == user_id,
            PointTransaction.source_type == DAILY_OPEN_SOURCE,
            PointTransaction.created_at >= datetime.combine(since, datetime.min.time()).astimezone(),
        )
    )
    open_dates = {_to_local_date(row) for row in rows}
    streak = 0
    cursor = today
    while cursor in open_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _maybe_award_streak(
    session: AsyncSession, user: User, today: date
) -> PointTransaction | None:
    """+20 for every additional unbroken 7-day run -- ToR section 5 row 2
    ("7 активных дней подряд")."""
    streak = await _current_streak_length(session, user.id, today)
    if streak == 0 or streak % 7 != 0:
        return None
    return await add_points(
        session,
        user_id=user.id,
        points=DIGITAL_ENGAGEMENT_POINTS["streak_7day"],
        reason="7 активных дней подряд",
        approved_by=user.id,
        source_type=STREAK_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=f"digital:streak7:{user.id}:{streak}",
    )


async def award_event_registration(
    session: AsyncSession, *, user_id: int, event_id: int
) -> PointTransaction | None:
    """+10, once per unique event a user has ever registered for -- ToR
    section 5 last row. Registering is a click; this stays a
    digital-engagement amount, distinct from the real attendance points
    events award separately on confirmed attendance
    (event_registration_service.award_attendance_points)."""
    return await add_points(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["event_registration"],
        reason="Регистрация на событие",
        approved_by=user_id,
        related_event_id=event_id,
        source_type=EVENT_REGISTRATION_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=f"digital:event_registration:{event_id}:{user_id}",
    )


# --- My Vector ---------------------------------------------------------
# Every function below takes only ids/dates -- never checkin answers, state
# scores, goal titles, or note text. ToR section 6: the points ledger may
# only ever record that a Vector action of a given type happened, not its
# content. Vector's own privacy model (development_service.py) is
# unaffected; this module never reads or stores anything from it.


async def award_vector_monthly_checkin(
    session: AsyncSession, *, user_id: int, month: str
) -> PointTransaction | None:
    """+30, once per month -- ToR section 6
    ("vector.monthly_checkin_completed +30"). One MonthlyCheckin row exists
    per (user, month) already (uq_monthly_checkin_user_month), so the
    idempotency key alone is the cap -- no separate count check needed."""
    return await add_points(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["vector_monthly_checkin"],
        reason="Ежемесячный check-in «Моего вектора»",
        approved_by=user_id,
        source_type=VECTOR_CHECKIN_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=f"digital:vector_checkin:{user_id}:{month}",
    )


async def award_vector_weekly_pulse(
    session: AsyncSession, *, user_id: int, week_start: date
) -> PointTransaction | None:
    """+10, max 4/month -- ToR section 5 ("Weekly check-in / рефлексия
    Vector")."""
    key = f"digital:vector_pulse:{user_id}:{week_start.isoformat()}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    month = _month_key(week_start)
    if await _month_award_count(session, user_id, VECTOR_PULSE_SOURCE, month) >= VECTOR_PULSE_MONTHLY_CAP:
        return None
    return await add_points(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["vector_weekly_pulse"],
        reason="Еженедельный check-in «Моего вектора»",
        approved_by=user_id,
        source_type=VECTOR_PULSE_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=key,
    )


async def award_goal_set(
    session: AsyncSession, *, user_id: int, goal_id: int, month: str
) -> PointTransaction | None:
    """+15, max 2/month -- ToR section 5 ("Постановка личной цели")."""
    key = f"digital:goal_set:{goal_id}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    if await _month_award_count(session, user_id, GOAL_SET_SOURCE, month) >= GOAL_SET_MONTHLY_CAP:
        return None
    return await add_points(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["goal_set"],
        reason="Постановка личной цели",
        approved_by=user_id,
        source_type=GOAL_SET_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=key,
    )


async def award_goal_completed(
    session: AsyncSession, *, user_id: int, goal_id: int, month: str
) -> PointTransaction | None:
    """+25, max 2/month -- ToR section 5 ("Завершение личной цели"). Callers
    must only invoke this for a goal review with result == "done" -- a
    partial/abandoned/changed-mind review is not a completion."""
    key = f"digital:goal_done:{goal_id}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    if await _month_award_count(session, user_id, GOAL_COMPLETED_SOURCE, month) >= GOAL_COMPLETED_MONTHLY_CAP:
        return None
    return await add_points(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["goal_completed"],
        reason="Завершение личной цели",
        approved_by=user_id,
        source_type=GOAL_COMPLETED_SOURCE,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=key,
    )
