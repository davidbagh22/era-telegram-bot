from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.referral_service import (
    FIRST_EVENT_REFERRAL_POINTS,
    REGISTRATION_REFERRAL_POINTS,
    get_referral_summary,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/me")
async def my_referral_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    summary = await get_referral_summary(session, user=user, settings=settings)
    await session.commit()
    return {
        "code": summary.code,
        "invite_url": summary.invite_url,
        "share_text": summary.share_text,
        "registration_points_each": REGISTRATION_REFERRAL_POINTS,
        "first_event_points_each": FIRST_EVENT_REFERRAL_POINTS,
        "invited_count": summary.invited_count,
        "registered_count": summary.registered_count,
        "first_event_count": summary.first_event_count,
        "earned_points": summary.earned_points,
    }
