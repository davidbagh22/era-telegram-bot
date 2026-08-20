from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import PointTransaction, User
from app.database.referral_models import ReferralCode, ReferralRelationship
from app.services.points_service import add_points, make_idempotency_key
from app.utils.constants import ApplicationStatus, PointCategory

# Referral economy v2: points reward the inviter for a real conversion, not
# for link clicks/chat joins and not for the invitee's own registration.
REGISTRATION_REFERRAL_POINTS = 30
FIRST_EVENT_REFERRAL_POINTS = 70
FIRST_ACTIVITY_REFERRAL_POINTS = FIRST_EVENT_REFERRAL_POINTS
ACTIVE_REFERRAL_POINTS = 0
REFERRAL_PER_INVITEE_CAP = 100
# Kept in the public response for backwards compatibility. Zero means that
# there is no additional calendar-month ceiling; the hard business rule is
# the 100-point cap per unique invited participant.
REFERRAL_MONTHLY_CAP = 0
REFERRAL_SOURCE_TYPES = (
    "referral_registration",
    "referral_first_activity",
    # Historical transaction types remain included in totals.
    "referral_first_event",
    "referral_active",
)
CODE_LENGTH = 6
OFFICIAL_BOT_HANDLE = "@ERA_1bot"
OFFICIAL_BOT_URL = "https://t.me/ERA_1bot"
ERA_TIMEZONE = ZoneInfo("Asia/Yerevan")


@dataclass(frozen=True)
class ReferralSummary:
    code: str
    invite_url: str
    share_text: str
    invited_count: int
    registered_count: int
    first_event_count: int
    active_count: int
    earned_points: int
    monthly_earned_points: int
    monthly_cap: int


def normalize_referral_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = "".join(value.strip().split())
    if len(code) != CODE_LENGTH or not code.isdigit():
        return None
    return code


async def get_or_create_referral_code(session: AsyncSession, user_id: int) -> ReferralCode:
    existing = await session.get(ReferralCode, user_id)
    if existing is not None:
        return existing

    await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
    existing = await session.get(ReferralCode, user_id)
    if existing is not None:
        return existing

    for _ in range(20):
        code = str(secrets.randbelow(900_000) + 100_000)
        if await session.scalar(select(ReferralCode.user_id).where(ReferralCode.code == code)):
            continue
        row = ReferralCode(user_id=user_id, code=code)
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except IntegrityError:
            continue
    raise RuntimeError("could_not_allocate_referral_code")


async def validate_referral_code(
    session: AsyncSession,
    value: str | None,
    *,
    telegram_id: int | None = None,
) -> tuple[ReferralCode, User]:
    code = normalize_referral_code(value)
    if code is None:
        raise ValueError("invalid_referral_code")
    row = await session.scalar(select(ReferralCode).where(ReferralCode.code == code))
    if row is None:
        raise ValueError("referral_code_not_found")
    inviter = await session.get(User, row.user_id)
    if inviter is None or inviter.is_archived:
        raise ValueError("referral_code_not_found")
    if telegram_id is not None and inviter.telegram_id == telegram_id:
        raise ValueError("self_referral_not_allowed")
    return row, inviter


async def bind_referral_code(
    session: AsyncSession,
    *,
    invitee: User,
    value: str | None,
) -> ReferralRelationship | None:
    code = normalize_referral_code(value)
    if code is None:
        return None

    existing = await session.scalar(
        select(ReferralRelationship).where(ReferralRelationship.invitee_id == invitee.id)
    )
    if existing is not None:
        return existing

    code_row, inviter = await validate_referral_code(
        session, code, telegram_id=invitee.telegram_id
    )
    if inviter.id == invitee.id:
        raise ValueError("self_referral_not_allowed")

    relationship = ReferralRelationship(
        inviter_id=code_row.user_id,
        invitee_id=invitee.id,
        code=code_row.code,
    )
    session.add(relationship)
    await session.flush()
    return relationship


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(ERA_TIMEZONE)
    start_local = datetime(local_now.year, local_now.month, 1, tzinfo=ERA_TIMEZONE)
    if local_now.month == 12:
        end_local = datetime(local_now.year + 1, 1, 1, tzinfo=ERA_TIMEZONE)
    else:
        end_local = datetime(local_now.year, local_now.month + 1, 1, tzinfo=ERA_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _inviter_referral_points(
    session: AsyncSession,
    *,
    inviter_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(PointTransaction.points), 0))
        .select_from(PointTransaction)
        .join(
            ReferralRelationship,
            ReferralRelationship.id == PointTransaction.source_id,
        )
        .where(
            PointTransaction.user_id == inviter_id,
            ReferralRelationship.inviter_id == inviter_id,
            PointTransaction.source_type.in_(REFERRAL_SOURCE_TYPES),
        )
    )
    if start is not None:
        stmt = stmt.where(PointTransaction.created_at >= start)
    if end is not None:
        stmt = stmt.where(PointTransaction.created_at < end)
    return int(await session.scalar(stmt) or 0)


async def _relationship_points(
    session: AsyncSession,
    relationship: ReferralRelationship,
) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == relationship.inviter_id,
                PointTransaction.source_id == relationship.id,
                PointTransaction.source_type.in_(REFERRAL_SOURCE_TYPES),
            )
        )
        or 0
    )


