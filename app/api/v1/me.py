from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.schemas import MiniAppUserSummary, summarize_user
from app.config import Settings
from app.database.models import User
from app.services import ui_preferences_service as ui_prefs

router = APIRouter(tags=["me"])


class UiPreferencesOut(BaseModel):
    accent_color: str | None = None
    updated_at: datetime | None = None


class UiPreferencesIn(BaseModel):
    # null resets to the default ERA colour.
    accent_color: str | None = None


def _preferences_out(row) -> UiPreferencesOut:
    if row is None:
        return UiPreferencesOut()
    return UiPreferencesOut(accent_color=row.accent_color, updated_at=row.updated_at)


@router.get("/me", response_model=MiniAppUserSummary)
async def read_me(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MiniAppUserSummary:
    return summarize_user(user, settings)


@router.get("/me/preferences", response_model=UiPreferencesOut)
async def read_ui_preferences(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UiPreferencesOut:
    return _preferences_out(await ui_prefs.get_ui_preferences(session, user.id))


@router.put("/me/preferences", response_model=UiPreferencesOut)
async def update_ui_preferences(
    payload: UiPreferencesIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UiPreferencesOut:
    try:
        row = await ui_prefs.set_accent_color(session, user.id, payload.accent_color)
    except ui_prefs.InvalidAccentColor:
        raise HTTPException(status_code=422, detail="invalid_accent_color")
    return _preferences_out(row)
