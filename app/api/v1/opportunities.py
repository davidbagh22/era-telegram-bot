from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative
from app.services import opportunity_service
from app.services.notification_service import notify_admins
from app.services.opportunity_service import OpportunityScope

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class OpportunityOut(BaseModel):
    id: int
    partner_name: str
    title: str
    description: str
    point_cost: int
    remaining_slots: str
    expires_at: str | None
    instruction: str | None
    source_url: str | None
    application_status: str | None
    is_saved: bool
    reasons: list[str] = []


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
    return OpportunityOut(
        id=offer.id,
        partner_name=partner.name,
        title=offer.title,
        description=offer.description,
        point_cost=offer.point_cost,
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
        return [await _to_opportunity_out(session, offer, partner, user) for offer, partner in rows]

    if scope == "mine":
        applications = await opportunity_service.list_my_applications(session, user)
        out: list[OpportunityOut] = []
        for _, offer in applications:
            partner = await session.get(Partner, offer.partner_id)
            out.append(await _to_opportunity_out(session, offer, partner, user))
        return out

    if scope == "for_me":
        recommended = await opportunity_service.recommended_offers(session, user)
        return [
            await _to_opportunity_out(session, item.offer, item.partner, user, reasons=item.reasons)
            for item in recommended
        ]

    rows = await opportunity_service.list_active_offers(session)
    return [await _to_opportunity_out(session, offer, partner, user) for offer, partner in rows]


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
    _, error = await opportunity_service.apply_to_offer(session, offer, user)
    if error == "offer_unavailable":
        raise HTTPException(status_code=409, detail="offer_unavailable")
    if error == "already_applied":
        raise HTTPException(status_code=409, detail="already_applied")
    if error == "insufficient_points":
        raise HTTPException(status_code=409, detail="insufficient_points")
    if error == "no_slots":
        raise HTTPException(status_code=409, detail="no_slots")
    if bot is not None:
        await notify_admins(
            bot,
            settings,
            f"Новая заявка на партнёрское предложение\n\n{offer.title}\n"
            f"Участник: {user.first_name} {user.last_name or ''}\n"
            f"Стоимость: {offer.point_cost} баллов",
        )
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
    await opportunity_service.unsave_offer(session, offer_id, user.id)
    return await _to_opportunity_out(session, offer, partner, user)
