from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.activity_service import calendar_items, history_entries

router = APIRouter(prefix="/activity", tags=["activity"])


class CalendarItemOut(BaseModel):
    kind: str
    id: int
    title: str
    date: str
    time: str | None


class HistoryEntryOut(BaseModel):
    kind: str
    title: str
    date: str
    detail: str


@router.get("/calendar", response_model=list[CalendarItemOut])
async def read_calendar(
    days_ahead: int = Query(60, ge=1, le=365),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CalendarItemOut]:
    items = await calendar_items(session, user, days_ahead=days_ahead)
    return [
        CalendarItemOut(kind=item.kind, id=item.id, title=item.title, date=item.date, time=item.time)
        for item in items
    ]


@router.get("/history", response_model=list[HistoryEntryOut])
async def read_history(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[HistoryEntryOut]:
    entries = await history_entries(session, user, limit=limit)
    return [
        HistoryEntryOut(kind=entry.kind, title=entry.title, date=entry.date, detail=entry.detail)
        for entry in entries
    ]
