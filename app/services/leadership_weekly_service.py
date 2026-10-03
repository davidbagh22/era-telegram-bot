from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.leadership_models import (
    LeaderChatMembership,
    LeadershipFeedback,
    LeadershipReportPulse,
)
from app.database.models import (
    Event,
    LeadershipAttentionItem,
    LeadershipGoal,
    LeadershipReport,
    Office,
    Project,
    Task,
    User,
    UserDepartment,
    UserDirection,
    UserOffice,
)
from app.services.audit_service import audit
from app.services.bot_notification_service import PrimaryAction, send_bot_notification
from app.services.leadership_permission_service import is_assignment_active
from app.services import leadership_report_service
from app.services.weekly_pulse_cycle_service import (
    create_or_get_cycle,
    eligible_members,
    get_schedule,
    upsert_leader_membership,
)
from app.utils.constants import (
    ApplicationStatus,
    AttentionItemSeverity,
    AttentionItemStatus,
    LeadershipGoalStatus,
    LeadershipReportStatus,
    Role,
    TaskStatus,
)

MISSED_REPORT_TYPE = "leader_missed_weekly_report"
DIVERGENCE_TYPE = "leader_objective_subjective_divergence"


def _local_datetime(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


@dataclass(frozen=True, slots=True)
class WeeklyReportView:
    report: LeadershipReport
    pulse: LeadershipReportPulse


def week_bounds(day: date | None = None) -> tuple[date, date]:
    day = day or date.today()
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _assignment_scope(assignment: UserOffice | None, office: Office | None) -> tuple[str, int | None]:
    if assignment is not None and assignment.scope_type:
        return assignment.scope_type, assignment.scope_id
    if office is not None:
        if office.department_id is not None:
            return "department", office.department_id
        if office.direction_id is not None:
            return "direction", office.direction_id
        return office.scope_type or "global", office.scope_id
    return "global", None


async def _active_assignment_for_owner(
    session: AsyncSession,
    owner_id: int,
    assignment_id: int | None = None,
) -> tuple[UserOffice | None, Office | None]:
    query = (
        select(UserOffice, Office)
        .join(Office, Office.id == UserOffice.office_id)
        .where(
            UserOffice.user_id == owner_id,
            UserOffice.is_active.is_(True),
            Office.is_active.is_(True),
        )
    )
    if assignment_id is not None:
        query = query.where(UserOffice.id == assignment_id)
    rows = (await session.execute(query.order_by(UserOffice.id))).all()
    for assignment, office in rows:
        if is_assignment_active(assignment):
            return assignment, office
    return None, None


async def _scope_user_ids(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: int | None,
    owner_id: int,
) -> set[int]:
    base = [
        User.application_status == ApplicationStatus.APPROVED,
        User.is_blocked.is_(False),
        User.is_archived.is_(False),
    ]
    if scope_type == "department" and scope_id is not None:
        values = await session.scalars(
            select(User.id)
            .join(UserDepartment, UserDepartment.user_id == User.id)
            .where(*base, UserDepartment.department_id == scope_id)
        )
        return set(values.all())
    if scope_type == "direction" and scope_id is not None:
        values = await session.scalars(
            select(User.id)
            .join(UserDirection, UserDirection.user_id == User.id)
            .where(*base, UserDirection.direction_id == scope_id)
        )
        return set(values.all())
    if scope_type == "global":
        values = await session.scalars(select(User.id).where(*base))
        return set(values.all())
    # Project/event/office-specific responsibilities do not have a universal
    # membership table. Keep the snapshot conservative instead of leaking
    # organization-wide data into a narrow scope.
    return {owner_id}


async def build_system_snapshot(
    session: AsyncSession,
    *,
    owner_id: int,
    scope_type: str,
    scope_id: int | None,
    period_start: date,
    period_end: date,
) -> dict:
    """Build immutable objective facts for one leader/week and one scope."""
    user_ids = await _scope_user_ids(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        owner_id=owner_id,
    )
    ids = user_ids or {owner_id}
    start_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    task_filter = Task.assignee_id.in_(ids)
    tasks_total = int(
        await session.scalar(select(func.count()).select_from(Task).where(task_filter)) or 0
    )
    tasks_completed = int(
        await session.scalar(
            select(func.count()).select_from(Task).where(
                task_filter,
                Task.status == TaskStatus.COMPLETED,
            )
        )
        or 0
    )
    tasks_overdue = int(
        await session.scalar(
            select(func.count()).select_from(Task).where(
                task_filter,
                Task.status != TaskStatus.COMPLETED,
                Task.deadline < now,
            )
        )
        or 0
    )
    tasks_period_completed = int(
        await session.scalar(
            select(func.count()).select_from(Task).where(
                task_filter,
                Task.status == TaskStatus.COMPLETED,
                Task.updated_at >= start_dt,
                Task.updated_at < end_dt,
            )
        )
        or 0
    )

    project_conditions = []
    event_conditions = []
    if scope_type == "department" and scope_id is not None:
        project_conditions.append(Project.department_id == scope_id)
        event_conditions.append(Event.department_id == scope_id)
    elif scope_type == "direction" and scope_id is not None:
        project_conditions.append(Project.direction_id == scope_id)
        event_conditions.append(Event.direction_id == scope_id)
    elif scope_type == "global":
        pass
    else:
        project_conditions.append(Project.author_id == owner_id)
        event_conditions.append(Event.created_by == owner_id)

    projects_active = int(
        await session.scalar(
            select(func.count()).select_from(Project).where(
                *project_conditions,
                Project.status.notin_(["rejected", "completed", "cancelled", "archived"]),
            )
        )
        or 0
    )
    events_period = int(
        await session.scalar(
            select(func.count()).select_from(Event).where(
                *event_conditions,
                Event.event_date >= period_start,
                Event.event_date <= period_end,
            )
        )
        or 0
    )
    goals_active = int(
        await session.scalar(
            select(func.count()).select_from(LeadershipGoal).where(
                LeadershipGoal.owner_id == owner_id,
                LeadershipGoal.status == LeadershipGoalStatus.ACTIVE,
                LeadershipGoal.period_end >= period_start,
            )
        )
        or 0
    )

    overdue_rate = round(tasks_overdue / tasks_total, 4) if tasks_total else 0.0
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "scope_type": scope_type,
        "scope_id": scope_id,
        "team_size": len(user_ids),
        "tasks_total": tasks_total,
        "tasks_completed": tasks_completed,
        "tasks_completed_this_week": tasks_period_completed,
        "tasks_overdue": tasks_overdue,
        "tasks_overdue_rate": overdue_rate,
        "projects_active": projects_active,
        "events_this_week": events_period,
        "active_goals": goals_active,
    }


