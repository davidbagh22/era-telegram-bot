from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative
from app.services.audit_service import audit
from app.services.authorization_service import can_manage_partners

router = APIRouter(prefix="/admin", tags=["admin-partners"])


async def require_partner_editor(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_partners(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="offer_reviewer_access_required")
    return user


class PartnerUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    source_url: str | None = Field(default=None, max_length=500)


class PartnerOut(BaseModel):
    id: int
    name: str
    description: str
    source_url: str | None
    is_active: bool
    is_archived: bool


class OfferUpdateIn(BaseModel):
    partner_id: int | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    point_cost: int | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=1)
    instruction: str | None = None
    source_url: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None


class OfferOut(BaseModel):
    id: int
    partner_id: int
    partner_name: str
    title: str
    description: str
    point_cost: int
    quantity: int | None
    expires_at: str | None
    instruction: str | None
    source_url: str | None
    is_active: bool
    is_archived: bool


def _partner_out(item: Partner) -> PartnerOut:
    return PartnerOut(
        id=item.id,
        name=item.name,
        description=item.description,
        source_url=item.source_url,
        is_active=item.is_active,
        is_archived=item.is_archived,
    )


async def _offer_out(session: AsyncSession, item: PartnerInitiative) -> OfferOut:
    partner = await session.get(Partner, item.partner_id)
    return OfferOut(
        id=item.id,
        partner_id=item.partner_id,
        partner_name=partner.name if partner else "Партнёр",
        title=item.title,
        description=item.description,
        point_cost=item.point_cost,
        quantity=item.quantity,
        expires_at=item.expires_at.isoformat() if item.expires_at else None,
        instruction=item.instruction,
        source_url=item.source_url,
        is_active=item.is_active,
        is_archived=item.is_archived,
    )


@router.patch("/partners/{partner_id}", response_model=PartnerOut)
async def update_partner(
    partner_id: int,
    payload: PartnerUpdateIn,
    actor: User = Depends(require_partner_editor),
    session: AsyncSession = Depends(get_session),
) -> PartnerOut:
    item = await session.get(Partner, partner_id)
    if item is None or item.is_archived:
        raise HTTPException(status_code=404, detail="partner_not_found")

    changes = payload.model_dump(exclude_unset=True)
    old = {key: getattr(item, key) for key in changes}
    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name_required")
        item.name = name
    if "description" in changes:
        description = (changes["description"] or "").strip()
        if not description:
            raise HTTPException(status_code=422, detail="description_required")
        item.description = description
    if "source_url" in changes:
        item.source_url = (changes["source_url"] or "").strip() or None

    await audit(
        session,
        actor_id=actor.id,
        action="partner.updated",
        entity_type="partner",
        entity_id=item.id,
        old_value=old,
        new_value={key: getattr(item, key) for key in changes},
    )
    await session.flush()
    return _partner_out(item)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
async def update_offer(
    offer_id: int,
    payload: OfferUpdateIn,
    actor: User = Depends(require_partner_editor),
    session: AsyncSession = Depends(get_session),
) -> OfferOut:
    item = await session.get(PartnerInitiative, offer_id)
    if item is None or item.is_archived:
        raise HTTPException(status_code=404, detail="opportunity_not_found")

    changes = payload.model_dump(exclude_unset=True)
    old = {key: getattr(item, key) for key in changes}

    if "partner_id" in changes:
        partner = await session.get(Partner, changes["partner_id"])
        if partner is None or partner.is_archived:
            raise HTTPException(status_code=422, detail="partner_not_found")
        item.partner_id = partner.id
    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="title_required")
        item.title = title
    if "description" in changes:
        description = (changes["description"] or "").strip()
        if not description:
            raise HTTPException(status_code=422, detail="description_required")
        item.description = description
    if "point_cost" in changes:
        item.point_cost = changes["point_cost"]
    if "quantity" in changes:
        item.quantity = changes["quantity"]
    if "instruction" in changes:
        item.instruction = (changes["instruction"] or "").strip() or None
    if "source_url" in changes:
        item.source_url = (changes["source_url"] or "").strip() or None
    if "expires_at" in changes:
        item.expires_at = changes["expires_at"]

    await audit(
        session,
        actor_id=actor.id,
        action="partner_offer.updated",
        entity_type="partner_initiative",
        entity_id=item.id,
        old_value={key: value.isoformat() if isinstance(value, datetime) else value for key, value in old.items()},
        new_value={
            key: (value.isoformat() if isinstance(value, datetime) else value)
            for key, value in ((key, getattr(item, key)) for key in changes)
        },
    )
    await session.flush()
    return await _offer_out(session, item)
