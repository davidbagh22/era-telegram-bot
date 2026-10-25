from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.community_verification_models import (
    CommunityMemberIdentity,
    CommunityVerificationCampaign,
    CommunityVerificationDelivery,
)
from app.database.models import User
from app.utils.constants import ApplicationStatus

logger = logging.getLogger(__name__)

PRESET_DURATION_HOURS = frozenset({24, 48, 72, 120, 168})
MIN_CUSTOM_HOURS = 1
MAX_CUSTOM_HOURS = 24 * 30


@dataclass(frozen=True)
class CampaignStartResult:
    campaign: CommunityVerificationCampaign
    created: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def observe_member_identity(
    session: AsyncSession,
    *,
    telegram_id: int,
    general_chat_id: int | None,
    user: User | None,
    is_current_member: bool,
    seen_at: datetime | None = None,
) -> CommunityMemberIdentity:
    now = seen_at or utcnow()
    row = await session.get(CommunityMemberIdentity, telegram_id)
    if row is None:
        row = CommunityMemberIdentity(
            telegram_id=telegram_id,
            user_id=user.id if user else None,
            general_chat_id=general_chat_id,
            first_seen_at=now,
            last_seen_at=now,
            is_current_member=is_current_member,
        )
        session.add(row)
    else:
        if user is not None:
            row.user_id = user.id
        if general_chat_id is not None:
            row.general_chat_id = general_chat_id
        row.last_seen_at = now
        row.is_current_member = is_current_member
    await session.flush()
    return row


async def sync_known_users(session: AsyncSession, general_chat_id: int | None) -> int:
    """Make canonical User rows addressable by a campaign without pretending
    Telegram exposes a full member list. Unregistered chat identities are
    learned separately by the chat observer middleware.
    """
    users = list((await session.scalars(select(User))).all())
    for user in users:
        existing = await session.get(CommunityMemberIdentity, user.telegram_id)
        if existing is None:
            await observe_member_identity(
                session,
                telegram_id=user.telegram_id,
                general_chat_id=general_chat_id,
                user=user,
                is_current_member=True,
            )
        elif existing.user_id is None:
            existing.user_id = user.id
    await session.flush()
    return len(users)


def validate_duration(hours: int) -> int:
    value = int(hours)
    if value in PRESET_DURATION_HOURS:
        return value
    if MIN_CUSTOM_HOURS <= value <= MAX_CUSTOM_HOURS:
        return value
    raise ValueError("invalid_verification_duration")


async def active_campaign(session: AsyncSession) -> CommunityVerificationCampaign | None:
    return await session.scalar(
        select(CommunityVerificationCampaign)
        .where(CommunityVerificationCampaign.status == "active")
        .order_by(CommunityVerificationCampaign.started_at.desc())
        .limit(1)
    )


async def _group_launch_message(
    bot: Bot,
    settings: Settings,
    campaign: CommunityVerificationCampaign,
    *,
    pin: bool,
) -> None:
    if not settings.general_chat_id or campaign.group_message_id:
        return
    try:
        me = await bot.get_me()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Пройти проверку / открыть ЭРА",
                    url=f"https://t.me/{me.username}?start=registration",
                )
            ]]
        )
        message = await bot.send_message(
            settings.general_chat_id,
            "🔥 Проверка состава ЭРА\n\n"
            "Мы обновляем актуальный состав сообщества. Если Вы ещё не прошли регистрацию — откройте личный бот и заполните анкету. "
            "Если заявка уже на рассмотрении или одобрена, повторно ничего отправлять не нужно.\n\n"
            "После завершения периода никто не будет удалён автоматически — спорные случаи остаются на решение команды.",
            reply_markup=keyboard,
        )
        campaign.group_message_id = message.message_id
        if pin:
            try:
                await bot.pin_chat_message(
                    settings.general_chat_id,
                    message.message_id,
                    disable_notification=True,
                )
                campaign.group_pinned = True
            except TelegramAPIError:
                logger.exception("Could not pin Community Verification launch message")
    except TelegramAPIError:
        # Campaign state is authoritative. A Telegram delivery problem is
        # recorded/visible but must not roll back the campaign itself.
        logger.exception("Could not post Community Verification launch message")


