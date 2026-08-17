from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    LeadershipAttentionItem,
    LeadershipGoal,
    LeadershipReport,
    Office,
    Task,
    User,
    UserOffice,
)
from app.services.audit_service import audit
from app.services.notification_service import notify_admins, safe_send
from app.utils.constants import (
    AttentionItemSeverity,
    AttentionItemStatus,
    LeadershipGoalStatus,
    LeadershipReportStatus,
    TaskStatus,
)

# Leadership OS ToR sections 40-42, 61: the weekly quick report, the
# 🔴 -> attention-item escalation, and rule-based problem detection.

_BLOCKER_ATTENTION_TYPE = "leader_blocker"
_OVERDUE_ATTENTION_TYPE = "leader_overdue_tasks"
_NO_GOALS_ATTENTION_TYPE = "leader_no_monthly_goals"


@dataclass(frozen=True, slots=True)
class QuickReportResult:
    report: LeadershipReport
    attention_item: LeadershipAttentionItem | None


async def resolve_escalation_target(
    session: AsyncSession, office_assignment: UserOffice | None
) -> User | None:
    """"Логически вышестоящий руководитель" (ToR section 41) -- follows
    Office.reports_to_office_id to whoever currently holds the parent
    office. Falls back to None (caller notifies admins instead) when there
    is no parent office or it's currently vacant."""
    if office_assignment is None:
        return None
    office = await session.get(Office, office_assignment.office_id)
    if office is None or office.reports_to_office_id is None:
        return None
    holder_assignment = await session.scalar(
        select(UserOffice).where(
            UserOffice.office_id == office.reports_to_office_id,
            UserOffice.is_active.is_(True),
        )
    )
    if holder_assignment is None:
        return None
    return await session.get(User, holder_assignment.user_id)


async def submit_quick_report(
    session: AsyncSession,
    *,
    owner_id: int,
    period_start: date,
    period_end: date,
    status: str,
    scope_type: str = "global",
    scope_id: int | None = None,
    office_assignment_id: int | None = None,
    main_result: str | None = None,
    blocker_type: str | None = None,
    blocker_note: str | None = None,
    next_priorities: list[str] | None = None,
    needs_help: bool = False,
    bot: Bot | None = None,
    settings: Settings | None = None,
) -> QuickReportResult:
    # Idempotent per owner+period (ToR section 39) -- resubmitting the same
    # week's report updates it in place instead of creating a duplicate.
    report = await session.scalar(
        select(LeadershipReport).where(
            LeadershipReport.owner_id == owner_id,
            LeadershipReport.period_start == period_start,
        )
    )
    if report is None:
        report = LeadershipReport(owner_id=owner_id, period_start=period_start, period_end=period_end)
        session.add(report)

    report.office_assignment_id = office_assignment_id
    report.scope_type = scope_type
    report.scope_id = scope_id
    report.status = status
    report.main_result = (main_result or "").strip()[:1000] or None
    report.blocker_type = blocker_type
    report.blocker_note = (blocker_note or "").strip()[:1000] or None
    report.next_priorities = (next_priorities or [])[:3]
    report.needs_help = needs_help
    report.submitted_at = datetime.now(timezone.utc)
    await session.flush()

    attention_item = None
    if status == LeadershipReportStatus.NEEDS_HELP or needs_help:
        attention_item = await _escalate_blocker(
            session,
            owner_id=owner_id,
            office_assignment_id=office_assignment_id,
            scope_type=scope_type,
            scope_id=scope_id,
            note=report.blocker_note,
            bot=bot,
            settings=settings,
        )

    await audit(
        session,
        actor_id=owner_id,
        action="leadership_report.submitted",
        entity_type="leadership_report",
        entity_id=report.id,
        old_value=None,
        new_value={"status": status},
    )
    return QuickReportResult(report=report, attention_item=attention_item)


async def _escalate_blocker(
    session: AsyncSession,
    *,
    owner_id: int,
    office_assignment_id: int | None,
    scope_type: str,
    scope_id: int | None,
    note: str | None,
    bot: Bot | None,
    settings: Settings | None,
) -> LeadershipAttentionItem:
    existing = await session.scalar(
        select(LeadershipAttentionItem).where(
            LeadershipAttentionItem.type == _BLOCKER_ATTENTION_TYPE,
            LeadershipAttentionItem.owner_id == owner_id,
            LeadershipAttentionItem.status == AttentionItemStatus.OPEN,
        )
    )
    assignment = (
        await session.get(UserOffice, office_assignment_id) if office_assignment_id else None
    )
    responsible = await resolve_escalation_target(session, assignment)

    if existing is not None:
        existing.resolution = note  # reuse as a running "latest note" field until resolved
        return existing

    item = LeadershipAttentionItem(
        type=_BLOCKER_ATTENTION_TYPE,
        severity=AttentionItemSeverity.HIGH,
        scope_type=scope_type,
        scope_id=scope_id,
        owner_id=owner_id,
        responsible_id=responsible.id if responsible else None,
        status=AttentionItemStatus.OPEN,
    )
    session.add(item)
    await session.flush()

    if bot is not None and settings is not None:
        owner = await session.get(User, owner_id)
        owner_name = f"{owner.first_name} {owner.last_name or ''}".strip() if owner else str(owner_id)
        text = f"🔴 {owner_name} отметил(а) в отчёте: нужна помощь.\n\n{note or ''}".strip()
        if responsible is not None:
            await safe_send(bot, responsible.telegram_id, text)
        else:
            await notify_admins(bot, settings, text)

    return item


