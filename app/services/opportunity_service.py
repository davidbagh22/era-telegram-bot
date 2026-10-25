from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PortfolioItem, User
from app.database.partners import (
    Partner,
    PartnerInitiative,
    PartnerOfferApplication,
    SavedOpportunity,
)
from app.services.activity_metrics_service import get_all_metrics
from app.services.points_service import add_points, add_portfolio_item, total_points
from app.services.progression_service import RANK_ORDER
from app.utils.constants import STATUS_LABELS, ParticipationStatus

OpportunityScope = Literal["for_me", "all", "saved", "mine"]
OFFER_APPLICATION_ACTIONS = (
    "approve",
    "reject",
    "needs_info",
    "partner_approve",
    "issue",
)

ACTIVE_APPLICATION_STATUSES = {
    "pending",
    "requested",
    "under_review",
    "needs_info",
    "partner_review",
    "approved",
    "issued",
}
REVIEW_QUEUE_STATUSES = {
    "pending",
    "requested",
    "under_review",
    "needs_info",
    "partner_review",
}
RECOGNITION_TYPES = {"certificate", "letter"}

METRIC_LABELS = {
    "events_attended": "подтверждённых посещений",
    "events_organized": "организованных мероприятий",
    "events_coordinated": "координаций мероприятий",
    "tasks_completed": "выполненных задач",
    "project_activities": "проектных активностей",
    "project_contributions": "подтверждённых вкладов в проекты",
    "project_milestones": "закрытых этапов проектов",
    "projects_completed": "завершённых проектов",
    "projects_led": "проектов в роли лидера",
    "volunteer_hours": "часов волонтёрства",
    "volunteer_activities": "волонтёрских активностей",
    "social_activities": "общественных активностей",
    "media_activities": "медиа-активностей",
    "culture_activities": "культурных активностей",
    "partner_activities": "партнёрских активностей",
    "leadership_activities": "лидерских активностей",
    "mentorship_activities": "активностей наставничества",
    "mentorship_outcomes": "подтверждённых результатов наставничества",
    "house_moscow_activities": "активностей, связанных с Домом Москвы",
    "ksoors_activities": "активностей, связанных с КСООРС Армении",
    "student_association_activities": "активностей студенческой ассоциации",
}


def is_recognition(offer: PartnerInitiative) -> bool:
    return offer.opportunity_type in RECOGNITION_TYPES


def _active_offer_filters(now: datetime):
    return (
        PartnerInitiative.is_active.is_(True),
        PartnerInitiative.is_archived.is_(False),
        Partner.is_active.is_(True),
        Partner.is_archived.is_(False),
        (PartnerInitiative.expires_at.is_(None) | (PartnerInitiative.expires_at >= now)),
    )


async def list_partners(session: AsyncSession, *, include_archived: bool = False) -> list[Partner]:
    conditions = [] if include_archived else [Partner.is_archived.is_(False)]
    return list(
        (await session.scalars(select(Partner).where(*conditions).order_by(Partner.name))).all()
    )


async def create_partner(
    session: AsyncSession,
    *,
    name: str,
    description: str,
    source_url: str | None,
    created_by_id: int | None,
) -> Partner:
    partner = Partner(
        name=name,
        description=description,
        source_url=source_url,
        created_by=created_by_id,
    )
    session.add(partner)
    await session.flush()
    return partner


def set_partner_active(partner: Partner, active: bool) -> None:
    partner.is_active = active


def archive_partner(partner: Partner) -> None:
    partner.is_active = False
    partner.is_archived = True


async def list_offers_admin(
    session: AsyncSession, *, include_archived: bool = False
) -> list[tuple[PartnerInitiative, Partner]]:
    conditions = [] if include_archived else [PartnerInitiative.is_archived.is_(False)]
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .where(*conditions)
        .order_by(Partner.name, PartnerInitiative.title)
    )
    return list(result.all())


async def get_offer_with_partner(
    session: AsyncSession, offer_id: int
) -> tuple[PartnerInitiative, Partner] | None:
    offer = await session.get(PartnerInitiative, offer_id)
    if offer is None:
        return None
    partner = await session.get(Partner, offer.partner_id)
    if partner is None:
        return None
    return offer, partner


async def create_offer(
    session: AsyncSession,
    *,
    partner_id: int,
    title: str,
    description: str,
    point_cost: int,
    quantity: int | None,
    expires_at: datetime | None,
    instruction: str | None,
    source_url: str | None,
) -> PartnerInitiative:
    # Legacy external opportunity creator. Recognition catalog entries are
    # seeded/configured separately and never reinterpret arbitrary external
    # offers as certificates.
    offer = PartnerInitiative(
        partner_id=partner_id,
        title=title,
        description=description,
        point_cost=point_cost,
        quantity=quantity,
        expires_at=expires_at,
        instruction=instruction,
        source_url=source_url,
        opportunity_type="external",
        is_active=True,
        is_archived=False,
    )
    session.add(offer)
    await session.flush()
    return offer


