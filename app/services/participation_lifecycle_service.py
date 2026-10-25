from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, User
from app.database.participation_models import (
    ParticipationLifecycle,
    ReactivationCampaign,
    ReactivationDelivery,
)
from app.services.bot_notification_service import PrimaryAction, send_bot_notification
from app.services.meaningful_activity_service import (
    has_current_responsibility,
    last_meaningful_activity_at,
)
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import miniapp_profile_url

CURRENT_ONBOARDING_VERSION = 1

MODE_ACTIVE = "ACTIVE"
MODE_LIGHT = "LIGHT"
MODE_PAUSED = "PAUSED"
MODE_OBSERVER = "OBSERVER"
MODE_EXITED = "EXITED"
PARTICIPATION_MODES = frozenset(
    {MODE_ACTIVE, MODE_LIGHT, MODE_PAUSED, MODE_OBSERVER, MODE_EXITED}
)

STATE_ADAPTATION = "ADAPTATION"
STATE_ACTIVE = "ACTIVE"
STATE_COOLING = "COOLING"
STATE_INACTIVE = "INACTIVE"
STATE_DORMANT = "DORMANT"
STATE_ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"
ACTIVITY_STATES = frozenset(
    {
        STATE_ADAPTATION,
        STATE_ACTIVE,
        STATE_COOLING,
        STATE_INACTIVE,
        STATE_DORMANT,
        STATE_ARCHIVE_CANDIDATE,
    }
)

DEFAULT_THRESHOLDS = {
    "adaptation_days": 21,
    "active_days": 14,
    "cooling_end_days": 29,
    "inactive_end_days": 59,
    "dormant_end_days": 89,
}
THRESHOLDS_SETTING_KEY = "participation_lifecycle_thresholds"
REACTIVATION_DELAYS_DAYS = (0, 7, 14, 30, 60)
MAX_REACTIVATION_ATTEMPTS = 5
QUIET_START_HOUR = 22
QUIET_END_HOUR = 9


@dataclass(frozen=True)
class LifecycleSnapshot:
    participation_mode: str
    activity_state: str
    last_meaningful_at: datetime | None
    pause_until: date | None
    onboarding_version: int
    onboarding_completed_at: datetime | None

    @property
    def needs_onboarding(self) -> bool:
        return self.onboarding_version < CURRENT_ONBOARDING_VERSION


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def get_thresholds(session: AsyncSession) -> dict[str, int]:
    result = dict(DEFAULT_THRESHOLDS)
    setting = await session.scalar(select(AppSetting).where(AppSetting.key == THRESHOLDS_SETTING_KEY))
    if setting is None or not isinstance(setting.value, dict):
        return result
    for key, default in DEFAULT_THRESHOLDS.items():
        try:
            value = int(setting.value.get(key, default))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            result[key] = value
    # Keep state windows ordered even if an administrator enters a bad value.
    result["active_days"] = max(1, result["active_days"])
    result["adaptation_days"] = max(result["active_days"], result["adaptation_days"])
    result["cooling_end_days"] = max(result["active_days"] + 1, result["cooling_end_days"])
    result["inactive_end_days"] = max(result["cooling_end_days"] + 1, result["inactive_end_days"])
    result["dormant_end_days"] = max(result["inactive_end_days"] + 1, result["dormant_end_days"])
    return result


async def get_or_create_lifecycle(session: AsyncSession, user: User) -> ParticipationLifecycle:
    row = await session.get(ParticipationLifecycle, user.id)
    if row is not None:
        return row
    now = _now()
    row = ParticipationLifecycle(
        user_id=user.id,
        participation_mode=MODE_ACTIVE,
        activity_state=STATE_ADAPTATION,
        state_since=now,
        onboarding_version=0,
    )
    session.add(row)
    await session.flush()
    return row


