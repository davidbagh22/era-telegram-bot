"""Personal-message and chat broadcasts — shared by the bot's "📨 Рассылка в
личные сообщения" and "📣 Сообщение в выбранные чаты" flows
(app/handlers/admin/panel.py, app/handlers/admin/management_ready.py) and
the Mini App's admin tools. See app/services/admin_goals_service.py for why
this is extracted.

Chat binding itself (attaching a Telegram chat_id to a chat_key via a
forwarded message) stays bot-only by design — Telegram only exposes a
chat's id through a message actually sent in it, which a web form can't
replicate. This service only sends to chats that are already bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Broadcast, Department, Direction, User, UserDepartment, UserDirection
from app.services.audit_service import audit
from app.services.notification_service import BroadcastResult, broadcast_detailed, safe_send
from app.utils.constants import ApplicationStatus

AUDIENCE_TYPES = {"all", "role", "department", "direction", "age", "city"}
ROLE_FILTER_VALUES = {"participant", "activist", "leader", "head", "council"}
AGE_RANGES: dict[str, tuple[int, int]] = {
    "14_17": (14, 17),
    "18_24": (18, 24),
    "25_34": (25, 34),
    "35_plus": (35, 200),
}
CHAT_KEYS = {"general", "internal", "external", "leaders"}
MAX_TEXT_LENGTH = 3500


class BroadcastError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class AudienceOption:
    value: str
    label: str


async def department_options(session: AsyncSession) -> list[AudienceOption]:
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    return [AudienceOption(value=str(d.id), label=d.name) for d in departments]


async def direction_options(session: AsyncSession) -> list[AudienceOption]:
    directions = (await session.scalars(select(Direction).order_by(Direction.name))).all()
    return [AudienceOption(value=str(d.id), label=d.name) for d in directions]


def _parse_id(filter_value: str | None) -> int:
    if not filter_value:
        raise BroadcastError("filter_required")
    try:
        return int(filter_value)
    except ValueError as exc:
        raise BroadcastError("invalid_filter") from exc


async def _resolve_recipients(
    session: AsyncSession, audience: str, filter_value: str | None
) -> list[User]:
    if audience not in AUDIENCE_TYPES:
        raise BroadcastError("invalid_audience")
    query = select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_blocked.is_(False),
    )
    if audience == "role":
        if filter_value not in ROLE_FILTER_VALUES:
            raise BroadcastError("invalid_filter")
        query = query.where(User.role == filter_value)
    elif audience == "department":
        query = query.join(UserDepartment).where(UserDepartment.department_id == _parse_id(filter_value))
    elif audience == "direction":
        query = query.join(UserDirection).where(UserDirection.direction_id == _parse_id(filter_value))
    elif audience == "city":
        if not filter_value or not filter_value.strip():
            raise BroadcastError("filter_required")
        query = query.where(func.lower(User.city) == filter_value.strip().lower())
    elif audience == "age":
        if filter_value not in AGE_RANGES:
            raise BroadcastError("invalid_filter")
        low, high = AGE_RANGES[filter_value]
        query = query.where(User.age.between(low, high))
    return list((await session.scalars(query)).unique().all())


async def preview_recipient_count(session: AsyncSession, audience: str, filter_value: str | None) -> int:
    return len(await _resolve_recipients(session, audience, filter_value))


async def send_personal_broadcast(
    bot: Bot,
    session: AsyncSession,
    *,
    audience: str,
    filter_value: str | None,
    text: str,
    author_id: int | None,
) -> BroadcastResult:
    text = text.strip()[:MAX_TEXT_LENGTH]
    if not text:
        raise BroadcastError("text_required")
    recipients = await _resolve_recipients(session, audience, filter_value)
    item = Broadcast(
        title="Рассылка ЭРА",
        text=text,
        audience_type=audience,
        audience_filter_json={"value": filter_value} if filter_value else {},
        author_id=author_id,
        status="sending",
    )
    session.add(item)
    await session.flush()
    result = await broadcast_detailed(bot, (u.telegram_id for u in recipients), text)
    item.status = "sent"
    item.sent_at = datetime.now().astimezone()
    await audit(
        session,
        actor_id=author_id,
        action="broadcast.sent",
        entity_type="broadcast",
        entity_id=item.id,
        new_value={
            "sent": result.sent,
            "failed": result.failed,
            "duplicates": result.duplicates,
            "temporary_failed": result.temporary_failed,
            "permanent_failed": result.permanent_failed,
        },
    )
    return result


async def send_chat_broadcast(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    *,
    chat_key: str,
    text: str,
    actor_id: int | None,
) -> None:
    if chat_key not in CHAT_KEYS:
        raise BroadcastError("invalid_chat")
    text = text.strip()[:MAX_TEXT_LENGTH]
    if not text:
        raise BroadcastError("text_required")
    chat_ids = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    chat_id = chat_ids.get(chat_key)
    if not chat_id:
        raise BroadcastError("chat_not_bound")
    ok = await safe_send(bot, chat_id, text)
    if not ok:
        # Was silently dropped before (2026-08 chat infrastructure audit,
        # docs/SYSTEM_FLOW_MATRIX.md) -- the registry's "last error" column
        # needs a real audit trail to read from, not just the admin's own
        # in-the-moment error toast. Staged here, not committed -- the
        # caller (app/api/v1/admin.py's send_chat_broadcast_endpoint) must
        # commit it explicitly before the BroadcastError propagates out of
        # get_session's request scope, which would otherwise roll it back
        # along with everything else in this failed request.
        await audit(
            session,
            actor_id=actor_id,
            action="chat.broadcast_failed",
            entity_type="chat",
            entity_id=None,
            new_value={"chat": chat_key},
        )
        raise BroadcastError("delivery_failed")
    await audit(
        session,
        actor_id=actor_id,
        action="chat.broadcast_sent",
        entity_type="chat",
        entity_id=None,
        new_value={"chat": chat_key},
    )