async def list_reports(
    session: AsyncSession, *, owner_id: int | None = None, scope_type: str | None = None
) -> list[LeadershipReport]:
    conditions = []
    if owner_id is not None:
        conditions.append(LeadershipReport.owner_id == owner_id)
    if scope_type is not None:
        conditions.append(LeadershipReport.scope_type == scope_type)
    return list(
        (
            await session.scalars(
                select(LeadershipReport).where(*conditions).order_by(LeadershipReport.period_start.desc())
            )
        ).all()
    )


async def current_report(session: AsyncSession, *, owner_id: int, period_start: date) -> LeadershipReport | None:
    return await session.scalar(
        select(LeadershipReport).where(
            LeadershipReport.owner_id == owner_id, LeadershipReport.period_start == period_start
        )
    )


async def list_attention_items(
    session: AsyncSession,
    *,
    status: str | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
    responsible_id: int | None = None,
) -> list[LeadershipAttentionItem]:
    conditions = []
    if status is not None:
        conditions.append(LeadershipAttentionItem.status == status)
    if scope_type is not None:
        conditions.append(LeadershipAttentionItem.scope_type == scope_type)
    if scope_id is not None:
        conditions.append(LeadershipAttentionItem.scope_id == scope_id)
    if responsible_id is not None:
        conditions.append(LeadershipAttentionItem.responsible_id == responsible_id)
    return list(
        (
            await session.scalars(
                select(LeadershipAttentionItem)
                .where(*conditions)
                .order_by(LeadershipAttentionItem.created_at.desc())
            )
        ).all()
    )


async def resolve_attention_item(
    session: AsyncSession, item: LeadershipAttentionItem, *, resolver_id: int, resolution: str | None
) -> LeadershipAttentionItem:
    item.status = AttentionItemStatus.RESOLVED
    item.resolved_at = datetime.now(timezone.utc)
    item.resolution = (resolution or "").strip()[:1000] or None
    await audit(
        session,
        actor_id=resolver_id,
        action="leadership_attention_item.resolved",
        entity_type="leadership_attention_item",
        entity_id=item.id,
        old_value=None,
        new_value={"status": item.status},
    )
    return item


# --- Rule-based problem detection (ToR section 61) --------------------------
# Deliberately a small, real, extensible starting set -- not every rule
# listed in the ToR -- each dedup'd against any already-open item of the
# same type for the same owner so re-running the check doesn't spam.

_OVERDUE_RATE_THRESHOLD = 0.37  # ToR section 61's own example figure


async def _create_if_absent(
    session: AsyncSession, *, type_: str, owner_id: int, scope_type: str, scope_id: int | None
) -> LeadershipAttentionItem | None:
    existing = await session.scalar(
        select(LeadershipAttentionItem).where(
            LeadershipAttentionItem.type == type_,
            LeadershipAttentionItem.owner_id == owner_id,
            LeadershipAttentionItem.status == AttentionItemStatus.OPEN,
        )
    )
    if existing is not None:
        return None
    item = LeadershipAttentionItem(
        type=type_,
        severity=AttentionItemSeverity.MEDIUM,
        scope_type=scope_type,
        scope_id=scope_id,
        owner_id=owner_id,
        status=AttentionItemStatus.OPEN,
    )
    session.add(item)
    await session.flush()
    return item


async def _leaders_with_active_offices(session: AsyncSession) -> list[UserOffice]:
    # JSON columns don't compare portably in SQL (varies by dialect), so the
    # "does this office actually grant anything" filter happens in Python.
    rows = (
        await session.execute(
            select(UserOffice, Office)
            .join(Office, Office.id == UserOffice.office_id)
            .where(UserOffice.is_active.is_(True))
        )
    ).all()
    return [a for a, o in rows if o.permission_template]


async def run_attention_rules(
    session: AsyncSession, *, today: date | None = None
) -> list[LeadershipAttentionItem]:
    today = today or date.today()
    created: list[LeadershipAttentionItem] = []

    for assignment in await _leaders_with_active_offices(session):
        total = int(
            await session.scalar(
                select(func.count()).select_from(Task).where(Task.assignee_id == assignment.user_id)
            )
            or 0
        )
        if total >= 5:
            overdue = int(
                await session.scalar(
                    select(func.count())
                    .select_from(Task)
                    .where(
                        Task.assignee_id == assignment.user_id,
                        Task.status != TaskStatus.COMPLETED,
                        Task.deadline < datetime.now(timezone.utc),
                    )
                )
                or 0
            )
            if overdue / total >= _OVERDUE_RATE_THRESHOLD:
                item = await _create_if_absent(
                    session,
                    type_=_OVERDUE_ATTENTION_TYPE,
                    owner_id=assignment.user_id,
                    scope_type="office",
                    scope_id=assignment.office_id,
                )
                if item:
                    created.append(item)

        month_start = today.replace(day=1)
        has_goal = await session.scalar(
            select(func.count())
            .select_from(LeadershipGoal)
            .where(
                LeadershipGoal.owner_id == assignment.user_id,
                LeadershipGoal.status != LeadershipGoalStatus.CANCELLED,
                LeadershipGoal.period_end >= month_start,
            )
        )
        if not has_goal:
            item = await _create_if_absent(
                session,
                type_=_NO_GOALS_ATTENTION_TYPE,
                owner_id=assignment.user_id,
                scope_type="office",
                scope_id=assignment.office_id,
            )
            if item:
                created.append(item)

    return created
