from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative
from app.services import opportunity_service
from app.services.notification_service import notify_admins
from app.services.opportunity_service import OpportunityScope

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class EligibilityCheckOut(BaseModel):
    key: str
    label: str
    required: str
    current: str
    ok: bool


class OpportunityOut(BaseModel):
    id: int
    partner_name: str
    title: str
    description: str
    # point_cost stays in the wire contract for existing clients. For
    # certificate/letter it is a threshold, not a spendable price.
    point_cost: int
    required_points: int
    opportunity_type: str
    min_rank: str | None
    eligible: bool
    eligibility_checks: list[EligibilityCheckOut] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    default_award_wording: str | None
    partner_review_required: bool
    remaining_slots: str
    expires_at: str | None
    instruction: str | None
    source_url: str | None
    application_status: str | None
    is_saved: bool
    reasons: list[str] = Field(default_factory=list)


class ApplicationOut(BaseModel):
    initiative_id: int
    title: str
    status: str


async def _to_opportunity_out(
    session: AsyncSession,
    offer: PartnerInitiative,
    partner: Partner,
    user: User,
    *,
    reasons: list[str] | None = None,
) -> OpportunityOut:
    application = await opportunity_service.get_application(session, offer.id, user.id)
    slots = await opportunity_service.remaining_slots(session, offer)
    eligibility = await opportunity_service.evaluate_eligibility(session, offer, user)
    return OpportunityOut(
        id=offer.id,
        partner_name=partner.name,
        title=offer.title,
        description=offer.description,
        point_cost=offer.point_cost,
        required_points=offer.point_cost,
        opportunity_type=offer.opportunity_type,
        min_rank=offer.min_rank,
        eligible=eligibility.eligible and (slots is None or slots > 0),
        eligibility_checks=[
            EligibilityCheckOut(**check.as_dict()) for check in eligibility.checks
        ],
        missing_requirements=eligibility.missing,
        default_award_wording=offer.default_award_wording,
        partner_review_required=offer.partner_review_required,
        remaining_slots="unlimited" if slots is None else str(slots),
        expires_at=offer.expires_at.isoformat() if offer.expires_at else None,
        instruction=offer.instruction,
        source_url=offer.source_url,
        application_status=application.status if application else None,
        is_saved=await opportunity_service.is_saved(session, offer.id, user.id),
        reasons=reasons or [],
    )


@router.get("", response_model=list[OpportunityOut])
async def read_opportunities(
    scope: OpportunityScope = Query("for_me"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[OpportunityOut]:
    if scope == "saved":
        rows = await opportunity_service.list_saved_offers(session, user)
        return [
            await _to_opportunity_out(session, offer, partner, user)
            for offer, partner in rows
        ]

    if scope == "mine":
        applications = await opportunity_service.list_my_applications(session, user)
        out: list[OpportunityOut] = []
        for _, offer in applications:
            partner = await session.get(Partner, offer.partner_id)
            if partner is not None:
                out.append(await _to_opportunity_out(session, offer, partner, user))
        return out

    if scope == "for_me":
        recommended = await opportunity_service.recommended_offers(session, user)
        return [
            await _to_opportunity_out(
                session,
                item.offer,
                item.partner,
                user,
                reasons=item.reasons,
            )
            for item in recommended
        ]

    rows = await opportunity_service.list_active_offers(session)
    return [
        await _to_opportunity_out(session, offer, partner, user)
        for offer, partner in rows
    ]


@router.get("/{offer_id}", response_model=OpportunityOut)
async def read_opportunity(
    offer_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    offer = await session.get(PartnerInitiative, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    partner = await session.get(Partner, offer.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    return await _to_opportunity_out(session, offer, partner, user)


@router.post("/{offer_id}/apply", response_model=OpportunityOut)
async def apply_opportunity(
    offer_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> OpportunityOut:
    offer = await session.get(PartnerInitiative, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    partner = await session.get(Partner, offer.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    application, error = await opportunity_service.apply_to_offer(session, offer, user)
    if error == "offer_unavailable":
        raise HTTPException(status_code=409, detail="offer_unavailable")
    if error == "already_applied":
        raise HTTPException(status_code=409, detail="already_applied")
    if error == "insufficient_points":
        raise HTTPException(status_code=409, detail="insufficient_points")
    if error == "not_eligible":
        raise HTTPException(status_code=409, detail="not_eligible")
    if error == "no_slots":
        raise HTTPException(status_code=409, detail="no_slots")

    if bot is not None and application is not None:
        if opportunity_service.is_recognition(offer):
            eligibility = await opportunity_service.evaluate_eligibility(
                session, offer, user
            )
            notice = (
                "Новая заявка на документ\n\n"
                f"Получатель: {user.first_name} {user.last_name or ''}\n"
                f"Ранг: {eligibility.rank}\n"
                f"Баллы: {eligibility.points}\n"
                f"Организация: {partner.name}\n"
                f"Документ: «{offer.title}»\n\n"
                f"Основание: {application.basis_text or eligibility.basis}\n\n"
                f"Текст для документа: {application.award_wording or offer.default_award_wording or '—'}"
            )
        else:
            notice = (
                "Новая заявка на партнёрское предложение\n\n"
                f"{offer.title}\n"
                f"Участник: {user.first_name} {user.last_name or ''}\n"
                f"Баллы: {offer.point_cost}"
            )
        await notify_admins(bot, settings, notice)
    return await _to_opportunity_out(session, offer, partner, user)


@router.post("/{offer_id}/save", response_model=OpportunityOut)
async def save_opportunity(
    offer_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    offer = await session.get(PartnerInitiative, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    partner = await session.get(Partner, offer.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    await opportunity_service.save_offer(session, offer_id, user.id)
    return await _to_opportunity_out(session, offer, partner, user)


@router.post("/{offer_id}/unsave", response_model=OpportunityOut)
async def unsave_opportunity(
    offer_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    offer = await session.get(PartnerInitiative, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    partner = await session.get(Partner, offer.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    await opportunity_service.unsave_offer(session, offer_id, user.id)
    return await _to_opportunity_out(session, offer, partner, user)
