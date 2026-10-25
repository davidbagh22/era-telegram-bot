from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.community_verification_models import CommunityVerificationCampaign
from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.community_verification_service import (
    active_campaign,
    campaign_segment_rows,
    complete_due_campaigns,
    remind_selected,
    remove_selected,
    retain_selected,
    start_campaign,
)

router = APIRouter(prefix="/admin/community-verification", tags=["admin-verification"])
REMOVE_CONFIRMATION = "REMOVE_SELECTED"


class CampaignStartIn(BaseModel):
    duration_hours: int = Field(ge=1, le=720)
    pin_group_message: bool = True
    idempotency_key: str | None = Field(default=None, max_length=160)


class SelectionIn(BaseModel):
    telegram_ids: list[int] = Field(min_length=1, max_length=500)


class RemoveSelectionIn(SelectionIn):
    confirmation: str


class CampaignOut(BaseModel):
    id: int
    status: str
    duration_hours: int
    started_at: str
    ends_at: str
    completed_at: str | None
    group_message_id: int | None
    group_pinned: bool
    counts: dict[str, int]
    delivery_counts: dict[str, int]
    rows: list[dict]


class SelectionResultOut(BaseModel):
    requested: int
    changed: int
    failed: int = 0


def _require_admin(user: User, settings: Settings) -> None:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")


def _require_bot(bot: Bot | None) -> Bot:
    if bot is None:
        raise HTTPException(status_code=503, detail="telegram_bot_unavailable")
    return bot


async def _campaign_out(session: AsyncSession, campaign) -> CampaignOut:
    rows = await campaign_segment_rows(session, campaign)
    counts = Counter(str(row["registration_status"]) for row in rows)
    delivery_counts = Counter(str(row["delivery_status"]) for row in rows)
    return CampaignOut(
        id=campaign.id,
        status=campaign.status,
        duration_hours=campaign.duration_hours,
        started_at=campaign.started_at.isoformat(),
        ends_at=campaign.ends_at.isoformat(),
        completed_at=campaign.completed_at.isoformat() if campaign.completed_at else None,
        group_message_id=campaign.group_message_id,
        group_pinned=campaign.group_pinned,
        counts=dict(counts),
        delivery_counts=dict(delivery_counts),
        rows=rows,
    )


async def _latest_campaign(session: AsyncSession) -> CommunityVerificationCampaign | None:
    return await session.scalar(
        select(CommunityVerificationCampaign)
        .order_by(CommunityVerificationCampaign.started_at.desc())
        .limit(1)
    )


@router.get("", response_model=CampaignOut | None)
async def read_verification_campaign(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> CampaignOut | None:
    _require_admin(user, settings)
    await complete_due_campaigns(session, now=datetime.now(timezone.utc))
    campaign = await _latest_campaign(session)
    if campaign is None:
        return None
    return await _campaign_out(session, campaign)


@router.post("/start", response_model=CampaignOut)
async def start_verification_campaign(
    payload: CampaignStartIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    _require_admin(user, settings)
    real_bot = _require_bot(bot)
    try:
        result = await start_campaign(
            real_bot,
            settings,
            session,
            duration_hours=payload.duration_hours,
            actor_id=user.id,
            pin_group_message=payload.pin_group_message,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _campaign_out(session, result.campaign)


@router.post("/remind", response_model=SelectionResultOut)
async def remind_verification_selection(
    payload: SelectionIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    session: AsyncSession = Depends(get_session),
) -> SelectionResultOut:
    _require_admin(user, settings)
    campaign = await active_campaign(session)
    if campaign is None:
        raise HTTPException(status_code=409, detail="verification_campaign_not_active")
    deliveries = await remind_selected(_require_bot(bot), session, campaign, payload.telegram_ids)
    changed = sum(1 for row in deliveries if row.status == "sent")
    failed = sum(1 for row in deliveries if row.status in {"failed", "blocked", "unreachable"})
    return SelectionResultOut(requested=len(payload.telegram_ids), changed=changed, failed=failed)


@router.post("/retain", response_model=SelectionResultOut)
async def retain_verification_selection(
    payload: SelectionIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> SelectionResultOut:
    _require_admin(user, settings)
    changed = await retain_selected(session, payload.telegram_ids)
    return SelectionResultOut(requested=len(payload.telegram_ids), changed=changed)


@router.post("/remove", response_model=SelectionResultOut)
async def remove_verification_selection(
    payload: RemoveSelectionIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
    session: AsyncSession = Depends(get_session),
) -> SelectionResultOut:
    _require_admin(user, settings)
    if payload.confirmation != REMOVE_CONFIRMATION:
        raise HTTPException(status_code=422, detail="removal_confirmation_required")
    try:
        removed, failed = await remove_selected(
            _require_bot(bot), settings, session, payload.telegram_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SelectionResultOut(
        requested=len(payload.telegram_ids),
        changed=removed,
        failed=failed,
    )
