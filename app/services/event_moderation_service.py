from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, User
from app.services.audit_service import audit
from app.utils.constants import EventStatus

EVENT_DECISION_ACTIONS = ("approve", "revise", "reject")


@dataclass(frozen=True)
class EventDecisionResult:
    event: Event
    owner: User | None
    notice: str


async def list_events_for_review(session: AsyncSession) -> list[Event]:
    rows = await session.scalars(
        select(Event)
        .where(Event.status == EventStatus.PENDING_APPROVAL)
        .order_by(Event.event_date, Event.event_time)
    )
    return list(rows.all())


async def decide_event(
    session: AsyncSession,
    event: Event,
    *,
    action: str,
    comment: str,
    actor: User,
) -> EventDecisionResult:
    if action not in EVENT_DECISION_ACTIONS:
        raise ValueError(f"unknown event decision action: {action!r}")
    if action in ("revise", "reject") and not comment.strip():
        raise ValueError("comment_required")

    owner = await session.get(User, event.created_by)

    if action == "approve":
        event.status = EventStatus.APPROVED
        event.approved_by = actor.id
        await audit(
            session,
            actor_id=actor.id,
            action="event.approved_without_broadcast",
            entity_type="event",
            entity_id=event.id,
        )
        notice = (
            f"Мероприятие «{event.title}» одобрено. Рассылка будет только после "
            "отдельного подтверждения админа."
        )
    elif action == "revise":
        event.status = EventStatus.DRAFT
        notice = f"Мероприятие «{event.title}» возвращено на доработку\n\n{comment}"
    else:
        event.status = EventStatus.CANCELLED
        notice = f"Мероприятие «{event.title}» отклонено\n\n{comment}"

    return EventDecisionResult(event=event, owner=owner, notice=notice)
