"""Community Verification ToR: admin-run first-wave grace period for
existing chat members (§7-20), idempotent mass DM delivery tracking
(§10-14), and honest segment counts for the admin dashboard (§19-20).

Deliberately does NOT try to reconstruct "registration started but not
finished" from FSM storage -- that's only observable in Redis, not SQL, and
ToR §20 explicitly forbids faking precision the system doesn't actually
have. Every count here is derived from real rows: User, PendingChatJoinRequest,
CommunityVerificationDelivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.chat_moderation import CommunityVerificationCampaign, CommunityVerificationDelivery
from app.database.models import User
from app.services.audit_service import audit
from app.services.notification_service import BroadcastFailure, broadcast_detailed
from app.utils.constants import ApplicationStatus

ALLOWED_WINDOW_HOURS = (24, 48, 72, 120, 168)
DEFAULT_WINDOW_HOURS = 72
LAUNCH_KIND = "initial"
REMINDER_KIND = "reminder"
# Sentinel row for the one pinned chat post (ToR §8) -- 0 is never a real
# Telegram user id, so it can share the same delivery table / unique
# constraint as personal DMs instead of a second table for one row.
CHAT_PIN_KIND = "chat_pin"
CHAT_PIN_SENTINEL_TELEGRAM_ID = 0
# ToR §12's idempotency key, kept for documentation / external audit greps --
# the actual idempotency mechanism is the DB unique constraint on
# (campaign_id, telegram_id, kind), not a string comparison.
IDEMPOTENCY_KEY_TEMPLATE = "community_verification:{campaign_id}:{telegram_id}:{kind}"

# ToR §8 -- one pinned post in the general chat, and (ToR §10) the exact
# same text as a personal DM to every known user.
LAUNCH_ANNOUNCEMENT_TEXT = (
    "ЭРА становится больше, чем чат.\n\n"
    "Мы запускаем единое пространство ЭРА: события, проекты, задания, "
    "возможности, баллы, портфолио и «Мой вектор» — личный раздел, который "
    "помогает видеть свой прогресс, фокус и следующий шаг.\n\n"
    "Здесь можно не просто следить за событиями, а участвовать, собирать "
    "реальный опыт и постепенно брать больше ответственности внутри ЭРА.\n\n"
    "Мы также обновляем состав сообщества, чтобы в общем пространстве "
    "оставались реальные участники ЭРА.\n\n"
    "Пройди короткую регистрацию и подтверждение — после этого твой профиль "
    "станет частью новой системы."
)

# ToR §14 -- only to people who haven't started/finished registration; never
# to pending/approved/rejected (enforced by reminder_eligible_telegram_ids).
REMINDER_TEXT = (
    "До завершения первой верификации ЭРА — 1 день.\n\n"
    "Если ещё не зарегистрировался, открой ЭРА и создай свой профиль.\n\n"
    "Это займёт несколько минут и даст доступ ко всей новой системе: "
    "событиям, проектам, возможностям и «Моему вектору»."
)


class CampaignError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CampaignSegments:
    """ToR §19/§54. `chat_members_total` and `not_registered_estimate` are
    explicitly labeled estimates (ToR §20) -- Telegram's Bot API gives a
    member *count*, never a member list, so individuals in that gap can
    never be enumerated, only estimated in aggregate."""

    chat_members_total: int | None
    known_to_system: int
    pending: int
    approved: int
    rejected: int
    needs_info: int
    notified: int
    unreachable: int
    not_registered_estimate: int | None


@dataclass(frozen=True)
class CampaignStatusOut:
    campaign: CommunityVerificationCampaign | None
    segments: CampaignSegments


async def active_campaign(session: AsyncSession) -> CommunityVerificationCampaign | None:
    return await session.scalar(
        select(CommunityVerificationCampaign)
        .where(CommunityVerificationCampaign.status == "active")
        .order_by(CommunityVerificationCampaign.id.desc())
    )


async def latest_campaign(session: AsyncSession) -> CommunityVerificationCampaign | None:
    return await session.scalar(
        select(CommunityVerificationCampaign).order_by(CommunityVerificationCampaign.id.desc())
    )


async def start_campaign(
    session: AsyncSession, *, window_hours: int, started_by: int
) -> CommunityVerificationCampaign:
    if window_hours <= 0 or window_hours > 24 * 30:
        raise CampaignError("invalid_window")
    if await active_campaign(session) is not None:
        raise CampaignError("campaign_already_active")
    now = datetime.now(timezone.utc)
    campaign = CommunityVerificationCampaign(
        status="active",
        window_hours=window_hours,
        started_at=now,
        ends_at=now + timedelta(hours=window_hours),
        started_by=started_by,
    )
    session.add(campaign)
    await session.flush()
    await audit(
        session,
        actor_id=started_by,
        action="community_verification.started",
        entity_type="community_verification_campaign",
        entity_id=campaign.id,
        new_value={"window_hours": window_hours},
    )
    return campaign


async def complete_campaign(
    session: AsyncSession, campaign: CommunityVerificationCampaign, *, actor_id: int | None = None
) -> CommunityVerificationCampaign:
    if campaign.status == "completed":
        return campaign
    campaign.status = "completed"
    campaign.completed_at = datetime.now(timezone.utc)
    await session.flush()
    await audit(
        session,
        actor_id=actor_id,
        action="community_verification.completed",
        entity_type="community_verification_campaign",
        entity_id=campaign.id,
        new_value=None,
    )
    return campaign


async def complete_expired_campaigns(session: AsyncSession) -> int:
    """Scheduler hook (Phase 3): a campaign simply stops being "active" once
    its window elapses -- ToR §15 is explicit this must NEVER cascade into
    any chat restriction, it only changes what the admin dashboard shows."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.scalars(
            select(CommunityVerificationCampaign).where(
                CommunityVerificationCampaign.status == "active",
                CommunityVerificationCampaign.ends_at.is_not(None),
                CommunityVerificationCampaign.ends_at <= now,
            )
        )
    ).all()
    for campaign in rows:
        await complete_campaign(session, campaign)
    return len(rows)


