from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.leadership_models import LeaderChatMembership, WeeklyPulseCycle, WeeklyPulseSchedule
from app.database.models import User

ACTIVE_TELEGRAM_STATUSES = {"creator", "administrator", "member"}


class WeeklyPulseConfigurationError(ValueError):
    pass


def validate_schedule_values(
    *,
    open_weekday: int,
    open_time: time,
    deadline_hours: int,
    first_reminder_hours: int,
    final_reminder_hours: int,
    report_weekday: int,
    timezone_name: str,
) -> None:
    if open_weekday not in range(7) or report_weekday not in range(7):
        raise WeeklyPulseConfigurationError("weekday_must_be_0_to_6")
    if open_time.tzinfo is not None:
        raise WeeklyPulseConfigurationError("open_time_must_be_local_time")
    if not 1 <= deadline_hours <= 168:
        raise WeeklyPulseConfigurationError("deadline_hours_must_be_1_to_168")
    if not 1 <= final_reminder_hours < first_reminder_hours < deadline_hours:
        raise WeeklyPulseConfigurationError("reminders_must_be_ordered_before_deadline")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise WeeklyPulseConfigurationError("invalid_timezone") from exc


async def get_schedule(session: AsyncSession) -> WeeklyPulseSchedule:
    schedule = await session.get(WeeklyPulseSchedule, 1)
    if schedule is None:
        schedule = WeeklyPulseSchedule(id=1)
        session.add(schedule)
        await session.flush()
    return schedule


async def update_schedule(
    session: AsyncSession,
    *,
    enabled: bool,
    open_weekday: int,
    open_time: time,
    deadline_hours: int,
    first_reminder_hours: int,
    final_reminder_hours: int,
    report_weekday: int,
    timezone_name: str,
) -> WeeklyPulseSchedule:
    validate_schedule_values(
        open_weekday=open_weekday,
        open_time=open_time,
        deadline_hours=deadline_hours,
        first_reminder_hours=first_reminder_hours,
        final_reminder_hours=final_reminder_hours,
        report_weekday=report_weekday,
        timezone_name=timezone_name,
    )
    schedule = await get_schedule(session)
    schedule.enabled = enabled
    schedule.open_weekday = open_weekday
    schedule.open_time = open_time
    schedule.deadline_hours = deadline_hours
    schedule.first_reminder_hours = first_reminder_hours
    schedule.final_reminder_hours = final_reminder_hours
    schedule.report_weekday = report_weekday
    schedule.timezone = timezone_name
    await session.flush()
    return schedule


async def upsert_leader_membership(
    session: AsyncSession,
    *,
    leader_chat_id: int,
    telegram_user_id: int,
    membership_status: str,
    username: str | None = None,
    display_name: str = "",
    is_member: bool | None = None,
    now: datetime | None = None,
) -> LeaderChatMembership:
    """Track membership without changing the person's ERA role or status."""
    now = now or datetime.now(timezone.utc)
    active = membership_status in ACTIVE_TELEGRAM_STATUSES or (
        membership_status == "restricted" and is_member is True
    )
    row = await session.scalar(
        select(LeaderChatMembership).where(
            LeaderChatMembership.leader_chat_id == leader_chat_id,
            LeaderChatMembership.telegram_user_id == telegram_user_id,
        )
    )
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user_id))
    if row is None:
        row = LeaderChatMembership(
            leader_chat_id=leader_chat_id,
            telegram_user_id=telegram_user_id,
            joined_at=now if active else None,
        )
        session.add(row)
    elif active and row.joined_at is None:
        row.joined_at = now
    row.user_id = user.id if user is not None else None
    row.username = username
    row.display_name = display_name.strip()[:255]
    row.membership_status = membership_status[:16]
    row.last_verified_at = now
    row.is_weekly_pulse_eligible = active
    row.left_at = None if active else now
    await session.flush()
    return row


async def create_or_get_cycle(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    leader_chat_id: int,
) -> WeeklyPulseCycle:
    if date_to < date_from:
        raise WeeklyPulseConfigurationError("cycle_end_before_start")
    existing = await session.scalar(
        select(WeeklyPulseCycle).where(
            WeeklyPulseCycle.date_from == date_from,
            WeeklyPulseCycle.date_to == date_to,
        )
    )
    if existing is not None:
        return existing
    schedule = await get_schedule(session)
    if not schedule.enabled:
        raise WeeklyPulseConfigurationError("weekly_pulse_disabled")
    tz = ZoneInfo(schedule.timezone)
    open_day = date_from + timedelta(days=(schedule.open_weekday - date_from.weekday()) % 7)
    opens_at = datetime.combine(open_day, schedule.open_time, tzinfo=tz)
    deadline_at = opens_at + timedelta(hours=schedule.deadline_hours)
    report_at = datetime.combine(date_to, time(23, 59), tzinfo=tz)
    cycle = WeeklyPulseCycle(
        week_number=date_from.isocalendar().week,
        date_from=date_from,
        date_to=date_to,
        opens_at=opens_at,
        deadline_at=deadline_at,
        closes_at=max(deadline_at, report_at),
        status="open" if opens_at <= datetime.now(tz) else "scheduled",
        leader_chat_id=leader_chat_id,
    )
    session.add(cycle)
    await session.flush()
    return cycle


async def eligible_members(session: AsyncSession, *, leader_chat_id: int) -> list[LeaderChatMembership]:
    rows = await session.scalars(
        select(LeaderChatMembership)
        .where(
            LeaderChatMembership.leader_chat_id == leader_chat_id,
            LeaderChatMembership.is_weekly_pulse_eligible.is_(True),
        )
        .order_by(LeaderChatMembership.display_name, LeaderChatMembership.telegram_user_id)
    )
    return list(rows.all())