async def _ensure_delivery(
    session: AsyncSession,
    campaign: CommunityVerificationCampaign,
    identity: CommunityMemberIdentity,
    kind: str,
) -> CommunityVerificationDelivery:
    key = f"community_verification:{campaign.id}:{identity.telegram_id}:{kind}"
    row = await session.scalar(
        select(CommunityVerificationDelivery).where(
            CommunityVerificationDelivery.idempotency_key == key
        )
    )
    if row is not None:
        return row
    row = CommunityVerificationDelivery(
        campaign_id=campaign.id,
        telegram_id=identity.telegram_id,
        user_id=identity.user_id,
        delivery_kind=kind,
        status="pending",
        idempotency_key=key,
    )
    session.add(row)
    await session.flush()
    return row


async def _identity_user(
    session: AsyncSession, identity: CommunityMemberIdentity
) -> User | None:
    if identity.user_id:
        return await session.get(User, identity.user_id)
    return await session.scalar(
        select(User).where(User.telegram_id == identity.telegram_id)
    )


def _dm_copy(user: User | None, kind: str) -> tuple[str, bool]:
    """Return text and whether this recipient needs a registration reminder."""
    if user is None:
        prefix = "Напоминание" if kind == "reminder" else "Проверка состава ЭРА"
        return (
            f"🔥 {prefix}\n\nЧтобы подтвердить участие в сообществе, пройдите регистрацию в личном боте. "
            "После отправки анкеты повторно заполнять её не нужно.",
            True,
        )
    if user.application_status == ApplicationStatus.PENDING:
        return (
            "✅ Ваша анкета уже получена и находится на рассмотрении. Повторная регистрация не нужна.",
            False,
        )
    if user.application_status == ApplicationStatus.NEEDS_INFO:
        return (
            "Нужно уточнение по Вашей заявке ЭРА. Проверьте последнее сообщение от бота и отправьте запрошенную информацию.",
            False,
        )
    if user.application_status == ApplicationStatus.APPROVED:
        return (
            "✅ Ваш профиль ЭРА уже подтверждён. Никаких дополнительных действий для проверки состава не требуется.",
            False,
        )
    return (
        "Ваша заявка в ЭРА ранее не была одобрена. Повторная регистрация по этой кампании не требуется.",
        False,
    )


async def deliver_identity(
    bot: Bot,
    session: AsyncSession,
    campaign: CommunityVerificationCampaign,
    identity: CommunityMemberIdentity,
    *,
    kind: str,
) -> CommunityVerificationDelivery:
    delivery = await _ensure_delivery(session, campaign, identity, kind)
    if delivery.status in {"sent", "skipped", "blocked", "unreachable"}:
        return delivery
    user = await _identity_user(session, identity)
    if user is not None and identity.user_id != user.id:
        identity.user_id = user.id
        delivery.user_id = user.id

    text, needs_registration = _dm_copy(user, kind)
    if kind == "reminder" and not needs_registration:
        # PENDING/APPROVED/REJECTED never receive a registration reminder.
        delivery.status = "skipped"
        delivery.error_code = "registration_reminder_not_applicable"
        return delivery

    delivery.attempt_count += 1
    delivery.last_attempt_at = utcnow()
    try:
        await bot.send_message(identity.telegram_id, text)
    except TelegramForbiddenError:
        delivery.status = "blocked"
        delivery.error_code = "bot_blocked"
    except TelegramBadRequest:
        delivery.status = "unreachable"
        delivery.error_code = "telegram_unreachable"
    except TelegramAPIError:
        delivery.status = "failed"
        delivery.error_code = "telegram_delivery_failed"
    else:
        delivery.status = "sent"
        delivery.sent_at = utcnow()
        delivery.error_code = None
    return delivery


async def start_campaign(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    *,
    duration_hours: int,
    actor_id: int | None,
    pin_group_message: bool = True,
    idempotency_key: str | None = None,
) -> CampaignStartResult:
    duration_hours = validate_duration(duration_hours)
    existing = await active_campaign(session)
    if existing is not None:
        return CampaignStartResult(existing, False)

    now = utcnow()
    launch_key = idempotency_key or f"community_verification:{now.date().isoformat()}:{duration_hours}"
    by_key = await session.scalar(
        select(CommunityVerificationCampaign).where(
            CommunityVerificationCampaign.launch_key == launch_key
        )
    )
    if by_key is not None:
        return CampaignStartResult(by_key, False)

    campaign = CommunityVerificationCampaign(
        launch_key=launch_key,
        status="active",
        duration_hours=duration_hours,
        started_at=now,
        ends_at=now + timedelta(hours=duration_hours),
        created_by=actor_id,
    )
    session.add(campaign)
    await session.flush()

    await sync_known_users(session, settings.general_chat_id)
    identities = list(
        (
            await session.scalars(
                select(CommunityMemberIdentity)
                .where(CommunityMemberIdentity.is_current_member.is_(True))
                .order_by(CommunityMemberIdentity.telegram_id)
            )
        ).all()
    )
    await _group_launch_message(bot, settings, campaign, pin=pin_group_message)
    for identity in identities:
        await deliver_identity(bot, session, campaign, identity, kind="launch")
    await session.flush()
    return CampaignStartResult(campaign, True)