async def eligible_launch_recipients(session: AsyncSession) -> list[User]:
    """ToR §10: everyone the system can plausibly DM -- known telegram_id,
    not blocked/archived. Includes already-approved users; the launch
    message itself is informational (ToR §8's pinned-post text), not a
    forced re-registration demand."""
    return list(
        (
            await session.scalars(
                select(User).where(User.is_blocked.is_(False), User.is_archived.is_(False))
            )
        ).all()
    )


async def reminder_eligible_telegram_ids(
    session: AsyncSession, campaign: CommunityVerificationCampaign
) -> list[int]:
    """ToR §14: only people who were actually notified in wave 1 AND still
    have no User row at all (never started, or started and never finished
    the FSM -- both look identical from SQL, and that's fine: either way
    they haven't registered). Never re-sent to pending/approved/rejected."""
    delivered = (
        await session.scalars(
            select(CommunityVerificationDelivery.telegram_id).where(
                CommunityVerificationDelivery.campaign_id == campaign.id,
                CommunityVerificationDelivery.kind == LAUNCH_KIND,
                CommunityVerificationDelivery.status == "sent",
            )
        )
    ).all()
    if not delivered:
        return []
    known = set(
        (
            await session.scalars(
                select(User.telegram_id).where(User.telegram_id.in_(delivered))
            )
        ).all()
    )
    return [telegram_id for telegram_id in delivered if telegram_id not in known]


async def _chat_member_count(bot: Bot, settings: Settings) -> int | None:
    if settings.general_chat_id is None:
        return None
    try:
        return await bot.get_chat_member_count(settings.general_chat_id)
    except TelegramAPIError:
        return None


async def campaign_segments(
    session: AsyncSession, bot: Bot, settings: Settings, campaign: CommunityVerificationCampaign | None
) -> CampaignSegments:
    chat_total = await _chat_member_count(bot, settings)

    status_counts = dict(
        (
            await session.execute(
                select(User.application_status, func.count()).group_by(User.application_status)
            )
        ).all()
    )
    known_to_system = sum(status_counts.values())
    pending = int(status_counts.get(ApplicationStatus.PENDING, 0))
    approved = int(status_counts.get(ApplicationStatus.APPROVED, 0))
    rejected = int(status_counts.get(ApplicationStatus.REJECTED, 0))
    needs_info = int(status_counts.get(ApplicationStatus.NEEDS_INFO, 0))

    notified = unreachable = 0
    if campaign is not None:
        notified = int(
            await session.scalar(
                select(func.count(func.distinct(CommunityVerificationDelivery.telegram_id))).where(
                    CommunityVerificationDelivery.campaign_id == campaign.id,
                    CommunityVerificationDelivery.status == "sent",
                )
            )
            or 0
        )
        unreachable = int(
            await session.scalar(
                select(func.count(func.distinct(CommunityVerificationDelivery.telegram_id))).where(
                    CommunityVerificationDelivery.campaign_id == campaign.id,
                    CommunityVerificationDelivery.status.in_(["blocked", "unreachable"]),
                )
            )
            or 0
        )

    not_registered_estimate = max(0, chat_total - known_to_system) if chat_total is not None else None

    return CampaignSegments(
        chat_members_total=chat_total,
        known_to_system=known_to_system,
        pending=pending,
        approved=approved,
        rejected=rejected,
        needs_info=needs_info,
        notified=notified,
        unreachable=unreachable,
        not_registered_estimate=not_registered_estimate,
    )