async def ensure_weekly_report(
    session: AsyncSession,
    *,
    owner_id: int,
    period_start: date | None = None,
    office_assignment_id: int | None = None,
) -> WeeklyReportView:
    period_start, period_end = (
        week_bounds(period_start) if period_start else week_bounds()
    )
    report = await leadership_report_service.current_report(
        session, owner_id=owner_id, period_start=period_start
    )

    assignment, office = await _active_assignment_for_owner(
        session, owner_id, office_assignment_id
    )
    if office_assignment_id is not None and assignment is None:
        raise ValueError("office_assignment_not_owned_or_inactive")
    scope_type, scope_id = _assignment_scope(assignment, office)

    if report is None:
        report = LeadershipReport(
            owner_id=owner_id,
            office_assignment_id=assignment.id if assignment else None,
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
        )
        session.add(report)
        await session.flush()
    else:
        # Existing report owns its original scope. A later request cannot move
        # historical system facts to another department/direction.
        scope_type, scope_id = report.scope_type, report.scope_id

    pulse = await session.scalar(
        select(LeadershipReportPulse).where(
            LeadershipReportPulse.report_id == report.id
        )
    )
    if pulse is None:
        pulse = LeadershipReportPulse(
            report_id=report.id,
            system_snapshot=await build_system_snapshot(
                session,
                owner_id=owner_id,
                scope_type=scope_type,
                scope_id=scope_id,
                period_start=period_start,
                period_end=period_end,
            ),
        )
        session.add(pulse)
        await session.flush()
    return WeeklyReportView(report=report, pulse=pulse)


