"""Recent activity feed for Admin Mode's Overview screen — the "Последняя
активность" section of the 2026-08 Admin Mode redesign.

Reads app/database/models.py's existing AuditLog directly rather than
inventing a second activity-tracking mechanism: every mutating admin/
participant action in this codebase already calls
app/services/audit_service.py::audit(), so AuditLog is already a complete,
real record — this just makes it legible instead of fabricating a
lighter-weight summary alongside it.

Deliberately does not attempt an exhaustive label for every one of the
~60 distinct `action` strings used across the codebase (grep for
`action="` if you need the full list) — ACTION_LABELS covers the ones an
admin actually cares to see at a glance in a short feed; anything else
still renders (never a raw blank), just less prettily, via
_humanize_fallback below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, User

ACTION_LABELS: dict[str, str] = {
    "user.registered": "зарегистрировался(-ась)",
    "user.approved": "одобрил(а) заявку",
    "user.rejected": "отклонил(а) заявку",
    "user.needs_info": "запросил(а) уточнение по заявке",
    "project.submitted": "отправил(а) проект на рассмотрение",
    "project.draft_created": "создал(а) черновик проекта",
    "project.created": "создал(а) проект",
    "event.submitted": "отправил(а) мероприятие на согласование",
    "event.registered": "зарегистрировался(-ась) на мероприятие",
    "event.broadcast_published": "опубликовал(а) анонс мероприятия",
    "task.created": "создал(а) задачу",
    "task.admin_created": "создал(а) задачу",
    "task.open_published": "опубликовал(а) открытую задачу",
    "question.created": "задал(а) вопрос",
    "broadcast.sent": "отправил(а) рассылку",
    "chat.broadcast_sent": "отправил(а) сообщение в чат",
    "points.added": "начислил(а) баллы",
    "portfolio.item_added": "добавил(а) запись в портфолио",
    "department.application_created": "подал(а) заявку на направление",
    "user.role_changed": "изменил(а) роль участника",
    "user.permission_changed": "изменил(а) права участника",
    "user.status_changed": "изменил(а) статус участника",
    "user.data_exported": "выгрузил(а) свои данные",
    "user.deletion_requested": "запросил(а) удаление аккаунта",
}


def _humanize_fallback(action: str) -> str:
    tail = action.rsplit(".", 1)[-1]
    return tail.replace("_", " ")


@dataclass(slots=True)
class ActivityEntry:
    id: int
    actor_name: str | None
    summary: str
    entity_type: str
    created_at: datetime


async def recent_activity(session: AsyncSession, limit: int = 12) -> list[ActivityEntry]:
    rows = (
        await session.execute(
            select(AuditLog, User.first_name, User.last_name)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    entries: list[ActivityEntry] = []
    for log, first_name, last_name in rows:
        actor_name = " ".join(part for part in (first_name, last_name) if part) or None
        summary = ACTION_LABELS.get(log.action, _humanize_fallback(log.action))
        entries.append(
            ActivityEntry(
                id=log.id,
                actor_name=actor_name,
                summary=summary,
                entity_type=log.entity_type,
                created_at=log.created_at,
            )
        )
    return entries
