"""Digital engagement scoring for ERA Platform.

Digital actions can add small reputation points but never count as Meaningful
Activity. Every award is idempotent and all digital sources share one calendar-
month cap so repetitive app use cannot outrun real participation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting, PointTransaction, User
from app.services.points_service import add_points
from app.utils.constants import DIGITAL_ENGAGEMENT_POINTS, ApplicationStatus, PointCategory

DAILY_OPEN_SOURCE = "digital_daily_open"
STREAK_SOURCE = "digital_streak_7day"
PROFILE_COMPLETE_SOURCE = "digital_profile_complete"
MATERIAL_ACK_SOURCE = "digital_material_ack"
EVENT_REGISTRATION_SOURCE = "digital_event_registration"
VECTOR_CHECKIN_SOURCE = "digital_vector_checkin"
VECTOR_PULSE_SOURCE = "digital_vector_pulse"
GOAL_SET_SOURCE = "digital_goal_set"
GOAL_COMPLETED_SOURCE = "digital_goal_completed"

VECTOR_PULSE_MONTHLY_CAP = 4
GOAL_SET_MONTHLY_CAP = 2
GOAL_COMPLETED_MONTHLY_CAP = 2
MATERIAL_ACK_MONTHLY_CAP = 5
DEFAULT_DIGITAL_MONTHLY_POINTS_CAP = 300
DIGITAL_CAP_SETTING_KEY = "digital_engagement_monthly_cap"
IMPORTANT_MATERIALS_SETTING_KEY = "important_materials"
PROFILE_COMPLETION_POINTS = 50
MATERIAL_ACK_POINTS = 5


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, month_num = (int(part) for part in month.split("-"))
    start = date(year, month_num, 1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (
        datetime.combine(start, datetime.min.time()).astimezone(),
        datetime.combine(next_month, datetime.min.time()).astimezone(),
    )


def _to_local_date(value: datetime) -> date:
    return value.astimezone().date() if value.tzinfo else value.date()


def is_digitally_engaged(user: User) -> bool:
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
    start, end = _month_bounds(month)
    return int(
        await session.scalar(
            select(func.count(PointTransaction.id)).where(
                PointTransaction.user_id == user_id,
                PointTransaction.source_type == source_type,
                PointTransaction.created_at >= start,
                PointTransaction.created_at < end,
            )
        )
        or 0
    )


async def digital_monthly_cap(session: AsyncSession) -> int:
    setting = await session.scalar(
        select(AppSetting).where(AppSetting.key == DIGITAL_CAP_SETTING_KEY)
    )
    value = setting.value if setting is not None else None
    if isinstance(value, dict):
        value = value.get("points")
    try:
        cap = int(value) if value is not None else DEFAULT_DIGITAL_MONTHLY_POINTS_CAP
    except (TypeError, ValueError):
        cap = DEFAULT_DIGITAL_MONTHLY_POINTS_CAP
    return max(0, min(cap, 1000))


async def digital_points_this_month(
    session: AsyncSession, user_id: int, *, month: str | None = None
) -> int:
    month = month or _month_key(datetime.now().astimezone().date())
    start, end = _month_bounds(month)
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user_id,
                PointTransaction.category == PointCategory.DIGITAL_ENGAGEMENT,
                PointTransaction.created_at >= start,
                PointTransaction.created_at < end,
            )
        )
        or 0
    )


async def _award_digital(
    session: AsyncSession,
    *,
    user_id: int,
    points: int,
    reason: str,
    source_type: str,
    idempotency_key: str,
    related_event_id: int | None = None,
) -> PointTransaction | None:
    existing = await _existing_transaction(session, idempotency_key)
    if existing is not None:
        return existing
    cap = await digital_monthly_cap(session)
    already = await digital_points_this_month(session, user_id)
    remaining = max(cap - already, 0)
    award = min(max(int(points), 0), remaining)
    if award <= 0:
        return None
    return await add_points(
        session,
        user_id=user_id,
        points=award,
        reason=reason,
        approved_by=user_id,
        source_type=source_type,
        category=PointCategory.DIGITAL_ENGAGEMENT,
        idempotency_key=idempotency_key,
        related_event_id=related_event_id,
    )


async def award_daily_open(session: AsyncSession, user: User) -> PointTransaction | None:
    if not is_digitally_engaged(user):
        return None
    today = datetime.now().astimezone().date()
    transaction = await _award_digital(
        session,
        user_id=user.id,
        points=DIGITAL_ENGAGEMENT_POINTS["daily_open"],
        reason="Активность в приложении за день",
        source_type=DAILY_OPEN_SOURCE,
        idempotency_key=f"digital:daily_open:{user.id}:{today.isoformat()}",
    )
    await _maybe_award_streak(session, user, today)
    return transaction


async def _current_streak_length(session: AsyncSession, user_id: int, today: date) -> int:
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
    streak = await _current_streak_length(session, user.id, today)
    if streak == 0 or streak % 7 != 0:
        return None
    return await _award_digital(
        session,
        user_id=user.id,
        points=DIGITAL_ENGAGEMENT_POINTS["streak_7day"],
        reason="7 активных дней подряд",
        source_type=STREAK_SOURCE,
        idempotency_key=f"digital:streak7:{user.id}:{streak}",
    )


def profile_is_complete(user: User) -> bool:
    required = (
        user.first_name,
        user.last_name,
        user.birth_date,
        user.phone,
        user.email,
        user.city,
        user.education_work,
        user.occupation,
        user.experience,
        user.motivation,
    )
    return all(bool(value) for value in required) and bool(user.skills)


async def award_profile_completion(
    session: AsyncSession,
    user: User,
    *,
    profile_version: str = "v1",
) -> PointTransaction | None:
    """+50 when the required ERA profile is genuinely complete, once/version."""
    if not is_digitally_engaged(user) or not profile_is_complete(user):
        return None
    return await _award_digital(
        session,
        user_id=user.id,
        points=PROFILE_COMPLETION_POINTS,
        reason="Полностью заполненный профиль",
        source_type=PROFILE_COMPLETE_SOURCE,
        idempotency_key=f"digital:profile_complete:{user.id}:{profile_version}",
    )


async def configured_important_materials(session: AsyncSession) -> list[dict]:
    setting = await session.scalar(
        select(AppSetting).where(AppSetting.key == IMPORTANT_MATERIALS_SETTING_KEY)
    )
    if setting is None or not isinstance(setting.value, list):
        return []
    result: list[dict] = []
    for raw in setting.value:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()[:80]
        version = str(raw.get("version") or "v1").strip()[:40]
        title = str(raw.get("title") or key).strip()[:255]
        if key and raw.get("active", True):
            result.append({"key": key, "version": version, "title": title})
    return result


async def award_material_acknowledgement(
    session: AsyncSession,
    user: User,
    *,
    material_key: str,
    material_version: str,
) -> PointTransaction | None:
    """+5 for an allow-listed important material, max five awards/month."""
    if not is_digitally_engaged(user):
        return None
    allowed = {
        (item["key"], item["version"])
        for item in await configured_important_materials(session)
    }
    identity = (material_key.strip(), material_version.strip())
    if identity not in allowed:
        raise ValueError("important_material_not_found")
    month = _month_key(datetime.now().astimezone().date())
    key = f"digital:material:{user.id}:{identity[0]}:{identity[1]}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    if await _month_award_count(session, user.id, MATERIAL_ACK_SOURCE, month) >= MATERIAL_ACK_MONTHLY_CAP:
        return None
    return await _award_digital(
        session,
        user_id=user.id,
        points=MATERIAL_ACK_POINTS,
        reason="Ознакомление с важным материалом",
        source_type=MATERIAL_ACK_SOURCE,
        idempotency_key=key,
    )


async def award_event_registration(
    session: AsyncSession, *, user_id: int, event_id: int
) -> PointTransaction | None:
    return await _award_digital(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["event_registration"],
        reason="Регистрация на событие",
        related_event_id=event_id,
        source_type=EVENT_REGISTRATION_SOURCE,
        idempotency_key=f"digital:event_registration:{event_id}:{user_id}",
    )


async def award_vector_monthly_checkin(
    session: AsyncSession, *, user_id: int, month: str
) -> PointTransaction | None:
    return await _award_digital(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["vector_monthly_checkin"],
        reason="Ежемесячный check-in «Моего вектора»",
        source_type=VECTOR_CHECKIN_SOURCE,
        idempotency_key=f"digital:vector_checkin:{user_id}:{month}",
    )


async def award_vector_weekly_pulse(
    session: AsyncSession, *, user_id: int, week_start: date
) -> PointTransaction | None:
    key = f"digital:vector_pulse:{user_id}:{week_start.isoformat()}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    month = _month_key(week_start)
    if await _month_award_count(session, user_id, VECTOR_PULSE_SOURCE, month) >= VECTOR_PULSE_MONTHLY_CAP:
        return None
    return await _award_digital(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["vector_weekly_pulse"],
        reason="Еженедельный check-in «Моего вектора»",
        source_type=VECTOR_PULSE_SOURCE,
        idempotency_key=key,
    )


async def award_goal_set(
    session: AsyncSession, *, user_id: int, goal_id: int, month: str
) -> PointTransaction | None:
    key = f"digital:goal_set:{goal_id}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    if await _month_award_count(session, user_id, GOAL_SET_SOURCE, month) >= GOAL_SET_MONTHLY_CAP:
        return None
    return await _award_digital(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["goal_set"],
        reason="Постановка личной цели",
        source_type=GOAL_SET_SOURCE,
        idempotency_key=key,
    )


async def award_goal_completed(
    session: AsyncSession, *, user_id: int, goal_id: int, month: str
) -> PointTransaction | None:
    key = f"digital:goal_done:{goal_id}"
    existing = await _existing_transaction(session, key)
    if existing is not None:
        return existing
    if await _month_award_count(session, user_id, GOAL_COMPLETED_SOURCE, month) >= GOAL_COMPLETED_MONTHLY_CAP:
        return None
    return await _award_digital(
        session,
        user_id=user_id,
        points=DIGITAL_ENGAGEMENT_POINTS["goal_completed"],
        reason="Завершение личной цели",
        source_type=GOAL_COMPLETED_SOURCE,
        idempotency_key=key,
    )