def _validate_score(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    if value < 1 or value > 5:
        raise ValueError(f"{field}_must_be_1_to_5")
    return int(value)


def _objective_risk(snapshot: dict) -> bool:
    return bool(
        int(snapshot.get("tasks_overdue") or 0) >= 2
        or float(snapshot.get("tasks_overdue_rate") or 0) >= 0.37
    )


def _subjective_positive(
    *, status: str, pace_score: int | None, clarity_score: int | None, load_score: int | None
) -> bool:
    scores_available = pace_score is not None and clarity_score is not None and load_score is not None
    return bool(
        status == LeadershipReportStatus.ON_TRACK
        and scores_available
        and pace_score >= 4
        and clarity_score >= 4
        and load_score <= 3
    )


async def _period_attention_exists(
    session: AsyncSession,
    *,
    type_: str,
    owner_id: int,
    period_start: date,
) -> bool:
    start_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=7)
    return bool(
        await session.scalar(
            select(func.count())
            .select_from(LeadershipAttentionItem)
            .where(
                LeadershipAttentionItem.type == type_,
                LeadershipAttentionItem.owner_id == owner_id,
                LeadershipAttentionItem.created_at >= start_dt,
                LeadershipAttentionItem.created_at < end_dt,
            )
        )
    )


async def _create_divergence_signal(
    session: AsyncSession,
    *,
    report: LeadershipReport,
    pulse: LeadershipReportPulse,
) -> LeadershipAttentionItem | None:
    if not _objective_risk(pulse.system_snapshot or {}):
        return None
    if not _subjective_positive(
        status=report.status,
        pace_score=pulse.pace_score,
        clarity_score=pulse.clarity_score,
        load_score=pulse.load_score,
    ):
        return None
    if await _period_attention_exists(
        session,
        type_=DIVERGENCE_TYPE,
        owner_id=report.owner_id,
        period_start=report.period_start,
    ):
        return None
    item = LeadershipAttentionItem(
        type=DIVERGENCE_TYPE,
        severity=AttentionItemSeverity.MEDIUM,
        scope_type=report.scope_type,
        scope_id=report.scope_id,
        owner_id=report.owner_id,
        status=AttentionItemStatus.OPEN,
    )
    session.add(item)
    await session.flush()
    return item


async def submit_weekly_pulse(
    session: AsyncSession,
    *,
    owner_id: int,
    period_start: date,
    status: str,
    office_assignment_id: int | None = None,
    main_result: str = "",
    blocker_type: str | None = None,
    blocker_note: str = "",
    next_priorities: list[str] | None = None,
    needs_help: bool = False,
    pace_score: int | None = None,
    clarity_score: int | None = None,
    load_score: int | None = None,
    attention_text: str = "",
    bot: Bot | None = None,
    settings: Settings | None = None,
) -> WeeklyReportView:
    view = await ensure_weekly_report(
        session,
        owner_id=owner_id,
        period_start=period_start,
        office_assignment_id=office_assignment_id,
    )
    result = await leadership_report_service.submit_quick_report(
        session,
        owner_id=owner_id,
        period_start=view.report.period_start,
        period_end=view.report.period_end,
        status=status,
        scope_type=view.report.scope_type,
        scope_id=view.report.scope_id,
        office_assignment_id=view.report.office_assignment_id,
        main_result=main_result,
        blocker_type=blocker_type,
        blocker_note=blocker_note,
        next_priorities=next_priorities,
        needs_help=needs_help,
        bot=bot,
        settings=settings,
    )
    pulse = view.pulse
    pulse.pace_score = _validate_score(pace_score, "pace_score")
    pulse.clarity_score = _validate_score(clarity_score, "clarity_score")
    pulse.load_score = _validate_score(load_score, "load_score")
    pulse.attention_text = attention_text.strip()[:1000] or None
    await session.flush()
    await _create_divergence_signal(session, report=result.report, pulse=pulse)
    await audit(
        session,
        actor_id=owner_id,
        action="leadership_weekly_pulse.submitted",
        entity_type="leadership_report",
        entity_id=result.report.id,
        new_value={
            "pace_score": pulse.pace_score,
            "clarity_score": pulse.clarity_score,
            "load_score": pulse.load_score,
        },
    )
    return WeeklyReportView(report=result.report, pulse=pulse)


