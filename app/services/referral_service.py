from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.referral_models import ReferralCode, ReferralRelationship
from app.services.points_service import add_points, make_idempotency_key
from app.utils.constants import ApplicationStatus

REGISTRATION_REFERRAL_POINTS = 200
FIRST_EVENT_REFERRAL_POINTS = 500
CODE_LENGTH = 6
OFFICIAL_BOT_HANDLE = "@ERA_1bot"
OFFICIAL_BOT_URL = "https://t.me/ERA_1bot"


@dataclass(frozen=True)
class ReferralSummary:
    code: str
    invite_url: str
    share_text: str
    invited_count: int
    registered_count: int
    first_event_count: int
    earned_points: int


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

    # Serialize concurrent requests for the same participant before creating
    # their permanent public code.
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
            # A different participant may have claimed the same random code
            # between our read and write. Generate another one without
            # rolling back the caller's transaction.
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


async def award_registration_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
) -> ReferralRelationship | None:
    """Award +200/+200 after the newcomer is approved and actually enters the general chat.

    This function intentionally does not try to infer Telegram membership itself. Callers
    invoke it only from authoritative chat-join/unrestrict paths.
    """

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

    await add_points(
        session,
        user_id=relationship.inviter_id,
        points=REGISTRATION_REFERRAL_POINTS,
        reason="Друг вступил в ЭРА и завершил регистрацию",
        approved_by=None,
        source_type="referral_registration",
        source_id=relationship.id,
        idempotency_key=make_idempotency_key(
            "referral", "registration", relationship.id, "inviter"
        ),
    )
    await add_points(
        session,
        user_id=relationship.invitee_id,
        points=REGISTRATION_REFERRAL_POINTS,
        reason="Регистрация в ЭРА по приглашению друга",
        approved_by=None,
        source_type="referral_registration",
        source_id=relationship.id,
        idempotency_key=make_idempotency_key(
            "referral", "registration", relationship.id, "invitee"
        ),
    )
    relationship.registration_rewarded_at = datetime.now(timezone.utc)
    await session.flush()
    return relationship


async def award_first_event_referral(
    session: AsyncSession,
    *,
    invitee_user_id: int,
    event_id: int,
) -> ReferralRelationship | None:
    """Award +500/+500 once, after the newcomer's first confirmed attendance."""

    relationship = await session.scalar(
        select(ReferralRelationship)
        .where(ReferralRelationship.invitee_id == invitee_user_id)
        .with_for_update()
    )
    if relationship is None or relationship.first_event_rewarded_at is not None:
        return relationship
    # The referral lifecycle is intentionally ordered. Event attendance cannot
    # silently replace the registration + general-chat condition.
    if relationship.registration_rewarded_at is None:
        return relationship

    await add_points(
        session,
        user_id=relationship.inviter_id,
        points=FIRST_EVENT_REFERRAL_POINTS,
        reason="Приглашённый друг пришёл на первое мероприятие",
        approved_by=None,
        related_event_id=event_id,
        source_type="referral_first_event",
        source_id=relationship.id,
        idempotency_key=make_idempotency_key(
            "referral", "first_event", relationship.id, "inviter"
        ),
    )
    await add_points(
        session,
        user_id=relationship.invitee_id,
        points=FIRST_EVENT_REFERRAL_POINTS,
        reason="Первое мероприятие после приглашения в ЭРА",
        approved_by=None,
        related_event_id=event_id,
        source_type="referral_first_event",
        source_id=relationship.id,
        idempotency_key=make_idempotency_key(
            "referral", "first_event", relationship.id, "invitee"
        ),
    )
    relationship.first_event_rewarded_at = datetime.now(timezone.utc)
    relationship.first_event_id = event_id
    await session.flush()
    return relationship


def _invite_url(settings: Settings, code: str) -> str:
    username = (settings.bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start=ref_{code}"


def _share_text(
    code: str,
    invite_url: str,
    general_chat_url: str,
) -> str:
    bot_url = invite_url or OFFICIAL_BOT_URL
    chat_url = general_chat_url.strip() or "https://t.me/+Q6MzTrnR21dmZjgy"
    return (
        "Присоединяйся к ЭРА 🔥\n\n"
        "ЭРА — это сообщество, где можно не просто знакомиться с новыми людьми, а "
        "пробовать себя в реальных проектах, находить возможности, развивать навыки "
        "и постепенно понимать, куда двигаться дальше.\n\n"
        "Внутри тебя ждут мероприятия, проекты, задачи, новые знакомства и «Мой вектор» — "
        "инструмент, который помогает лучше понять себя, своё состояние, сильные стороны "
        "и выбрать следующий шаг.\n\n"
        "Я уже внутри и приглашаю тебя присоединиться.\n\n"
        f"🤖 Бот ЭРА: {OFFICIAL_BOT_HANDLE}\n{bot_url}\n\n"
        f"💬 Общий чат:\n{chat_url}\n\n"
        f"При регистрации введи мой код: {code}\n\n"
        f"После регистрации и вступления в общий чат мы оба получим по "
        f"{REGISTRATION_REFERRAL_POINTS} баллов.\n"
        "А когда ты впервые придёшь на мероприятие и подтвердишь участие — ещё по "
        f"{FIRST_EVENT_REFERRAL_POINTS} баллов каждому.\n\n"
        "Не обязательно сразу знать, чего ты хочешь. ЭРА как раз помогает это понять — "
        "через людей, опыт и реальные действия."
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
    first_event_count = int(
        await session.scalar(
            select(func.count(ReferralRelationship.id)).where(
                ReferralRelationship.inviter_id == user.id,
                ReferralRelationship.first_event_rewarded_at.is_not(None),
            )
        )
        or 0
    )
    invite_url = _invite_url(settings, code_row.code)
    return ReferralSummary(
        code=code_row.code,
        invite_url=invite_url,
        share_text=_share_text(
            code_row.code,
            invite_url,
            settings.general_chat_url,
        ),
        invited_count=invited_count,
        registered_count=registered_count,
        first_event_count=first_event_count,
        earned_points=(
            registered_count * REGISTRATION_REFERRAL_POINTS
            + first_event_count * FIRST_EVENT_REFERRAL_POINTS
        ),
    )