async def complete_due_campaigns(session: AsyncSession, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    rows = list(
        (
            await session.scalars(
                select(CommunityVerificationCampaign).where(
                    CommunityVerificationCampaign.status == "active",
                    CommunityVerificationCampaign.ends_at <= now,
                )
            )
        ).all()
    )
    for campaign in rows:
        campaign.status = "completed"
        campaign.completed_at = now
    await session.flush()
    return len(rows)


async def remind_selected(
    bot: Bot,
    session: AsyncSession,
    campaign: CommunityVerificationCampaign,
    telegram_ids: list[int],
) -> list[CommunityVerificationDelivery]:
    identities = list(
        (
            await session.scalars(
                select(CommunityMemberIdentity).where(
                    CommunityMemberIdentity.telegram_id.in_(telegram_ids),
                    CommunityMemberIdentity.is_current_member.is_(True),
                )
            )
        ).all()
    )
    return [
        await deliver_identity(bot, session, campaign, identity, kind="reminder")
        for identity in identities
    ]


async def retain_selected(session: AsyncSession, telegram_ids: list[int]) -> int:
    rows = list(
        (
            await session.scalars(
                select(CommunityMemberIdentity).where(
                    CommunityMemberIdentity.telegram_id.in_(telegram_ids)
                )
            )
        ).all()
    )
    for row in rows:
        row.retained_by_admin = True
        row.is_current_member = True
    await session.flush()
    return len(rows)


async def remove_selected(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    telegram_ids: list[int],
) -> tuple[int, int]:
    if not settings.general_chat_id:
        raise ValueError("general_chat_not_configured")
    removed = failed = 0
    rows = list(
        (
            await session.scalars(
                select(CommunityMemberIdentity).where(
                    CommunityMemberIdentity.telegram_id.in_(telegram_ids)
                )
            )
        ).all()
    )
    for row in rows:
        try:
            await bot.ban_chat_member(settings.general_chat_id, row.telegram_id)
            # Kick, but do not create a permanent ban: an approved future join
            # request can be processed normally by the single Chat Access flow.
            await bot.unban_chat_member(
                settings.general_chat_id,
                row.telegram_id,
                only_if_banned=True,
            )
        except TelegramAPIError:
            failed += 1
            continue
        row.is_current_member = False
        row.retained_by_admin = False
        removed += 1
    await session.flush()
    return removed, failed


async def campaign_segment_rows(
    session: AsyncSession,
    campaign: CommunityVerificationCampaign,
) -> list[dict]:
    identities = list(
        (
            await session.scalars(
                select(CommunityMemberIdentity).order_by(
                    CommunityMemberIdentity.is_current_member.desc(),
                    CommunityMemberIdentity.last_seen_at.desc(),
                )
            )
        ).all()
    )
    deliveries = list(
        (
            await session.scalars(
                select(CommunityVerificationDelivery).where(
                    CommunityVerificationDelivery.campaign_id == campaign.id,
                    CommunityVerificationDelivery.delivery_kind == "launch",
                )
            )
        ).all()
    )
    delivery_by_tg = {row.telegram_id: row for row in deliveries}
    result: list[dict] = []
    for identity in identities:
        user = await _identity_user(session, identity)
        if user is None:
            registration_status = "not_started"
        else:
            registration_status = str(user.application_status)
        delivery = delivery_by_tg.get(identity.telegram_id)
        result.append(
            {
                "telegram_id": identity.telegram_id,
                "user_id": user.id if user else None,
                "name": (
                    f"{user.first_name} {user.last_name or ''}".strip()
                    if user
                    else "Не зарегистрирован"
                ),
                "registration_status": registration_status,
                "is_current_member": identity.is_current_member,
                "retained_by_admin": identity.retained_by_admin,
                "delivery_status": delivery.status if delivery else "pending",
                "attempt_count": delivery.attempt_count if delivery else 0,
                "sent_at": delivery.sent_at.isoformat() if delivery and delivery.sent_at else None,
                "last_attempt_at": (
                    delivery.last_attempt_at.isoformat()
                    if delivery and delivery.last_attempt_at
                    else None
                ),
            }
        )
    return result