def set_offer_active(offer: PartnerInitiative, active: bool) -> None:
    offer.is_active = active


def archive_offer(offer: PartnerInitiative) -> None:
    offer.is_active = False
    offer.is_archived = True


async def list_active_offers(session: AsyncSession) -> list[tuple[PartnerInitiative, Partner]]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .where(*_active_offer_filters(now))
        .order_by(Partner.name, PartnerInitiative.point_cost, PartnerInitiative.title)
    )
    return list(result.all())


async def list_all_offers(session: AsyncSession) -> list[tuple[PartnerInitiative, Partner]]:
    """Like list_active_offers but also returns inactive/archived/expired
    offers -- needed for the DELTA ToR §16 "Закрыто" state filter, which
    would otherwise never have anything to show."""
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .order_by(Partner.name, PartnerInitiative.point_cost, PartnerInitiative.title)
    )
    return list(result.all())


async def list_offer_facets(session: AsyncSession) -> dict[str, list[str]]:
    """DELTA ToR §16-17 filter sheet options, sourced from what's actually
    in the catalog rather than hardcoded -- an issuer with zero offers
    (e.g. a stale legacy Partner row) never shows up as a choice."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(Partner.name, PartnerInitiative.opportunity_type, PartnerInitiative.category)
            .join(Partner, Partner.id == PartnerInitiative.partner_id)
            .where(*_active_offer_filters(now))
        )
    ).all()
    issuers = sorted({name for name, _, _ in rows})
    types_ = sorted({otype for _, otype, _ in rows})
    categories = sorted({category for _, _, category in rows if category})
    return {"issuers": issuers, "types": types_, "categories": categories}


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


@dataclass(frozen=True)
class EligibilityCheck:
    key: str
    label: str
    required: str
    current: str
    ok: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "key": self.key,
            "label": self.label,
            "required": self.required,
            "current": self.current,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class OpportunityEligibility:
    eligible: bool
    points: int
    rank: str
    checks: list[EligibilityCheck]
    missing: list[str]
    basis: str

    def snapshot(self) -> dict:
        return {
            "eligible": self.eligible,
            "points": self.points,
            "rank": self.rank,
            "checks": [check.as_dict() for check in self.checks],
            "missing": list(self.missing),
        }


def _rank_index(value: str | None) -> int:
    if not value:
        return 0
    try:
        return RANK_ORDER.index(ParticipationStatus(value))
    except (ValueError, TypeError):
        return 0


async def _has_any_document(
    session: AsyncSession, user_id: int, titles: list[str]
) -> tuple[bool, str | None]:
    if not titles:
        return True, None
    title = await session.scalar(
        select(PortfolioItem.title).where(
            PortfolioItem.user_id == user_id,
            PortfolioItem.status == "verified",
            PortfolioItem.title.in_(titles),
        )
    )
    return title is not None, title


async def evaluate_eligibility(
    session: AsyncSession, offer: PartnerInitiative, user: User
) -> OpportunityEligibility:
    points = await total_points(session, user.id)
    metrics = await get_all_metrics(session, user_id=user.id)
    checks: list[EligibilityCheck] = []

    points_ok = points >= max(0, int(offer.point_cost or 0))
    checks.append(
        EligibilityCheck(
            key="points",
            label="Баллы",
            required=str(max(0, int(offer.point_cost or 0))),
            current=str(points),
            ok=points_ok,
        )
    )

    if offer.min_rank:
        current_rank = user.participation_status or ParticipationStatus.NEW_MEMBER
        rank_ok = _rank_index(current_rank) >= _rank_index(offer.min_rank)
        checks.append(
            EligibilityCheck(
                key="rank",
                label="Ранг",
                required=STATUS_LABELS.get(offer.min_rank, str(offer.min_rank)),
                current=STATUS_LABELS.get(current_rank, str(current_rank)),
                ok=rank_ok,
            )
        )

    rules = offer.eligibility_json or {}
    for metric_key, required_value in (rules.get("required_metrics") or {}).items():
        required_int = max(0, int(required_value or 0))
        current_int = max(0, int(metrics.get(metric_key, 0) or 0))
        checks.append(
            EligibilityCheck(
                key=f"metric:{metric_key}",
                label=METRIC_LABELS.get(metric_key, metric_key),
                required=str(required_int),
                current=str(current_int),
                ok=current_int >= required_int,
            )
        )

    alternatives = rules.get("required_any_metrics") or []
    if alternatives:
        alternative_results: list[tuple[bool, str]] = []
        for group in alternatives:
            parts: list[str] = []
            group_ok = True
            for metric_key, required_value in group.items():
                required_int = max(0, int(required_value or 0))
                current_int = max(0, int(metrics.get(metric_key, 0) or 0))
                group_ok = group_ok and current_int >= required_int
                parts.append(
                    f"{METRIC_LABELS.get(metric_key, metric_key)}: {current_int}/{required_int}"
                )
            alternative_results.append((group_ok, ", ".join(parts)))
        checks.append(
            EligibilityCheck(
                key="metric:any",
                label="Профиль подтверждённой деятельности",
                required="выполнить один из вариантов",
                current="; ".join(text for _, text in alternative_results),
                ok=any(ok for ok, _ in alternative_results),
            )
        )

    document_titles = [str(value) for value in (rules.get("required_any_documents") or [])]
    if document_titles:
        document_ok, found_title = await _has_any_document(session, user.id, document_titles)
        checks.append(
            EligibilityCheck(
                key="prerequisite_document",
                label="Предыдущий документ",
                required="один из: " + "; ".join(document_titles),
                current=found_title or "нет",
                ok=document_ok,
            )
        )

    missing = [check.label for check in checks if not check.ok]
    satisfied_facts = [
        f"{check.label}: {check.current}"
        for check in checks
        if check.ok and check.key != "prerequisite_document"
    ]
    basis = "Подтверждено системой: " + "; ".join(satisfied_facts) + "."
    return OpportunityEligibility(
        eligible=not missing,
        points=points,
        rank=str(user.participation_status or ParticipationStatus.NEW_MEMBER),
        checks=checks,
        missing=missing,
        basis=basis,
    )


async def apply_to_offer(
    session: AsyncSession, offer: PartnerInitiative, user: User
) -> tuple[PartnerOfferApplication | None, str | None]:
    if not offer.is_active or offer.is_archived:
        return None, "offer_unavailable"
    existing = await get_application(session, offer.id, user.id)
    if existing and existing.status in ACTIVE_APPLICATION_STATUSES:
        return None, "already_applied"
    slots = await remaining_slots(session, offer)
    if slots is not None and slots <= 0:
        return None, "no_slots"

    if is_recognition(offer):
        eligibility = await evaluate_eligibility(session, offer, user)
        if not eligibility.eligible:
            return None, "not_eligible"
        if existing:
            existing.status = "requested"
            existing.reviewed_by = None
            existing.admin_comment = None
            application = existing
        else:
            application = PartnerOfferApplication(
                initiative_id=offer.id,
                user_id=user.id,
                status="requested",
            )
            session.add(application)
        application.eligibility_snapshot_json = eligibility.snapshot()
        application.basis_text = eligibility.basis
        application.award_wording = offer.default_award_wording
        await session.flush()
        return application, None

    # Legacy external offers keep their existing redemption semantics so the
    # migration does not break already-published partner offers. Recognition
    # documents never enter this branch and never spend points.
    balance = await total_points(session, user.id)
    if balance < offer.point_cost:
        return None, "insufficient_points"
    if existing:
        existing.status = "pending"
        existing.reviewed_by = None
        existing.admin_comment = None
        application = existing
    else:
        application = PartnerOfferApplication(
            initiative_id=offer.id, user_id=user.id, status="pending"
        )
        session.add(application)
    await session.flush()
    return application, None


async def list_my_applications(
    session: AsyncSession, user: User
) -> list[tuple[PartnerOfferApplication, PartnerInitiative]]:
    result = await session.execute(
        select(PartnerOfferApplication, PartnerInitiative)
        .join(
            PartnerInitiative,
            PartnerInitiative.id == PartnerOfferApplication.initiative_id,
        )
        .where(PartnerOfferApplication.user_id == user.id)
        .order_by(PartnerOfferApplication.created_at.desc())
    )
    return list(result.all())


async def is_saved(session: AsyncSession, offer_id: int, user_id: int) -> bool:
    saved = await session.scalar(
        select(SavedOpportunity).where(
            SavedOpportunity.initiative_id == offer_id,
            SavedOpportunity.user_id == user_id,
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
            SavedOpportunity.initiative_id == offer_id,
            SavedOpportunity.user_id == user_id,
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
    session: AsyncSession, user: User, *, limit: int = 8
) -> list[RecommendedOffer]:
    rows = await list_active_offers(session)
    recommended: list[RecommendedOffer] = []
    balance = await total_points(session, user.id)
    for offer, partner in rows:
        if await has_active_application(session, offer.id, user.id):
            continue
        slots = await remaining_slots(session, offer)
        if slots is not None and slots <= 0:
            continue

        if is_recognition(offer):
            eligibility = await evaluate_eligibility(session, offer, user)
            reasons = (
                ["все условия выполнены"]
                if eligibility.eligible
                else ["осталось: " + ", ".join(eligibility.missing)]
            )
            recommended.append(
                RecommendedOffer(offer=offer, partner=partner, reasons=reasons)
            )
        else:
            if offer.point_cost > balance:
                continue
            reasons = ["доступно по вашему балансу баллов"]
            if slots is None:
                reasons.append("без ограничения по местам")
            else:
                reasons.append(f"свободных мест: {slots}")
            recommended.append(
                RecommendedOffer(offer=offer, partner=partner, reasons=reasons)
            )
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
        .where(PartnerOfferApplication.status.in_(REVIEW_QUEUE_STATUSES))
        .order_by(PartnerOfferApplication.created_at)
    )
    return list(rows.all())


async def _decide_recognition_application(
    session: AsyncSession,
    application: PartnerOfferApplication,
    offer: PartnerInitiative,
    participant: User,
    *,
    action: str,
    actor: User,
) -> OfferApplicationResult:
    if action == "reject":
        application.status = "rejected"
        application.reviewed_by = actor.id
        return OfferApplicationResult(
            application,
            "Заявка на документ отклонена. Баллы не списываются.",
            f"Заявка «{offer.title}» отклонена. Баллы не списываются.",
            0,
        )

    if action == "needs_info":
        application.status = "needs_info"
        application.reviewed_by = actor.id
        return OfferApplicationResult(
            application,
            "Запрошена дополнительная информация.",
            f"По заявке «{offer.title}» нужна дополнительная информация.",
            0,
        )

    if action == "partner_approve":
        if application.status != "partner_review":
            return OfferApplicationResult(
                application, "Заявка не находится на проверке партнёра.", None, 0
            )
        application.status = "approved"
        application.reviewed_by = actor.id
        return OfferApplicationResult(
            application,
            "Партнёрская проверка подтверждена. Документ можно выдать.",
            f"Заявка «{offer.title}» одобрена партнёром.",
            0,
        )

    if action == "issue":
        if application.status == "issued":
            return OfferApplicationResult(
                application, "Документ уже выдан.", None, 0
            )
        if application.status != "approved":
            return OfferApplicationResult(
                application, "Сначала заявка должна быть одобрена.", None, 0
            )
        item = await add_portfolio_item(
            session,
            user_id=participant.id,
            title=offer.title,
            item_type=offer.portfolio_item_type or offer.opportunity_type,
            description=application.award_wording or offer.default_award_wording,
            issued_by=actor.id,
        )
        application.status = "issued"
        application.issued_at = datetime.now(timezone.utc)
        application.portfolio_item_id = item.id
        application.reviewed_by = actor.id
        return OfferApplicationResult(
            application,
            "Документ отмечен как выданный и добавлен в существующее портфолио.",
            f"Документ «{offer.title}» выдан и добавлен в ваше портфолио.",
            0,
        )

    # approve: re-check current facts, never trust only the snapshot captured
    # when the participant applied.
    eligibility = await evaluate_eligibility(session, offer, participant)
    if not eligibility.eligible:
        return OfferApplicationResult(
            application,
            "Условия больше не выполняются: " + ", ".join(eligibility.missing),
            None,
            0,
        )
    application.eligibility_snapshot_json = eligibility.snapshot()
    application.basis_text = eligibility.basis
    application.award_wording = application.award_wording or offer.default_award_wording
    application.reviewed_by = actor.id
    application.status = "partner_review" if offer.partner_review_required else "approved"
    if application.status == "partner_review":
        admin_notice = "Проверка ЭРА завершена. Заявка передана на partner review."
        participant_notice = f"Заявка «{offer.title}» прошла проверку ЭРА и передана партнёру."
    else:
        admin_notice = "Заявка одобрена. Баллы сохранены; документ готов к выдаче."
        participant_notice = f"Заявка «{offer.title}» одобрена. Баллы не списываются."
    return OfferApplicationResult(
        application, admin_notice, participant_notice, 0
    )


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

    if is_recognition(offer):
        if application.status in {"rejected", "issued"} and action not in {"issue"}:
            return OfferApplicationResult(
                application=application,
                admin_notice="Заявка уже обработана.",
                participant_notice=None,
                points_charged=0,
            )
        return await _decide_recognition_application(
            session,
            application,
            offer,
            participant,
            action=action,
            actor=actor,
        )

    # Legacy external offer behavior remains intact for compatibility.
    if action not in {"approve", "reject"}:
        raise ValueError(f"unsupported action for external offer: {action!r}")
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
