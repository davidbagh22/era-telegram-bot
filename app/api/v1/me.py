from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_settings
from app.api.v1.schemas import MiniAppUserSummary, summarize_user
from app.config import Settings
from app.database.models import User

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MiniAppUserSummary)
async def read_me(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MiniAppUserSummary:
    return summarize_user(user, settings)
