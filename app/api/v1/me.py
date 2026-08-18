from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.schemas import CURRENT_ONBOARDING_VERSION, MiniAppUserSummary, summarize_user
from app.config import Settings
from app.database.models import User

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MiniAppUserSummary)
async def read_me(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> MiniAppUserSummary:
    return summarize_user(user, settings)


@router.post("/me/onboarding-seen", response_model=MiniAppUserSummary)
async def mark_onboarding_seen(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> MiniAppUserSummary:
    """Community Verification ToR §35/§47: called once the participant
    finishes (or explicitly dismisses) the post-approval "Как устроена ЭРА"
    screen. Idempotent -- never lowers an already-current version."""
    if user.onboarding_version < CURRENT_ONBOARDING_VERSION:
        user.onboarding_version = CURRENT_ONBOARDING_VERSION
        user.onboarding_completed_at = datetime.now(timezone.utc)
        await session.flush()
    return summarize_user(user, settings)
