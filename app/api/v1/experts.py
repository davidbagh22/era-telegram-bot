"""Expert platform API (#616 first slice).

Fail-closed when experts_platform_enabled is False. Draft profiles and
suggestion contacts never appear in participant/public responses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.api.security import InitDataError, verify_init_data
from app.api.v1.admin_executive_export import require_admin
from app.config import Settings
from app.database.models import User
from app.services import expert_platform_service as experts
from app.services.expert_platform_service import ExpertPlatformError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experts", tags=["experts"])


def require_experts_platform(settings: Settings = Depends(get_settings)) -> None:
    if not getattr(settings, "experts_platform_enabled", False):
        # Treat disabled module as absent — do not leak route existence.
        raise HTTPException(status_code=404, detail="feature_unavailable")


class CreateInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="profile", max_length=32)
    ttl_hours: int = Field(default=72, ge=1, le=24 * 30)
    title: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    bio_short: str | None = Field(default=None, max_length=500)
    topics: str | None = Field(default=None, max_length=2000)
    suggestion_id: int | None = Field(default=None, ge=1)
    audit_note: str | None = Field(default=None, max_length=500)
    mark_sent: bool = False


class CreateInviteOut(BaseModel):
    invite_id: int
    token: str
    purpose: str
    state: str
    expires_at: str
    expert_profile_id: int
    profile_status: str


class ClaimInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    token: str = Field(min_length=8, max_length=200)
    init_data: str = Field(default="", alias="initData", max_length=16_384)
    # Local/E2E only when settings.dev_auth_enabled; ignored otherwise.
    dev_telegram_id: int | None = Field(default=None, alias="devTelegramId")


class ClaimInviteOut(BaseModel):
    invite_id: int
    state: str
    purpose: str
    expert_profile_id: int
    profile_status: str
    claimed_telegram_id: int
    era_membership_required: bool = False


class SuggestExpertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expert_name: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=200)
    why_interesting: str = Field(min_length=1, max_length=4000)
    contact_private: str = Field(min_length=1, max_length=500)
    consent_given: bool
    links: str | None = Field(default=None, max_length=2000)


class SuggestExpertOut(BaseModel):
    id: int
    expert_name: str
    field: str
    status: str
    submitted_at: str | None


class PublishedExpertOut(BaseModel):
    id: int
    display_name: str
    title: str | None
    organization: str | None
    bio_short: str | None
    topics: str | None
    published_at: str | None


def _map_error(exc: ExpertPlatformError) -> HTTPException:
    code = str(exc)
    if code in {"invite_unavailable", "profile_not_found", "suggestion_not_found", "invite_not_found"}:
        return HTTPException(status_code=404, detail=code)
    if code in {"suggestion_rate_limited"}:
        return HTTPException(status_code=429, detail=code)
    if code in {"consent_required", "invite_already_claimed"}:
        return HTTPException(status_code=403, detail=code)
    return HTTPException(status_code=400, detail=code)


@router.get("", response_model=list[PublishedExpertOut])
async def list_experts(
    _gate: None = Depends(require_experts_platform),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PublishedExpertOut]:
    del user  # authenticated Mini App session required; listing is published-only
    profiles = await experts.list_published_experts(session, limit=limit, offset=offset)
    return [PublishedExpertOut(**experts.serialize_published_expert(p)) for p in profiles]


@router.get("/{expert_id}", response_model=PublishedExpertOut)
async def get_expert(
    expert_id: int,
    _gate: None = Depends(require_experts_platform),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PublishedExpertOut:
    del user
    profile = await experts.get_published_expert(session, expert_id)
    if profile is None:
        # Drafts and missing IDs share the same 404 — no existence oracle.
        raise HTTPException(status_code=404, detail="expert_not_found")
    return PublishedExpertOut(**experts.serialize_published_expert(profile))


@router.post("/invites", response_model=CreateInviteOut)
async def create_invite(
    payload: CreateInviteIn,
    _gate: None = Depends(require_experts_platform),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CreateInviteOut:
    try:
        created = await experts.create_invite(
            session,
            admin=admin,
            display_name=payload.display_name,
            purpose=payload.purpose,
            ttl_hours=payload.ttl_hours,
            title=payload.title,
            organization=payload.organization,
            bio_short=payload.bio_short,
            topics=payload.topics,
            suggestion_id=payload.suggestion_id,
            audit_note=payload.audit_note,
            mark_sent=payload.mark_sent,
        )
    except ExpertPlatformError as exc:
        raise _map_error(exc) from exc
    return CreateInviteOut(
        invite_id=created.invite.id,
        token=created.token,
        purpose=created.invite.purpose,
        state=created.invite.state,
        expires_at=created.invite.expires_at.isoformat(),
        expert_profile_id=created.profile.id,
        profile_status=created.profile.status,
    )


@router.post("/invites/claim", response_model=ClaimInviteOut)
async def claim_invite(
    request: Request,
    payload: ClaimInviteIn,
    _gate: None = Depends(require_experts_platform),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ClaimInviteOut:
    """Claim via Telegram initData — ERA membership is not required to start."""

    await enforce_rate_limit(
        request,
        key_prefix="expert_invite_claim",
        limit=30,
        window_seconds=60,
    )
    if settings.dev_auth_enabled and payload.dev_telegram_id is not None:
        telegram_id = payload.dev_telegram_id
    else:
        try:
            verified = verify_init_data(
                payload.init_data,
                bot_token=settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except InitDataError as exc:
            logger.warning("expert invite claim rejected: %s", exc)
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        telegram_id = verified.telegram_id

    try:
        invite, profile = await experts.claim_invite(
            session, token=payload.token, telegram_id=telegram_id
        )
    except ExpertPlatformError as exc:
        raise _map_error(exc) from exc

    return ClaimInviteOut(
        invite_id=invite.id,
        state=invite.state,
        purpose=invite.purpose,
        expert_profile_id=profile.id,
        profile_status=profile.status,
        claimed_telegram_id=telegram_id,
        era_membership_required=False,
    )


@router.post("/suggestions", response_model=SuggestExpertOut)
async def suggest_expert(
    request: Request,
    payload: SuggestExpertIn,
    _gate: None = Depends(require_experts_platform),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SuggestExpertOut:
    await enforce_rate_limit(
        request,
        key_prefix=f"expert_suggest_{user.id}",
        limit=10,
        window_seconds=60,
    )
    try:
        suggestion = await experts.suggest_expert(
            session,
            nominator=user,
            expert_name=payload.expert_name,
            field=payload.field,
            why_interesting=payload.why_interesting,
            contact_private=payload.contact_private,
            consent_given=payload.consent_given,
            links=payload.links,
        )
    except ExpertPlatformError as exc:
        raise _map_error(exc) from exc
    ack = experts.serialize_suggestion_ack(suggestion)
    # Hard guarantee: private contact never leaves this handler.
    if "contact_private" in ack:
        raise HTTPException(status_code=500, detail="suggestion_serialization_error")
    return SuggestExpertOut(**ack)