async def campaign_status(session: AsyncSession, bot: Bot, settings: Settings) -> CampaignStatusOut:
    campaign = await latest_campaign(session)
    segments = await campaign_segments(session, bot, settings, campaign)
    return CampaignStatusOut(campaign=campaign, segments=segments)


@dataclass(frozen=True)
class NotRegisteredEntry:
    telegram_id: int
    delivery_status: str
    notified_at: datetime | None


async def not_registered_recipients(
    session: AsyncSession, campaign: CommunityVerificationCampaign
) -> list[NotRegisteredEntry]:
    """ToR §16: the only individually-actionable "not registered" list is
    people we actually tried to notify (we have their telegram_id) who
    still have no User row -- never the unknowable "in the chat but never
    interacted with the bot" population (ToR §20)."""
    rows = (
        await session.execute(
            select(CommunityVerificationDelivery.telegram_id, CommunityVerificationDelivery.status, CommunityVerificationDelivery.sent_at)
            .where(
                CommunityVerificationDelivery.campaign_id == campaign.id,
                CommunityVerificationDelivery.kind == LAUNCH_KIND,
            )
        )
    ).all()
    if not rows:
        return []
    telegram_ids = [row[0] for row in rows]
    known = set(
        (await session.scalars(select(User.telegram_id).where(User.telegram_id.in_(telegram_ids)))).all()
    )
    return [
        NotRegisteredEntry(telegram_id=telegram_id, delivery_status=status, notified_at=sent_at)
        for telegram_id, status, sent_at in rows
        if telegram_id not in known
    ]


def _classify_failure(failure: BroadcastFailure | None) -> str:
    """ToR §11's status vocabulary, mapped from the same
    notification_service failure reasons every other broadcast in this repo
    already produces (app/services/admin_broadcast_service.py)."""
    if failure is None:
        return "sent"
    reason = failure.reason
    if reason.startswith("TelegramForbiddenError"):
        return "blocked"
    if reason.startswith("TelegramNotFound") or reason.startswith("TelegramBadRequest"):
        return "unreachable"
    return "failed"


async def _already_attempted(session: AsyncSession, campaign_id: int, kind: str) -> set[int]:
    return set(
        (
            await session.scalars(
                select(CommunityVerificationDelivery.telegram_id).where(
                    CommunityVerificationDelivery.campaign_id == campaign_id,
                    CommunityVerificationDelivery.kind == kind,
                )
            )
        ).all()
    )


@dataclass(frozen=True)
class WaveResult:
    total_recipients: int
    already_attempted: int
    sent: int
    blocked: int
    unreachable: int
    failed: int


async def _send_wave(
    session: AsyncSession,
    bot: Bot,
    *,
    campaign: CommunityVerificationCampaign,
    kind: str,
    telegram_ids: list[int],
    text: str,
) -> WaveResult:
    """Shared idempotent send-and-record path for both the launch wave and
    the reminder wave (ToR §12/§56: never send the same kind twice to the
    same person for the same campaign -- enforced here by pre-filtering
    against existing rows, and structurally by the DB unique constraint if
    two requests ever race)."""
    attempted = await _already_attempted(session, campaign.id, kind)
    pending_ids = [telegram_id for telegram_id in telegram_ids if telegram_id not in attempted]
    if not pending_ids:
        return WaveResult(len(telegram_ids), len(telegram_ids), 0, 0, 0, 0)

    result = await broadcast_detailed(bot, pending_ids, text)
    failed_by_id = {failure.chat_id: failure for failure in result.failures}
    now = datetime.now(timezone.utc)
    counts = {"sent": 0, "blocked": 0, "unreachable": 0, "failed": 0}
    for telegram_id in pending_ids:
        status = _classify_failure(failed_by_id.get(telegram_id))
        counts[status] += 1
        session.add(
            CommunityVerificationDelivery(
                campaign_id=campaign.id,
                telegram_id=telegram_id,
                kind=kind,
                status=status,
                attempt_count=1,
                sent_at=now if status == "sent" else None,
                last_attempt_at=now,
            )
        )
    await session.flush()
    return WaveResult(
        total_recipients=len(telegram_ids),
        already_attempted=len(attempted),
        sent=counts["sent"],
        blocked=counts["blocked"],
        unreachable=counts["unreachable"],
        failed=counts["failed"],
    )


