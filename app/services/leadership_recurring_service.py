from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LeadershipRecurringTemplate, Task, UserOffice
from app.utils.constants import TaskStatus

# Leadership OS ToR sections 36-37, 81: recurring responsibility *templates*
# are new (LeadershipRecurringTemplate); each period's actual to-do is a
# plain Task (section 81: "не создавать LeadershipTask, если Task способен
# покрыть функцию") assigned to the office holder, tagged so it's
# recognizable as a recurring-responsibility instance rather than an
# ad-hoc task.

RECURRING_TASK_MARKER = "leadership_recurring_template_id"


def current_period(frequency: str, *, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if frequency == "weekly":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    start = today.replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return start, end


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)


async def list_templates_for_office(
    session: AsyncSession, office_id: int
) -> list[LeadershipRecurringTemplate]:
    """Templates apply either to one specific office (office_id set) or to
    every leadership office (office_id is NULL -- the universal minimum set,
    ToR section 36)."""
    return list(
        (
            await session.scalars(
                select(LeadershipRecurringTemplate).where(
                    LeadershipRecurringTemplate.is_active.is_(True),
                    (LeadershipRecurringTemplate.office_id == office_id)
                    | (LeadershipRecurringTemplate.office_id.is_(None)),
                )
            )
        ).all()
    )


async def sync_recurring_tasks(
    session: AsyncSession, assignment: UserOffice, *, today: date | None = None
) -> list[Task]:
    """Idempotent: creates one Task per active template per current period
    for this assignment's holder, skipping ones that already exist (ToR
    section 39: "idempotency; dedup; completed item не напоминается")."""
    today = today or date.today()
    templates = await list_templates_for_office(session, assignment.office_id)
    created: list[Task] = []
    for template in templates:
        period_start, period_end = current_period(template.frequency, today=today)
        marker = f"{RECURRING_TASK_MARKER}:{template.id}:{period_start.isoformat()}"
        existing = await session.scalar(
            select(Task).where(
                Task.assignee_id == assignment.user_id,
                Task.comment == marker,
            )
        )
        if existing is not None:
            continue
        task = Task(
            title=template.title,
            description=template.description or template.title,
            assignee_id=assignment.user_id,
            creator_id=assignment.appointed_by,
            deadline=_end_of_day(period_end),
            points=0,
            status=TaskStatus.NEW,
            task_type="private",
            comment=marker,
        )
        session.add(task)
        created.append(task)
    if created:
        await session.flush()
    return created