async def can_review_report(
    session: AsyncSession,
    *,
    reviewer: User,
    report: LeadershipReport,
) -> bool:
    if reviewer.role == Role.ADMIN:
        return True
    assignment = (
        await session.get(UserOffice, report.office_assignment_id)
        if report.office_assignment_id
        else None
    )
    target = await leadership_report_service.resolve_escalation_target(session, assignment)
    return bool(target and target.id == reviewer.id)


async def add_feedback(
    session: AsyncSession,
    *,
    report: LeadershipReport,
    reviewer: User,
    status: str,
    comment: str,
) -> LeadershipFeedback:
    if not await can_review_report(session, reviewer=reviewer, report=report):
        raise PermissionError("feedback_scope_forbidden")
    feedback = LeadershipFeedback(
        report_id=report.id,
        reviewer_id=reviewer.id,
        status=status,
        comment=comment.strip()[:2000] or None,
    )
    session.add(feedback)
    await session.flush()
    await audit(
        session,
        actor_id=reviewer.id,
        action="leadership_report.feedback_added",
        entity_type="leadership_report",
        entity_id=report.id,
        new_value={"status": status},
    )
    return feedback


async def list_feedback(
    session: AsyncSession, *, report_id: int
) -> list[LeadershipFeedback]:
    return list(
        (
            await session.scalars(
                select(LeadershipFeedback)
                .where(LeadershipFeedback.report_id == report_id)
                .order_by(LeadershipFeedback.created_at.asc(), LeadershipFeedback.id.asc())
            )
        ).all()
    )


async def _active_leader_assignments(session: AsyncSession) -> list[tuple[UserOffice, Office, User]]:
    rows = (
        await session.execute(
            select(UserOffice, Office, User)
            .join(Office, Office.id == UserOffice.office_id)
            .join(User, User.id == UserOffice.user_id)
            .where(
                UserOffice.is_active.is_(True),
                Office.is_active.is_(True),
                User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
            )
            .order_by(UserOffice.id)
        )
    ).all()
    return [
        (assignment, office, user)
        for assignment, office, user in rows
        if office.permission_template and is_assignment_active(assignment)
    ]