async def _add_inviter_referral_points(
    session: AsyncSession,
    *,
    relationship: ReferralRelationship,
    requested_points: int,
    reason: str,
    source_type: str,
    stage: str,
    related_event_id: int | None = None,
) -> int:
    # Lock the relationship itself so two concurrent confirmations cannot both
    # observe spare per-invitee capacity.
    relationship = await session.scalar(
        select(ReferralRelationship)
        .where(ReferralRelationship.id == relationship.id)
        .with_for_update()
    ) or relationship
    already_earned = await _relationship_points(session, relationship)
    remaining = max(0, REFERRAL_PER_INVITEE_CAP - already_earned)
    points = min(max(0, requested_points), remaining)
    if points <= 0:
        return 0
    await add_points(
        session,
        user_id=relationship.inviter_id,
        points=points,
        reason=reason,
        approved_by=None,
        related_event_id=related_event_id,
        source_type=source_type,
        source_id=relationship.id,
        category=PointCategory.REFERRAL,
        idempotency_key=make_idempotency_key(
            "referral", stage, relationship.id, "inviter"
        ),
    )
    return points


async def award_registration_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
) -> ReferralRelationship | None:
    """Award +30 to the inviter only after the invitee becomes APPROVED."""

    relationship = await session.scalar(
        select(ReferralRelationship)
        .where(ReferralRelationship.invitee_id == invitee_user_id)
        .with_for_update()
    )
    if relationship is None or relationship.registration_rewarded_at is not None:
        return relationship

    invitee = await session.get(User, invitee_user_id)
    if invitee is None or invitee.application_status != ApplicationStatus.APPROVED:
        return relationship

    now = datetime.now(timezone.utc)
    await _add_inviter_referral_points(
        session,
        relationship=relationship,
        requested_points=REGISTRATION_REFERRAL_POINTS,
        reason="Приглашённый участник прошёл регистрацию и был одобрен",
        source_type="referral_registration",
        stage="registration",
    )
    relationship.registration_rewarded_at = now
    await session.flush()
    return relationship


async def award_first_activity_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
    event_id: int | None = None,
) -> ReferralRelationship | None:
    """Award +70 once after the first confirmed ERA event/project activity.

    The existing first_event_rewarded_at column is deliberately reused as the
    durable one-time marker so this economy change does not require a risky
    production migration. `first_event_id` is populated only for event-based
    confirmation; project confirmations can leave it null.
    """

    relationship = await session.scalar(
        select(ReferralRelationship)
        .where(ReferralRelationship.invitee_id == invitee_user_id)
        .with_for_update()
    )
    if relationship is None or relationship.first_event_rewarded_at is not None:
        return relationship
    if relationship.registration_rewarded_at is None:
        return relationship

    now = datetime.now(timezone.utc)
    await _add_inviter_referral_points(
        session,
        relationship=relationship,
        requested_points=FIRST_ACTIVITY_REFERRAL_POINTS,
        reason="Приглашённый участник подтвердил первое участие в ЭРА",
        source_type="referral_first_activity",
        stage="first_activity",
        related_event_id=event_id,
    )
    relationship.first_event_rewarded_at = now
    if event_id is not None:
        relationship.first_event_id = event_id
    await session.flush()
    return relationship


async def award_first_event_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
    event_id: int,
) -> ReferralRelationship | None:
    """Compatibility wrapper for confirmed event attendance."""

    return await award_first_activity_referral(
        session,
        invitee_user_id=invitee_user_id,
        event_id=event_id,
    )


async def award_active_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
) -> ReferralRelationship | None:
    """Compatibility no-op: the old third referral stage no longer exists."""

    return await session.scalar(
        select(ReferralRelationship).where(
            ReferralRelationship.invitee_id == invitee_user_id
        )
    )


def _invite_url(settings: Settings, code: str) -> str:
    username = (settings.bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start=ref_{code}"


def _share_text(code: str, invite_url: str, general_chat_url: str) -> str:
    bot_url = invite_url or OFFICIAL_BOT_URL
    return (
        "Присоединяйся к ЭРА 🔥\n\n"
        "ЭРА — среда, где из участника вырастают в лидера через реальные проекты, события и возможности.\n\n"
        f"Открой бот: {bot_url}\n"
        f"При регистрации введи мой код: {code}\n\n"
        "Баллы появляются не за ссылку и не за вступление в чат: "
        "пригласивший получает +30 после одобрения регистрации и ещё +70 после первого подтверждённого участия."
    )


async def get_referral_summary(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
) -> ReferralSummary:
    code_row = await get_or_create_referral_code(session, user.id)
    invited_count = int(
        await session.scalar(
            select(func.count(ReferralRelationship.id)).where(
                ReferralRelationship.inviter_id == user.id
            )
        )
        or 0
    )
    registered_count = int(
        await session.scalar(
            select(func.count(ReferralRelationship.id)).where(
                ReferralRelationship.inviter_id == user.id,
                ReferralRelationship.registration_rewarded_at.is_not(None),
            )
        )
        or 0
    )
    first_activity_count = int(
        await session.scalar(
            select(func.count(ReferralRelationship.id)).where(
                ReferralRelationship.inviter_id == user.id,
                ReferralRelationship.first_event_rewarded_at.is_not(None),
            )
        )
        or 0
    )
    now = datetime.now(timezone.utc)
    month_start, month_end = _month_bounds(now)
    earned_points = await _inviter_referral_points(session, inviter_id=user.id)
    monthly_earned_points = await _inviter_referral_points(
        session,
        inviter_id=user.id,
        start=month_start,
        end=month_end,
    )
    invite_url = _invite_url(settings, code_row.code)
    return ReferralSummary(
        code=code_row.code,
        invite_url=invite_url,
        share_text=_share_text(code_row.code, invite_url, settings.general_chat_url),
        invited_count=invited_count,
        registered_count=registered_count,
        first_event_count=first_activity_count,
        active_count=first_activity_count,
        earned_points=earned_points,
        monthly_earned_points=monthly_earned_points,
        monthly_cap=REFERRAL_MONTHLY_CAP,
    )
