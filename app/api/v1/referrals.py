from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.referral_service import (
    ACTIVE_REFERRAL_POINTS,
    FIRST_EVENT_REFERRAL_POINTS,
    REFERRAL_MONTHLY_CAP,
    REFERRAL_PER_INVITEE_CAP,
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
        "active_points_each": ACTIVE_REFERRAL_POINTS,
        "per_invitee_cap": REFERRAL_PER_INVITEE_CAP,
        "monthly_cap": REFERRAL_MONTHLY_CAP,
        "invited_count": summary.invited_count,
        "registered_count": summary.registered_count,
        "first_event_count": summary.first_event_count,
        "active_count": summary.active_count,
        "earned_points": summary.earned_points,
        "monthly_earned_points": summary.monthly_earned_points,
    }