async def run_missed_report_signals(
    session: AsyncSession,
    *,
    period_start: date | None = None,
    eligible_owner_ids: set[int] | None = None,
) -> list[LeadershipAttentionItem]:
    period_start, _ = week_bounds(period_start)
    created: list[LeadershipAttentionItem] = []
    seen_users: set[int] = set()
    for assignment, office, user in await _active_leader_assignments(session):
        if eligible_owner_ids is not None and user.id not in eligible_owner_ids:
            continue
        if user.id in seen_users:
            continue
        seen_users.add(user.id)
        report = await leadership_report_service.current_report(
            session, owner_id=user.id, period_start=period_start
        )
        if report is not None and report.submitted_at is not None:
            continue
        if await _period_attention_exists(
            session,
            type_=MISSED_REPORT_TYPE,
            owner_id=user.id,
            period_start=period_start,
        ):
            continue
        scope_type, scope_id = _assignment_scope(assignment, office)
        responsible = await leadership_report_service.resolve_escalation_target(
            session, assignment
        )
        item = LeadershipAttentionItem(
            type=MISSED_REPORT_TYPE,
            severity=AttentionItemSeverity.MEDIUM,
            scope_type=scope_type,
            scope_id=scope_id,
            owner_id=user.id,
            responsible_id=responsible.id if responsible else None,
            status=AttentionItemStatus.OPEN,
        )
        session.add(item)
        await session.flush()
        created.append(item)
    return created


