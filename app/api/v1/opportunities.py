from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

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
from app.services.points_service import total_points

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

OpportunityState = Literal["available", "almost", "closed", "requested", "review", "issued"]
OpportunitySort = Literal["closing_soon", "newest", "by_organization"]
OpportunityDisplayState = Literal["locked", "almost", "available", "new"]
NEW_OPPORTUNITY_WINDOW = timedelta(days=7)

_REQUESTED_STATUSES = {"pending", "requested"}
_REVIEW_STATUSES = {"under_review", "needs_info", "partner_review", "approved"}


class FacetsOut(BaseModel):
    issuers: list[str]
    types: list[str]
    categories: list[str]


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
    category: str | None
    min_rank: str | None
    eligible: bool
    display_state: OpportunityDisplayState
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
    is_offer_open: bool
    state: OpportunityState


class ApplicationOut(BaseModel):
    initiative_id: int
    title: str
    status: str


def _is_recognition_offer(offer: PartnerInitiative) -> bool:
    # Existing partner opportunities predate opportunity_type. Treat absent
    # metadata as the legacy external kind; recognition remains opt-in only.
    return getattr(offer, "opportunity_type", "external") in {"certificate", "letter"}


def _is_offer_open(offer: PartnerInitiative, slots: int | None, now: datetime) -> bool:
    if not offer.is_active or offer.is_archived:
        return False
    if offer.expires_at and offer.expires_at < now:
        return False
    if slots is not None and slots <= 0:
        return False
    return True


def _compute_state(
    *,
    offer_open: bool,
    application_status: str | None,
    eligible: bool,
    missing_requirements: list[str],
) -> OpportunityState:
    """DELTA ToR §16-17's Статус facet. Application status wins whenever
    present -- what happened to *your* request matters more than the
    offer's current eligibility once you've already applied."""
    if application_status == "issued":
        return "issued"
    if application_status in _REQUESTED_STATUSES:
        return "requested"
    if application_status in _REVIEW_STATUSES:
        return "review"
    if eligible:
        return "available" if offer_open else "closed"
    # "Почти доступно": not eligible yet, but only one requirement stands
    # between the participant and it -- a real, non-fabricated closeness
    # signal computed from the same eligibility_checks the card already
    # shows, not an invented number. Everything else (offer genuinely
    # closed, or open but too far to matter right now) collapses into
    # "closed" -- the ToR's Статус facet has no separate bucket for "open,
    # but not realistically actionable yet".
    if offer_open and len(missing_requirements) <= 1:
        return "almost"
    return "closed"


def _is_recent_offer(offer: PartnerInitiative) -> bool:
    created_at = getattr(offer, "created_at", None)
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - created_at
    return timedelta(0) <= age <= NEW_OPPORTUNITY_WINDOW


def _display_state(
    offer: PartnerInitiative,
    *,
    eligible: bool,
    missing_requirements: list[str],
) -> OpportunityDisplayState:
    if not eligible:
        # "Almost" is intentionally strict: the user is one concrete
        # recognition requirement away. External offers can be arbitrarily
        # far from their points threshold, so they remain locked until the
        # existing redemption contract says they are actually available.
        if _is_recognition_offer(offer) and len(missing_requirements) == 1:
            return "almost"
        return "locked"
    if _is_recent_offer(offer):
        return "new"
    return "available"


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
    recognition = _is_recognition_offer(offer)

    eligibility_checks: list[EligibilityCheckOut] = []
    missing_requirements: list[str] = []
    # Strict rank/metric/document eligibility belongs only to recognition
    # documents. Legacy external offers keep their old redemption contract;
    # the display state mirrors the same points + slots checks used by
    # apply_to_offer so the UI never says "available" and then rejects for
    # insufficient points.
    if recognition:
        eligibility = await opportunity_service.evaluate_eligibility(session, offer, user)
        eligible = eligibility.eligible and (slots is None or slots > 0)
        eligibility_checks = [
            EligibilityCheckOut(**check.as_dict()) for check in eligibility.checks
        ]
        missing_requirements = eligibility.missing
        if slots is not None and slots <= 0:
            missing_requirements = [*missing_requirements, "Свободные места"]
    else:
        balance = await total_points(session, user.id)
        has_points = balance >= max(0, int(offer.point_cost or 0))
        has_slots = slots is None or slots > 0
        eligible = has_points and has_slots
        if not has_points:
            missing_requirements.append("Баллы")
        if not has_slots:
            missing_requirements.append("Свободные места")

    offer_open = _is_offer_open(offer, slots, datetime.now(timezone.utc))
    state = _compute_state(
        offer_open=offer_open,
        application_status=application.status if application else None,
        eligible=eligible,
        missing_requirements=missing_requirements,
    )

    return OpportunityOut(
        id=offer.id,
        partner_name=partner.name,
        title=offer.title,
        description=offer.description,
        point_cost=offer.point_cost,
        required_points=offer.point_cost,
        opportunity_type=getattr(offer, "opportunity_type", "external"),
        category=getattr(offer, "category", None),
        min_rank=getattr(offer, "min_rank", None),
        eligible=eligible,
        display_state=_display_state(
            offer,
            eligible=eligible,
            missing_requirements=missing_requirements,
        ),
        eligibility_checks=eligibility_checks,
        missing_requirements=missing_requirements,
        default_award_wording=getattr(offer, "default_award_wording", None),
        partner_review_required=bool(getattr(offer, "partner_review_required", False)),
        remaining_slots="unlimited" if slots is None else str(slots),
        expires_at=offer.expires_at.isoformat() if offer.expires_at else None,
        instruction=offer.instruction,
        source_url=offer.source_url,
        application_status=application.status if application else None,
        is_saved=await opportunity_service.is_saved(session, offer.id, user.id),
        reasons=reasons or [],
        is_offer_open=offer_open,
        state=state,
    )


