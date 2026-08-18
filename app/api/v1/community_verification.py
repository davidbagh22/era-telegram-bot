"""Community Verification ToR §7-16/§19: admin campaign control, dashboard,
and the launch/reminder DM waves + pinned chat post.

Removal/moderation-gate changes are a later phase of the same ToR.
"""

from __future__ import annotations

from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_session, get_settings
from app.api.v1.admin import enforce_admin_action_rate_limit, require_full_admin
from app.config import Settings
from app.database.models import User
from app.services import community_verification_service as cv_service

router = APIRouter(prefix="/admin/community-verification", tags=["admin-community-verification"])


class CampaignOut(BaseModel):
    id: int
    status: Literal["not_started", "active", "completed"]
    window_hours: int
    started_at: str | None
    ends_at: str | None
    completed_at: str | None


class SegmentsOut(BaseModel):
    chat_members_total: int | None
    known_to_system: int
    pending: int
    approved: int
    rejected: int
    needs_info: int
    notified: int
    unreachable: int
    not_registered_estimate: int | None


class CampaignStatusOut(BaseModel):
    campaign: CampaignOut | None
    segments: SegmentsOut


def _campaign_out(campaign) -> CampaignOut | None:
    if campaign is None:
        return None
    return CampaignOut(
        id=campaign.id,
        status=campaign.status,
        window_hours=campaign.window_hours,
        started_at=campaign.started_at.isoformat() if campaign.started_at else None,
        ends_at=campaign.ends_at.isoformat() if campaign.ends_at else None,
        completed_at=campaign.completed_at.isoformat() if campaign.completed_at else None,
    )


@router.get("/status", response_model=CampaignStatusOut)
async def read_campaign_status(
    _admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> CampaignStatusOut:
    await cv_service.complete_expired_campaigns(session)
    status = await cv_service.campaign_status(session, bot, settings)
    return CampaignStatusOut(
        campaign=_campaign_out(status.campaign),
        segments=SegmentsOut(**status.segments.__dict__),
    )


class StartCampaignIn(BaseModel):
    window_hours: int = cv_service.DEFAULT_WINDOW_HOURS


@router.post("/start", response_model=CampaignOut)
async def start_campaign_endpoint(
    payload: StartCampaignIn,
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> CampaignOut:
    try:
        campaign = await cv_service.start_campaign(
            session, window_hours=payload.window_hours, started_by=admin.id
        )
    except cv_service.CampaignError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    return _campaign_out(campaign)


@router.post("/complete", response_model=CampaignOut)
async def complete_campaign_endpoint(
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> CampaignOut:
    campaign = await cv_service.active_campaign(session)
    if campaign is None:
        raise HTTPException(status_code=409, detail="no_active_campaign")
    campaign = await cv_service.complete_campaign(session, campaign, actor_id=admin.id)
    return _campaign_out(campaign)


class LaunchWaveOut(BaseModel):
    pin_status: Literal["posted", "already_posted", "failed", "no_chat_bound"]
    total_recipients: int
    already_attempted: int
    sent: int
    blocked: int
    unreachable: int
    failed: int


def _wave_out(pin_status: str, result: cv_service.WaveResult) -> LaunchWaveOut:
    return LaunchWaveOut(
        pin_status=pin_status,
        total_recipients=result.total_recipients,
        already_attempted=result.already_attempted,
        sent=result.sent,
        blocked=result.blocked,
        unreachable=result.unreachable,
        failed=result.failed,
    )


@router.post("/send-launch", response_model=LaunchWaveOut)
async def send_launch_endpoint(
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> LaunchWaveOut:
    """ToR §8/§10: one pinned chat post + the same text as a personal DM to
    every known user. Safe to call more than once -- both the pin and the
    per-recipient DMs are idempotent, so a retry after a partial failure
    (timeout, bot restart) only ever reaches whoever hasn't been reached yet."""
    campaign = await cv_service.active_campaign(session)
    if campaign is None:
        raise HTTPException(status_code=409, detail="no_active_campaign")
    pin_status = await cv_service.post_launch_pin(session, bot, settings, campaign, actor_id=admin.id)
    result = await cv_service.send_launch_wave(session, bot, campaign, actor_id=admin.id)
    return _wave_out(pin_status, result)


class NotRegisteredEntryOut(BaseModel):
    telegram_id: int
    delivery_status: str
    notified_at: str | None


@router.get("/not-registered", response_model=list[NotRegisteredEntryOut])
async def list_not_registered_endpoint(
    _admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
) -> list[NotRegisteredEntryOut]:
    campaign = await cv_service.latest_campaign(session)
    if campaign is None:
        return []
    entries = await cv_service.not_registered_recipients(session, campaign)
    return [
        NotRegisteredEntryOut(
            telegram_id=entry.telegram_id,
            delivery_status=entry.delivery_status,
            notified_at=entry.notified_at.isoformat() if entry.notified_at else None,
        )
        for entry in entries
    ]


class TelegramIdsIn(BaseModel):
    telegram_ids: list[int]


class RemindSelectedOut(BaseModel):
    requested: int
    eligible: int
    sent: int
    blocked: int
    unreachable: int
    failed: int


@router.post("/remind", response_model=RemindSelectedOut)
async def remind_selected_endpoint(
    payload: TelegramIdsIn,
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RemindSelectedOut:
    """ToR §16's per-person/bulk "Напомнить"."""
    if not payload.telegram_ids:
        raise HTTPException(status_code=422, detail="telegram_ids_required")
    campaign = await cv_service.latest_campaign(session)
    if campaign is None:
        raise HTTPException(status_code=409, detail="no_campaign")
    result = await cv_service.remind_selected(session, bot, campaign, payload.telegram_ids, actor_id=admin.id)
    return RemindSelectedOut(**result.__dict__)


class RemoveSelectedOut(BaseModel):
    requested: int
    removed: int
    failed: int


@router.post("/remove", response_model=RemoveSelectedOut)
async def remove_selected_endpoint(
    payload: TelegramIdsIn,
    admin: User = Depends(require_full_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_admin_action_rate_limit),
) -> RemoveSelectedOut:
    """ToR §16/§17's per-person/bulk "Удалить" -- deliberately requires an
    explicit admin call every time (never automatic), matching the ToR's
    strongest constraint: no auto-removal of anyone but REJECTED applicants."""
    if not payload.telegram_ids:
        raise HTTPException(status_code=422, detail="telegram_ids_required")
    result = await cv_service.remove_selected(session, bot, settings, payload.telegram_ids, actor_id=admin.id)
    return RemoveSelectedOut(**result.__dict__)
