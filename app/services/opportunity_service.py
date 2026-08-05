from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.partners import (
    Partner,
    PartnerInitiative,
    PartnerOfferApplication,
    SavedOpportunity,
)
from app.services.points_service import add_points, total_points

OpportunityScope = Literal["for_me", "all", "saved", "mine"]
OFFER_APPLICATION_ACTIONS = ("approve", "reject")

ACTIVE_APPLICATION_STATUSES = {"pending", "approved"}


def _active_offer_filters(now: datetime):
    return (
        PartnerInitiative.is_active.is_(True),
        PartnerInitiative.is_archived.is_(False),
        Partner.is_active.is_(True),
        Partner.is_archived.is_(False),
        (PartnerInitiative.expires_at.is_(None) | (PartnerInitiative.expires_at >= now)),
    )


async def list_active_offers(session: AsyncSession) -> list[tuple[PartnerInitiative, Partner]]:
    """Mirrors app/handlers/participant/partner_offers_block16.py::offers_list —
    the shared source of truth for "what counts as an active offer"."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .where(*_active_offer_filters(now))
        .order_by(Partner.name, PartnerInitiative.title)
    )
    return list(result.all())


async def remaining_slots(session: AsyncSession, offer: PartnerInitiative) -> int | None:
    if offer.quantity is None:
        return None
    used = int(
        await session.scalar(
            select(func.count(PartnerOfferApplication.id)).where(
                PartnerOfferApplication.initiative_id == offer.id,
                PartnerOfferApplication.status.in_(ACTIVE_APPLICATION_STATUSES),
            )
        )
        or 0
    )
    return max(offer.quantity - used, 0)


async def get_application(
    session: AsyncSession, offer_id: int, user_id: int
) -> PartnerOfferApplication | None:
    return await session.scalar(
        select(PartnerOfferApplication).where(
            PartnerOfferApplication.initiative_id == offer_id,
            PartnerOfferApplication.user_id == user_id,
        )
    )


async def has_active_application(session: AsyncSession, offer_id: int, user_id: int) -> bool:
    application = await get_application(session, offer_id, user_id)
    return bool(application and application.status in ACTIVE_APPLICATION_STATUSES)


async def apply_to_offer(
    session: AsyncSession, offer: PartnerInitiative, user: User
) -> tuple[PartnerOfferApplication | None, str | None]:
    """Mirrors app/handlers/participant/partner_offers_block16.py::offer_apply.
    Points are only ever deducted on admin approval (Admin Mode, PR 7) —
    applying never touches the balance."""
    if not offer.is_active or offer.is_archived:
        return None, "offer_unavailable"
    existing = await get_application(session, offer.id, user.id)
    if existing and existing.status in ACTIVE_APPLICATION_STATUSES:
        return None, "already_applied"
    balance = await total_points(session, user.id)
    if balance < offer.point_cost:
        return None, "insufficient_points"
    slots = await remaining_slots(session, offer)
    if slots is not None and slots <= 0:
        return None, "no_slots"
    if existing:
        existing.status = "pending"
        existing.reviewed_by = None
        existing.admin_comment = None
        application = existing
    else:
        application = PartnerOfferApplication(initiative_id=offer.id, user_id=user.id, status="pending")
        session.add(application)
    await session.flush()
    return application, None


async def list_my_applications(
    session: AsyncSession, user: User
) -> list[tuple[PartnerOfferApplication, PartnerInitiative]]:
    result = await session.execute(
        select(PartnerOfferApplication, PartnerInitiative)
        .join(PartnerInitiative, PartnerInitiative.id == PartnerOfferApplication.initiative_id)
        .where(PartnerOfferApplication.user_id == user.id)
        .order_by(PartnerOfferApplication.created_at.desc())
    )
    return list(result.all())


async def is_saved(session: AsyncSession, offer_id: int, user_id: int) -> bool:
    saved = await session.scalar(
        select(SavedOpportunity).where(
            SavedOpportunity.initiative_id == offer_id, SavedOpportunity.user_id == user_id
        )
    )
    return saved is not None


async def save_offer(session: AsyncSession, offer_id: int, user_id: int) -> None:
    if await is_saved(session, offer_id, user_id):
        return
    session.add(SavedOpportunity(initiative_id=offer_id, user_id=user_id))
    await session.flush()


async def unsave_offer(session: AsyncSession, offer_id: int, user_id: int) -> None:
    saved = await session.scalar(
        select(SavedOpportunity).where(
            SavedOpportunity.initiative_id == offer_id, SavedOpportunity.user_id == user_id
        )
    )
    if saved is not None:
        await session.delete(saved)
        await session.flush()


async def list_saved_offers(
    session: AsyncSession, user: User
) -> list[tuple[PartnerInitiative, Partner]]:
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .join(SavedOpportunity, SavedOpportunity.initiative_id == PartnerInitiative.id)
        .where(SavedOpportunity.user_id == user.id)
        .order_by(SavedOpportunity.created_at.desc())
    )
    return list(result.all())


@dataclass(frozen=True)
class RecommendedOffer:
    offer: PartnerInitiative
    partner: Partner
    reasons: list[str]


async def recommended_offers(
    session: AsyncSession, user: User, *, limit: int = 5
) -> list[RecommendedOffer]:
    """"Подходит тебе" with real reasons only — no fabricated match
    percentage, no department/age/city targeting (PartnerInitiative has no
    such fields anywhere in the schema, so claiming that match would be
    fake). Only signals that are actually computable: affordable, has open
    slots, not already applied."""
    balance = await total_points(session, user.id)
    rows = await list_active_offers(session)
    recommended: list[RecommendedOffer] = []
    for offer, partner in rows:
        if await has_active_application(session, offer.id, user.id):
            continue
        reasons: list[str] = []
        if offer.point_cost <= balance:
            reasons.append("доступно по вашему балансу баллов")
        else:
            continue
        slots = await remaining_slots(session, offer)
        if slots is None:
            reasons.append("без ограничения по местам")
        elif slots > 0:
            reasons.append(f"свободных мест: {slots}")
        else:
            continue
        recommended.append(RecommendedOffer(offer=offer, partner=partner, reasons=reasons))
        if len(recommended) >= limit:
            break
    return recommended


@dataclass(frozen=True)
class OfferApplicationResult:
    application: PartnerOfferApplication
    admin_notice: str
    participant_notice: str | None
    points_charged: int


async def list_pending_offer_applications(
    session: AsyncSession,
) -> list[PartnerOfferApplication]:
    rows = await session.scalars(
        select(PartnerOfferApplication)
        .where(PartnerOfferApplication.status == "pending")
        .order_by(PartnerOfferApplication.created_at)
    )
    return list(rows.all())


async def decide_offer_application(
    session: AsyncSession,
    application: PartnerOfferApplication,
    offer: PartnerInitiative,
    participant: User,
    *,
    action: str,
    actor: User,
) -> OfferApplicationResult:
    if action not in OFFER_APPLICATION_ACTIONS:
        raise ValueError(f"unknown offer application action: {action!r}")
    if application.status != "pending":
        return OfferApplicationResult(
            application=application,
            admin_notice="Заявка уже обработана.",
            participant_notice=None,
            points_charged=0,
        )

    if action == "approve":
        balance = await total_points(session, participant.id)
        if balance < offer.point_cost:
            return OfferApplicationResult(
                application=application,
                admin_notice="У участника уже недостаточно баллов. Заявка не одобрена.",
                participant_notice=None,
                points_charged=0,
            )
        if offer.point_cost:
            await add_points(
                session,
                user_id=participant.id,
                points=-offer.point_cost,
                reason=f"Партнёрское предложение: {offer.title}",
                approved_by=actor.id,
                source_type="partner_offer",
                source_id=application.id,
                idempotency_key=f"partner_offer:{application.id}:approval",
            )
        application.status = "approved"
        application.reviewed_by = actor.id
        return OfferApplicationResult(
            application=application,
            admin_notice="Заявка одобрена. Баллы списаны один раз.",
            participant_notice=(
                f"Ваша заявка «{offer.title}» одобрена. Списано: {offer.point_cost} баллов. "
                "Команда ЭРА свяжется с Вами."
            ),
            points_charged=offer.point_cost,
        )

    application.status = "rejected"
    application.reviewed_by = actor.id
    return OfferApplicationResult(
        application=application,
        admin_notice="Заявка отклонена. Баллы не списаны.",
        participant_notice=f"Заявка «{offer.title}» отклонена. Баллы не списаны.",
        points_charged=0,
    )
