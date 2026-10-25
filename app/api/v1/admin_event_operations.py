from __future__ import annotations

import csv
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, Response
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Event, User
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
        result.append(
            EventParticipantDetailOut(
                registration_id=registration.id,
                participant_id=participant.id,
                participant_name=f"{first_name} {last_name}".strip(),
                first_name=first_name,
                last_name=last_name,
                status=registration.status,
            )
        )
    return result


def _safe_export_name(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


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
    sheet.append(["Имя", "Фамилия", "Номер телефона"])
    for _registration, participant in rows:
        sheet.append(
            [
                _safe_export_name(participant.first_name or ""),
                _safe_export_name(participant.last_name or ""),
                participant.phone or "",
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
    writer.writerow(["Имя", "Фамилия", "Номер телефона"])
    for _registration, participant in rows:
        writer.writerow(
            [
                _safe_export_name(participant.first_name or ""),
                _safe_export_name(participant.last_name or ""),
                participant.phone or "",
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ERA_event_{event_id}_participants.csv"'},
    )