async def open_weekly_pulses_job(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    async with session_factory() as session:
        schedule = await get_schedule(session)
        if not schedule.enabled or not settings.leaders_chat_id:
            return
        local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
        period_start, period_end = week_bounds(local_today)
        cycle = await create_or_get_cycle(
            session,
            date_from=period_start,
            date_to=period_end,
            leader_chat_id=settings.leaders_chat_id,
        )
        tz = ZoneInfo(schedule.timezone)
        now = datetime.now(tz)
        cycle_open = _local_datetime(cycle.opens_at, tz)
        cycle_deadline = _local_datetime(cycle.deadline_at, tz)
        if now < cycle_open:
            await session.commit()
            return
        if now >= cycle_deadline:
            if cycle.status in {"scheduled", "open"}:
                cycle.status = "processing"
            await session.commit()
            return

        assignments = await _active_leader_assignments(session)
        # Telegram cannot enumerate existing members. Backfill known leaders
        # with getChatMember once; subsequent join/leave changes arrive through
        # the bot's chat_member updates.
        for _assignment, _office, user in assignments:
            membership = await session.scalar(
                select(LeaderChatMembership).where(
                    LeaderChatMembership.leader_chat_id == settings.leaders_chat_id,
                    LeaderChatMembership.telegram_user_id == user.telegram_id,
                )
            )
            if membership is not None:
                continue
            try:
                chat_member = await bot.get_chat_member(
                    settings.leaders_chat_id, user.telegram_id
                )
            except TelegramAPIError:
                continue
            await upsert_leader_membership(
                session,
                leader_chat_id=settings.leaders_chat_id,
                telegram_user_id=user.telegram_id,
                membership_status=chat_member.status,
                username=user.username,
                display_name=f"{user.first_name} {user.last_name or ''}".strip(),
                is_member=getattr(chat_member, "is_member", None),
            )

        cycle.status = "open"
        roster = await eligible_members(session, leader_chat_id=settings.leaders_chat_id)
        eligible_user_ids = {member.user_id for member in roster if member.user_id is not None}
        cycle.eligible_count = len(roster)

        if cycle.announcement_message_id is None:
            buttons = []
            try:
                bot_info = await bot.get_me()
                if bot_info.username:
                    buttons.append(
                        InlineKeyboardButton(
                            text="Подключить Pulse",
                            url=f"https://t.me/{bot_info.username}?start=pulse_connect",
                        )
                    )
            except TelegramAPIError:
                pass
            try:
                announcement = await bot.send_message(
                    chat_id=settings.leaders_chat_id,
                    text=(
                        f"📊 <b>Открылся Weekly Pulse · неделя {cycle.week_number}</b>\n\n"
                        f"Ответили: {cycle.submitted_count} / {cycle.eligible_count}\n"
                        f"Заполните короткий отчёт до "
                        f"{cycle_deadline:%d.%m %H:%M}. "
                        "Если аккаунт ещё не связан с ЭРА, нажмите «Подключить Pulse»."
                    ),
                    parse_mode="HTML",
                    reply_markup=(
                        InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
                    ),
                )
                cycle.announcement_message_id = announcement.message_id
            except TelegramAPIError:
                pass

        seen_users: set[int] = set()
        for assignment, _office, user in assignments:
            if user.id not in eligible_user_ids:
                continue
            if user.id in seen_users:
                continue
            seen_users.add(user.id)
            view = await ensure_weekly_report(
                session,
                owner_id=user.id,
                period_start=period_start,
                office_assignment_id=assignment.id,
            )
            view.report.pulse_cycle_id = cycle.id
            if view.report.submitted_at is not None:
                continue
            action = (
                PrimaryAction(label="Открыть ЭРА", web_app_url=settings.effective_miniapp_url)
                if settings.effective_miniapp_url
                else None
            )
            await send_bot_notification(
                bot,
                user.telegram_id,
                emoji="📊",
                title="Weekly Pulse открыт",
                body=(
                    "Система уже собрала факты по вашей зоне. Добавьте короткий итог недели, "
                    "оцените темп, ясность и нагрузку и зафиксируйте следующий приоритет."
                ),
                action=action,
                settings=settings,
                delivery_key=f"leadership-pulse-open:{period_start}:{user.id}",
                notification_type="leadership_weekly_pulse",
            )
        submitted = await session.scalar(
            select(func.count(func.distinct(LeadershipReport.owner_id))).where(
                LeadershipReport.pulse_cycle_id == cycle.id,
                LeadershipReport.submitted_at.is_not(None),
            )
        )
        cycle.submitted_count = int(submitted or 0)
        if cycle.announcement_message_id is not None:
            try:
                await bot.edit_message_text(
                    chat_id=settings.leaders_chat_id,
                    message_id=cycle.announcement_message_id,
                    text=(
                        f"📊 <b>Пульс ЭРА · неделя {cycle.week_number}</b>\n\n"
                        f"Ответили: {cycle.submitted_count} / {cycle.eligible_count}\n"
                        f"Срок: {cycle_deadline:%d.%m %H:%M}"
                    ),
                    parse_mode="HTML",
                )
            except TelegramAPIError:
                pass
        await session.commit()


async def check_weekly_pulses_job(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    async with session_factory() as session:
        schedule = await get_schedule(session)
        if not schedule.enabled or not settings.leaders_chat_id:
            return
        local_today = datetime.now(ZoneInfo(schedule.timezone)).date()
        period_start, period_end = week_bounds(local_today)
        cycle = await create_or_get_cycle(
            session,
            date_from=period_start,
            date_to=period_end,
            leader_chat_id=settings.leaders_chat_id,
        )
        now = datetime.now(ZoneInfo(schedule.timezone))
        cycle_open = _local_datetime(cycle.opens_at, ZoneInfo(schedule.timezone))
        cycle_deadline = _local_datetime(cycle.deadline_at, ZoneInfo(schedule.timezone))
        if now < cycle_open:
            await session.commit()
            return

        if now < cycle_deadline:
            stages = []
            if now >= cycle_deadline - timedelta(hours=schedule.first_reminder_hours):
                stages.append("first")
            if now >= cycle_deadline - timedelta(hours=schedule.final_reminder_hours):
                stages.append("final")
            seen_users: set[int] = set()
            for _assignment, _office, user in await _active_leader_assignments(session):
                if user.id in seen_users:
                    continue
                seen_users.add(user.id)
                member = await session.scalar(
                    select(LeaderChatMembership).where(
                        LeaderChatMembership.leader_chat_id == settings.leaders_chat_id,
                        LeaderChatMembership.user_id == user.id,
                        LeaderChatMembership.is_weekly_pulse_eligible.is_(True),
                    )
                )
                if member is None:
                    continue
                report = await leadership_report_service.current_report(
                    session, owner_id=user.id, period_start=period_start
                )
                if report is not None and report.submitted_at is not None:
                    continue
                for stage in stages:
                    await send_bot_notification(
                        bot,
                        user.telegram_id,
                        emoji="⏳",
                        title="Напоминание: Weekly Pulse",
                        body=(
                            f"Отправьте отчёт за {period_start:%d.%m}–{period_end:%d.%m} "
                            f"до {cycle_deadline:%d.%m %H:%M}."
                        ),
                        action=(
                            PrimaryAction(
                                label="Открыть Weekly Pulse",
                                web_app_url=settings.effective_miniapp_url,
                            )
                            if settings.effective_miniapp_url
                            else None
                        ),
                        settings=settings,
                        delivery_key=f"leadership-pulse-cycle:{cycle.id}:{stage}:{user.id}",
                        notification_type="leadership_weekly_pulse_due",
                    )
            await session.commit()
            return

        eligible_owner_ids = {
            member.user_id
            for member in await eligible_members(
                session, leader_chat_id=settings.leaders_chat_id
            )
            if member.user_id is not None
        }
        created = await run_missed_report_signals(
            session,
            period_start=period_start,
            eligible_owner_ids=eligible_owner_ids,
        )
        await leadership_report_service.run_attention_rules(session, today=date.today())
        for item in created:
            user = await session.get(User, item.owner_id)
            if user is None:
                continue
            action = (
                PrimaryAction(label="Заполнить Weekly Pulse", web_app_url=settings.effective_miniapp_url)
                if settings.effective_miniapp_url
                else None
            )
            await send_bot_notification(
                bot,
                user.telegram_id,
                emoji="⏳",
                title="Weekly Pulse ждёт итог",
                body="Отчёт недели ещё не отправлен. Системные факты уже заполнены — остаётся ваша короткая оценка.",
                action=action,
                settings=settings,
                delivery_key=f"leadership-pulse-due:{period_start}:{user.id}",
                notification_type="leadership_weekly_pulse_due",
            )
        cycle.status = "processing"
        submitted = await session.scalar(
            select(func.count(func.distinct(LeadershipReport.owner_id))).where(
                LeadershipReport.pulse_cycle_id == cycle.id,
                LeadershipReport.submitted_at.is_not(None),
            )
        )
        cycle.submitted_count = int(submitted or 0)
        if cycle.announcement_message_id is not None:
            try:
                await bot.edit_message_text(
                    chat_id=settings.leaders_chat_id,
                    message_id=cycle.announcement_message_id,
                    text=(
                        f"📊 Пульс ЭРА · неделя {cycle.week_number}\n\n"
                        f"Срок закрыт. Ответили: {cycle.submitted_count} / "
                        f"{cycle.eligible_count}. Сводка передана администраторам."
                    ),
                )
            except TelegramAPIError:
                pass

        submitted_owner_ids = set(
            (
                await session.scalars(
                    select(LeadershipReport.owner_id).where(
                        LeadershipReport.pulse_cycle_id == cycle.id,
                        LeadershipReport.submitted_at.is_not(None),
                    )
                )
            ).all()
        )
        missing_names: list[str] = []
        for _assignment, _office, user in await _active_leader_assignments(session):
            if user.id in eligible_owner_ids and user.id not in submitted_owner_ids:
                missing_names.append(f"{user.first_name} {user.last_name or ''}".strip())
        if missing_names:
            summary = (
                f"Weekly Pulse · неделя {cycle.week_number}\n"
                f"Ответили: {cycle.submitted_count} / {cycle.eligible_count}.\n\n"
                "Не отправили отчёт:\n" + "\n".join(f"• {name}" for name in missing_names)
            )
            for admin_id in settings.admin_ids:
                await send_bot_notification(
                    bot,
                    admin_id,
                    title="Список неответивших по Weekly Pulse",
                    body=summary,
                    settings=settings,
                    delivery_key=f"leadership-pulse-missing:{cycle.id}:{admin_id}",
                    notification_type="leadership_weekly_pulse_admin_summary",
                )
        await session.commit()
