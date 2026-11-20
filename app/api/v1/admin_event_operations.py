from __future__ import annotations

import csv
from hashlib import sha256

from aiogram import Bot
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.services.notification_service import broadcast_detailed_once
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import telegram_event_miniapp_url
from app.services import event_registration_service
from app.services.authorization_service import can_manage_events

router = APIRouter(prefix="/admin/events", tags=["admin-event-operations"])


async def require_event_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


class EventParticipantDetailOut(BaseModel):
    organization: str | None = None
    phone: str | None = None
    registration_id: int
    participant_id: int
    participant_name: str
    first_name: str
    last_name: str
    status: str


async def _rows(session: AsyncSession, event_id: int):
    # Real SQLAlchemy sessions verify the object for a clean 404. Lightweight
    # service-unit doubles used by the existing suite may intentionally expose
    # only the participant service contract, so do not couple them to Session.get.
    getter = getattr(session, "get", None)
    if getter is not None and await getter(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return await event_registration_service.list_participants(session, event_id)


@router.get("/{event_id}/participants", response_model=list[EventParticipantDetailOut])
async def read_event_participants(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> list[EventParticipantDetailOut]:
    result: list[EventParticipantDetailOut] = []
    for registration, participant in await _rows(session, event_id):
        first_name = participant.first_name or ""
        last_name = participant.last_name or ""
        signup = getattr(registration, "signup", None) or {}
        result.append(
            EventParticipantDetailOut(
                registration_id=registration.id,
                participant_id=participant.id,
                participant_name=signup.get("full_name") or f"{first_name} {last_name}".strip(),
                organization=signup.get("organization"), phone=signup.get("phone"),
                first_name=first_name,
                last_name=last_name,
                status=registration.status,
            )
        )
    return result


def _safe_export_name(value: str) -> str:
    clean = value.replace("\r", " ").replace("\n", " ").strip()
    return "'" + clean if clean.startswith(("=", "+", "-", "@")) else clean


@router.get("/{event_id}/participants/export.xlsx")
async def export_event_participants_xlsx(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await _rows(session, event_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Участники"
    sheet.append(["Имя", "Фамилия", "Номер телефона", "ФИО для регистрации", "Организация или вуз"])
    for _registration, participant in rows:
        sheet.append(
            [
                _safe_export_name(participant.first_name or ""),
                _safe_export_name(participant.last_name or ""),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("phone") or participant.phone or ""),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("full_name", "")),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("organization", "")),
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 24
    sheet.column_dimensions["B"].width = 28
    sheet.column_dimensions["C"].width = 22
    output = BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ERA_event_{event_id}_participants.xlsx"'},
    )


@router.get("/{event_id}/participants/export.csv")
async def export_event_participants_csv(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await _rows(session, event_id)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Имя", "Фамилия", "Номер телефона", "ФИО для регистрации", "Организация или вуз"])
    for _registration, participant in rows:
        writer.writerow(
            [
                _safe_export_name(participant.first_name or ""),
                _safe_export_name(participant.last_name or ""),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("phone") or participant.phone or ""),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("full_name", "")),
                _safe_export_name((getattr(_registration, "signup", None) or {}).get("organization", "")),
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ERA_event_{event_id}_participants.csv"'},
    )


class EventShareTextOut(BaseModel):
    text: str


@router.get("/{event_id}/share-text", response_model=EventShareTextOut)
async def read_event_share_text(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EventShareTextOut:
    """Copy-ready public announcement, built from the *current* saved event.

    It never generates speculative forum URLs, and never sends a Telegram
    message. The registration deep link is tied to the selected event.
    """
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if event.status not in {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}:
        raise HTTPException(status_code=409, detail="event_not_published")

    experience = await session.get(EventExperience, event_id)
    description = (
        (experience.full_description if experience else None)
        or event.description
        or ""
    ).strip()
    title = event.title.strip()
    body = description if description.split("\n", 1)[0].strip() == title else f"{title}\n\n{description}"
    end_time = experience.end_time if experience else None
    interval = event.event_time.strftime("%H:%M")
    if end_time:
        interval += "–" + end_time.strftime("%H:%M")
    parts = [
        body.strip(),
        f"📅 {event.event_date:%d.%m.%Y} · {interval}",
        f"📍 {event.location}",
    ]

    general_link = str(settings.general_chat_url or "").strip()
    topic_link = str(experience.chat_url or "").strip() if experience else ""
    external_url = ""
    if experience and not experience.registration_required:
        external_url = str(experience.registration_url or experience.contact or "").strip()
    register_link = (external_url if external_url.startswith("https://")
                     else telegram_event_miniapp_url(settings.bot_username or "ERA_1bot", event.id))
    if general_link:
        parts.append("💬 Общий чат ЭРА: " + general_link)
    if topic_link:
        parts.append("📌 Тема мероприятия: " + topic_link)
    if register_link:
        parts.append("📝 Зарегистрироваться: " + register_link)
    return EventShareTextOut(text="\n\n".join(parts))


class RegistrantMessage(BaseModel):
    message: str = Field(min_length=1, max_length=3500)
    confirmation: str | None = Field(default=None, max_length=64)


@router.post("/{event_id}/participants/message")
async def message_registrants(
    event_id: int, payload: RegistrantMessage,
    admin: User = Depends(require_event_manager), session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings), bot: Bot | None = Depends(get_bot),
):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "event_not_found")
    body = payload.message.strip()
    message = f"{event.title}\n\n{body}"
    if not body or len(message.encode("utf-16-le")) // 2 > 4096:
        raise HTTPException(422, "message_length")
    recipients = list(await session.scalars(select(User.telegram_id).join(
        EventRegistration, EventRegistration.user_id == User.id,
    ).where(
        EventRegistration.event_id == event_id,
        EventRegistration.status.in_([RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME]),
        User.is_blocked.is_(False), User.is_archived.is_(False),
    ).distinct().order_by(User.telegram_id)))
    digest = sha256(message.encode()).hexdigest()
    identity = f"{admin.id}:{event_id}:{digest}:{recipients}"
    confirmation = sha256(identity.encode()).hexdigest()
    if payload.confirmation is None:
        return {"message": message, "count": len(recipients), "confirmation": confirmation}
    if payload.confirmation != confirmation:
        raise HTTPException(409, "Аудитория или текст изменились. Откройте предпросмотр ещё раз.")
    if bot is None:
        raise HTTPException(503, "Бот временно недоступен")
    result = await broadcast_detailed_once(
        bot, settings, recipients, message,
        delivery_key=f"event-members:{event_id}:{digest}", notification_type="event_members",
        max_attempts=1,
    )
    return {"sent": result.sent, "failed": result.failed, "total": result.total,
            "already_sent": result.total - result.sent - result.failed}