async def send_launch_wave(
    session: AsyncSession, bot: Bot, campaign: CommunityVerificationCampaign, *, actor_id: int | None
) -> WaveResult:
    recipients = await eligible_launch_recipients(session)
    result = await _send_wave(
        session,
        bot,
        campaign=campaign,
        kind=LAUNCH_KIND,
        telegram_ids=[user.telegram_id for user in recipients],
        text=LAUNCH_ANNOUNCEMENT_TEXT,
    )
    await audit(
        session,
        actor_id=actor_id,
        action="community_verification.launch_sent",
        entity_type="community_verification_campaign",
        entity_id=campaign.id,
        new_value={"sent": result.sent, "blocked": result.blocked, "unreachable": result.unreachable, "failed": result.failed},
    )
    return result


async def send_reminder_wave(
    session: AsyncSession, bot: Bot, campaign: CommunityVerificationCampaign, *, actor_id: int | None = None
) -> WaveResult:
    telegram_ids = await reminder_eligible_telegram_ids(session, campaign)
    result = await _send_wave(
        session, bot, campaign=campaign, kind=REMINDER_KIND, telegram_ids=telegram_ids, text=REMINDER_TEXT
    )
    if result.sent or result.blocked or result.unreachable or result.failed:
        await audit(
            session,
            actor_id=actor_id,
            action="community_verification.reminder_sent",
            entity_type="community_verification_campaign",
            entity_id=campaign.id,
            new_value={"sent": result.sent, "blocked": result.blocked, "unreachable": result.unreachable, "failed": result.failed},
        )
    return result


async def post_launch_pin(
    session: AsyncSession, bot: Bot, settings: Settings, campaign: CommunityVerificationCampaign, *, actor_id: int | None
) -> str:
    """ToR §8: exactly one pinned post in the general chat. Only recorded on
    confirmed success, unlike the personal-DM rows -- a failed pin attempt
    (bot temporarily lacks pin rights, etc.) should stay retryable rather
    than permanently "used up" the one allowed post.

    Returns one of "posted" / "already_posted" / "failed" / "no_chat_bound"
    -- a plain bool here previously conflated "already done" with "just
    failed", which produced misleading admin-facing copy."""
    if settings.general_chat_id is None:
        return "no_chat_bound"
    already = await session.scalar(
        select(CommunityVerificationDelivery.id).where(
            CommunityVerificationDelivery.campaign_id == campaign.id,
            CommunityVerificationDelivery.kind == CHAT_PIN_KIND,
        )
    )
    if already is not None:
        return "already_posted"
    try:
        message = await bot.send_message(settings.general_chat_id, LAUNCH_ANNOUNCEMENT_TEXT)
        await bot.pin_chat_message(settings.general_chat_id, message.message_id, disable_notification=False)
    except TelegramAPIError:
        return "failed"
    now = datetime.now(timezone.utc)
    session.add(
        CommunityVerificationDelivery(
            campaign_id=campaign.id,
            telegram_id=CHAT_PIN_SENTINEL_TELEGRAM_ID,
            kind=CHAT_PIN_KIND,
            status="sent",
            attempt_count=1,
            sent_at=now,
            last_attempt_at=now,
        )
    )
    await audit(
        session,
        actor_id=actor_id,
        action="community_verification.pin_posted",
        entity_type="community_verification_campaign",
        entity_id=campaign.id,
        new_value=None,
    )
    return "posted"


async def run_verification_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    """Scheduler hook (ToR §14): fires the reminder wave once a campaign is
    within its last 24h. Safe to poll repeatedly -- send_reminder_wave's own
    idempotency means only genuinely new-since-last-poll recipients ever get
    a second message."""
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        campaigns = (
            await session.scalars(
                select(CommunityVerificationCampaign).where(
                    CommunityVerificationCampaign.status == "active",
                    CommunityVerificationCampaign.ends_at.is_not(None),
                    CommunityVerificationCampaign.ends_at > now,
                    CommunityVerificationCampaign.ends_at <= now + timedelta(hours=24),
                )
            )
        ).all()
        for campaign in campaigns:
            await send_reminder_wave(session, bot, campaign)
        await complete_expired_campaigns(session)
        # session_factory() here is the raw AsyncSession context manager, not
        # the FastAPI request-scoped get_session dependency that auto-commits
        # -- without this, everything above rolls back on __aexit__ (same bug
        # class documented in app/api/deps.py::get_session).
        await session.commit()