async def evaluate_activity_state(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> tuple[str, datetime | None]:
    now = _as_utc(now) or _now()
    thresholds = await get_thresholds(session)
    latest = _as_utc(await last_meaningful_activity_at(session, user.id))
    responsible = await has_current_responsibility(session, user.id)
    created = _as_utc(user.created_at) or now
    account_age = max(0, (now - created).days)

    if responsible:
        return STATE_ACTIVE, latest
    if latest is not None:
        inactivity_days = max(0, (now - latest).days)
        if inactivity_days <= thresholds["active_days"]:
            return STATE_ACTIVE, latest
    else:
        # New people receive the full adaptation grace. They must never become
        # INACTIVE solely because they have not yet completed their first action.
        if account_age <= thresholds["adaptation_days"]:
            return STATE_ADAPTATION, None
        inactivity_days = account_age

    if inactivity_days <= thresholds["cooling_end_days"]:
        return STATE_COOLING, latest
    if inactivity_days <= thresholds["inactive_end_days"]:
        return STATE_INACTIVE, latest
    if inactivity_days <= thresholds["dormant_end_days"]:
        return STATE_DORMANT, latest
    return STATE_ARCHIVE_CANDIDATE, latest


async def refresh_user_lifecycle(
    session: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> ParticipationLifecycle:
    now = _as_utc(now) or _now()
    row = await get_or_create_lifecycle(session, user)

    # A finite pause ends deterministically. Nothing is deleted/archived.
    if row.participation_mode == MODE_PAUSED and row.pause_until and row.pause_until < now.date():
        row.participation_mode = row.mode_before_pause or MODE_ACTIVE
        row.mode_before_pause = None
        row.pause_until = None
        row.mode_changed_at = now
        row.returned_at = now

    state, latest = await evaluate_activity_state(session, user, now=now)
    row.last_meaningful_at = latest
    if row.activity_state != state:
        row.activity_state = state
        row.state_since = now
    await session.flush()
    return row


def snapshot(row: ParticipationLifecycle) -> LifecycleSnapshot:
    return LifecycleSnapshot(
        participation_mode=row.participation_mode,
        activity_state=row.activity_state,
        last_meaningful_at=row.last_meaningful_at,
        pause_until=row.pause_until,
        onboarding_version=row.onboarding_version,
        onboarding_completed_at=row.onboarding_completed_at,
    )


async def complete_onboarding(
    session: AsyncSession,
    user: User,
    *,
    version: int = CURRENT_ONBOARDING_VERSION,
) -> ParticipationLifecycle:
    row = await get_or_create_lifecycle(session, user)
    row.onboarding_version = max(row.onboarding_version, version)
    row.onboarding_completed_at = _now()
    await session.flush()
    return row


async def set_participation_mode(
    session: AsyncSession,
    user: User,
    mode: str,
    *,
    pause_until: date | None = None,
) -> ParticipationLifecycle:
    mode = str(mode).upper()
    if mode not in PARTICIPATION_MODES:
        raise ValueError("invalid_participation_mode")
    now = _now()
    row = await get_or_create_lifecycle(session, user)

    if mode == MODE_PAUSED:
        if pause_until is None or pause_until <= now.date():
            raise ValueError("pause_until_must_be_future")
        if row.participation_mode != MODE_PAUSED:
            row.mode_before_pause = row.participation_mode if row.participation_mode in {MODE_ACTIVE, MODE_LIGHT} else MODE_ACTIVE
        row.pause_until = pause_until
    else:
        row.pause_until = None
        row.mode_before_pause = None

    row.participation_mode = mode
    row.mode_changed_at = now
    if mode in {MODE_ACTIVE, MODE_LIGHT}:
        row.returned_at = now
    await stop_or_pause_reactivation_for_mode(session, user.id, mode, now=now)
    await session.flush()
    return row


async def record_meaningful_activity(
    session: AsyncSession,
    user_id: int,
    *,
    occurred_at: datetime | None = None,
) -> None:
    now = _as_utc(occurred_at) or _now()
    user = await session.get(User, user_id)
    if user is None:
        return
    row = await get_or_create_lifecycle(session, user)
    previous_state = row.activity_state
    row.last_meaningful_at = now
    row.activity_state = STATE_ACTIVE
    row.state_since = now
    if previous_state != STATE_ACTIVE:
        row.returned_at = now
    await complete_active_reactivation(session, user_id, outcome="meaningful_action", now=now)
    await session.flush()


async def _active_campaign(session: AsyncSession, user_id: int) -> ReactivationCampaign | None:
    return await session.scalar(
        select(ReactivationCampaign)
        .where(
            ReactivationCampaign.user_id == user_id,
            ReactivationCampaign.status == "active",
        )
        .order_by(ReactivationCampaign.started_at.desc())
        .limit(1)
    )


async def ensure_reactivation_campaign(
    session: AsyncSession,
    user: User,
    lifecycle: ParticipationLifecycle,
    *,
    now: datetime | None = None,
) -> ReactivationCampaign | None:
    now = _as_utc(now) or _now()
    if lifecycle.participation_mode not in {MODE_ACTIVE, MODE_LIGHT}:
        return None
    if lifecycle.activity_state not in {
        STATE_COOLING,
        STATE_INACTIVE,
        STATE_DORMANT,
        STATE_ARCHIVE_CANDIDATE,
    }:
        return None
    existing = await _active_campaign(session, user.id)
    if existing is not None:
        return existing

    state_anchor = lifecycle.state_since or now
    key = f"reactivation:{user.id}:{state_anchor.date().isoformat()}"
    existing_by_key = await session.scalar(
        select(ReactivationCampaign).where(ReactivationCampaign.campaign_key == key)
    )
    if existing_by_key is not None:
        return existing_by_key if existing_by_key.status == "active" else None

    campaign = ReactivationCampaign(
        user_id=user.id,
        campaign_key=key,
        status="active",
        current_attempt=0,
        started_at=now,
        next_attempt_at=now,
    )
    session.add(campaign)
    await session.flush()
    return campaign


async def complete_active_reactivation(
    session: AsyncSession,
    user_id: int,
    *,
    outcome: str,
    now: datetime | None = None,
) -> None:
    now = _as_utc(now) or _now()
    campaign = await _active_campaign(session, user_id)
    if campaign is None:
        return
    campaign.status = "completed"
    campaign.completed_at = now
    campaign.next_attempt_at = None
    campaign.outcome = outcome


async def stop_or_pause_reactivation_for_mode(
    session: AsyncSession,
    user_id: int,
    mode: str,
    *,
    now: datetime | None = None,
) -> None:
    now = _as_utc(now) or _now()
    campaign = await _active_campaign(session, user_id)
    if campaign is None:
        return
    if mode == MODE_PAUSED:
        campaign.status = "paused"
        campaign.outcome = "paused"
    elif mode == MODE_OBSERVER:
        campaign.status = "completed"
        campaign.outcome = "observer"
    elif mode == MODE_EXITED:
        campaign.status = "completed"
        campaign.outcome = "exited"
    elif mode in {MODE_ACTIVE, MODE_LIGHT}:
        return
    campaign.completed_at = now
    campaign.next_attempt_at = None


async def save_inactivity_reason(
    session: AsyncSession,
    user: User,
    reason: str,
) -> ReactivationCampaign | None:
    campaign = await _active_campaign(session, user.id)
    if campaign is None:
        return None
    campaign.inactivity_reason = (reason or "").strip()[:2000] or None
    await session.flush()
    return campaign


def _in_quiet_hours(now: datetime, timezone_name: str) -> bool:
    local = now.astimezone(ZoneInfo(timezone_name))
    return local.hour >= QUIET_START_HOUR or local.hour < QUIET_END_HOUR


def _next_after_quiet(now: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    local = now.astimezone(tz)
    target_day = local.date() + (timedelta(days=1) if local.hour >= QUIET_START_HOUR else timedelta())
    target = datetime.combine(target_day, time(QUIET_END_HOUR, 0), tzinfo=tz)
    return target.astimezone(timezone.utc)


def _attempt_copy(attempt_no: int, first_name: str) -> tuple[str, str, str]:
    if attempt_no == 1:
        return (
            "Мы давно не виделись",
            "В ЭРА появились новые события, проекты и задачи. Можно вернуться с одного небольшого действия — без длинных обязательств.",
            "Открыть ЭРА",
        )
    if attempt_no == 2:
        return (
            f"{first_name}, найдём удобный формат",
            "Не обязательно возвращаться сразу на полную нагрузку. Можно выбрать одно событие, короткую задачу или лёгкий режим участия.",
            "Посмотреть варианты",
        )
    if attempt_no == 3:
        return (
            "Что сейчас мешает включиться?",
            "Если причина в времени, нагрузке, формате или другом — это можно отметить в профиле. Нам важна причина, а не формальная активность.",
            "Ответить",
        )
    if attempt_no == 4:
        return (
            "Выберите свой режим участия",
            "Активный, лёгкий, пауза или наблюдатель — режим можно выбрать самому. Пауза останавливает регулярные напоминания и ничего не удаляет.",
            "Выбрать режим",
        )
    return (
        "Финальная сверка",
        "Хотим понять только одно: Вы хотите оставаться в ЭРА сейчас? Если нет времени — можно поставить паузу или перейти в наблюдатели. Автоматического удаления не будет.",
        "Открыть профиль",
    )


async def sync_lifecycle_state(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    now = _as_utc(now) or _now()
    users = list(
        (
            await session.scalars(
                select(User).where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                )
            )
        ).all()
    )
    changed = 0
    for user in users:
        row = await get_or_create_lifecycle(session, user)
        before = (row.activity_state, row.participation_mode, row.pause_until)
        await refresh_user_lifecycle(session, user, now=now)
        row = await get_or_create_lifecycle(session, user)
        await ensure_reactivation_campaign(session, user, row, now=now)
        after = (row.activity_state, row.participation_mode, row.pause_until)
        changed += int(before != after)
    await session.flush()
    return changed


async def process_reactivation_deliveries(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    now = _as_utc(now) or _now()
    campaigns = list(
        (
            await session.scalars(
                select(ReactivationCampaign).where(
                    ReactivationCampaign.status == "active",
                    ReactivationCampaign.next_attempt_at.is_not(None),
                    ReactivationCampaign.next_attempt_at <= now,
                    ReactivationCampaign.current_attempt < MAX_REACTIVATION_ATTEMPTS,
                )
            )
        ).all()
    )
    sent_count = 0
    for campaign in campaigns:
        user = await session.get(User, campaign.user_id)
        if user is None or user.is_blocked or user.is_archived or user.application_status != ApplicationStatus.APPROVED:
            campaign.status = "completed"
            campaign.completed_at = now
            campaign.outcome = "unavailable"
            campaign.next_attempt_at = None
            continue
        lifecycle = await get_or_create_lifecycle(session, user)
        if lifecycle.participation_mode not in {MODE_ACTIVE, MODE_LIGHT}:
            await stop_or_pause_reactivation_for_mode(
                session, user.id, lifecycle.participation_mode, now=now
            )
            continue
        if lifecycle.activity_state in {STATE_ACTIVE, STATE_ADAPTATION}:
            await complete_active_reactivation(session, user.id, outcome="returned", now=now)
            continue
        if _in_quiet_hours(now, settings.timezone):
            campaign.next_attempt_at = _next_after_quiet(now, settings.timezone)
            continue

        attempt_no = campaign.current_attempt + 1
        delivery_key = f"reactivation:{campaign.id}:attempt:{attempt_no}"
        delivery = await session.scalar(
            select(ReactivationDelivery).where(ReactivationDelivery.idempotency_key == delivery_key)
        )
        if delivery is None:
            delivery = ReactivationDelivery(
                campaign_id=campaign.id,
                attempt_no=attempt_no,
                idempotency_key=delivery_key,
                status="pending",
                scheduled_at=campaign.next_attempt_at or now,
            )
            session.add(delivery)
            await session.flush()
        if delivery.status == "sent":
            campaign.current_attempt = max(campaign.current_attempt, attempt_no)
        else:
            title, body, action_label = _attempt_copy(attempt_no, user.first_name)
            profile_url = miniapp_profile_url(settings.effective_miniapp_url)
            action = PrimaryAction(label=action_label, web_app_url=profile_url) if profile_url else None
            delivery.attempt_count += 1
            delivery.last_attempt_at = now
            delivered = await send_bot_notification(
                bot,
                user.telegram_id,
                emoji="🔥",
                title=title,
                body=body,
                action=action,
            )
            if not delivered:
                delivery.status = "failed"
                delivery.error_code = "telegram_delivery_failed"
                # Do not hammer a blocked/unreachable user. The next stage is
                # still scheduled normally and the campaign remains non-fatal.
            else:
                delivery.status = "sent"
                delivery.sent_at = now
                delivery.error_code = None
                sent_count += 1
            campaign.current_attempt = attempt_no

        if campaign.current_attempt >= MAX_REACTIVATION_ATTEMPTS:
            campaign.status = "completed"
            campaign.completed_at = now
            campaign.outcome = "no_response"
            campaign.next_attempt_at = None
        else:
            # Delay is relative to the campaign start, not to retries, so a
            # restart cannot gradually drift a campaign forever.
            next_index = campaign.current_attempt
            campaign.next_attempt_at = campaign.started_at + timedelta(
                days=REACTIVATION_DELAYS_DAYS[next_index]
            )
    await session.flush()
    return sent_count


async def run_reactivation_cycle(bot: Bot, settings: Settings, session_factory) -> None:
    async with session_factory() as session:
        now = _now()
        await sync_lifecycle_state(session, now=now)
        await process_reactivation_deliveries(bot, settings, session, now=now)
        await session.commit()