def _matches_facets(
    offer: PartnerInitiative,
    partner: Partner,
    *,
    issuer: str | None,
    otype: str | None,
    category: str | None,
) -> bool:
    if issuer and partner.name != issuer:
        return False
    if otype and getattr(offer, "opportunity_type", "external") != otype:
        return False
    if category and getattr(offer, "category", None) != category:
        return False
    return True


_SORT_KEYS = {
    "closing_soon": lambda item: (item.expires_at is None, item.expires_at or ""),
    "newest": lambda item: item.id,
    "by_organization": lambda item: (item.partner_name, item.title),
}


def _sort_opportunities(items: list[OpportunityOut], sort: OpportunitySort) -> list[OpportunityOut]:
    if sort == "newest":
        return sorted(items, key=_SORT_KEYS["newest"], reverse=True)
    return sorted(items, key=_SORT_KEYS[sort])


@router.get("/facets", response_model=FacetsOut)
async def read_opportunity_facets(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FacetsOut:
    return FacetsOut(**await opportunity_service.list_offer_facets(session))


@router.get("", response_model=list[OpportunityOut])
async def read_opportunities(
    scope: OpportunityScope = Query("for_me"),
    issuer: str | None = Query(None),
    type: str | None = Query(None),  # noqa: A002 -- matches the ToR's own param name
    category: str | None = Query(None),
    state: OpportunityState | None = Query(None),
    sort: OpportunitySort = Query("closing_soon"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[OpportunityOut]:
    """DELTA ToR §16-17: scope stays the top-level "Для тебя/Все/Сохранённые/
    Мои заявки" switch; issuer/type/category/state/sort are the real filter
    sheet layered on top of whichever scope is active, all resolved
    server-side so the result set actually matches what was asked for."""
    out: list[OpportunityOut] = []

    if scope == "saved":
        rows = await opportunity_service.list_saved_offers(session, user)
        rows = [r for r in rows if _matches_facets(*r, issuer=issuer, otype=type, category=category)]
        out = [await _to_opportunity_out(session, offer, partner, user) for offer, partner in rows]
    elif scope == "mine":
        applications = await opportunity_service.list_my_applications(session, user)
        for _, offer in applications:
            partner = await session.get(Partner, offer.partner_id)
            if partner is None or not _matches_facets(offer, partner, issuer=issuer, otype=type, category=category):
                continue
            out.append(await _to_opportunity_out(session, offer, partner, user))
    elif scope == "for_me":
        recommended = await opportunity_service.recommended_offers(session, user)
        recommended = [
            item for item in recommended
            if _matches_facets(item.offer, item.partner, issuer=issuer, otype=type, category=category)
        ]
        out = [
            await _to_opportunity_out(session, item.offer, item.partner, user, reasons=item.reasons)
            for item in recommended
        ]
    else:
        # "closed" has nothing to show from the active-only catalog --
        # only fetch inactive/expired/archived rows when someone actually
        # asked for that state, so the common case stays a cheap query.
        rows = (
            await opportunity_service.list_all_offers(session)
            if state == "closed"
            else await opportunity_service.list_active_offers(session)
        )
        rows = [r for r in rows if _matches_facets(*r, issuer=issuer, otype=type, category=category)]
        out = [await _to_opportunity_out(session, offer, partner, user) for offer, partner in rows]

    if state:
        out = [item for item in out if item.state == state]
    return _sort_opportunities(out, sort)


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
        if _is_recognition_offer(offer):
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
                f"Текст для документа: {application.award_wording or getattr(offer, 'default_award_wording', None) or '—'}"
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
