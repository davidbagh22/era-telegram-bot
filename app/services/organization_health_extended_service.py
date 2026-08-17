from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.career_models import CareerPortfolioItem, CareerProfile, RecommendationRequest
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication, SavedOpportunity
from app.database.referral_models import ReferralRelationship
from app.services.organization_health_service import (
    HealthMetric,
    OrganizationHealthSnapshot,
    build_organization_health,
)


def _pct(part: int | float, total: int | float) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _cap(value: float) -> int:
    return max(0, min(100, round(value)))


async def _count(session: AsyncSession, model, *conditions) -> int:
    query = select(func.count()).select_from(model)
    for condition in conditions:
        query = query.where(condition)
    return int(await session.scalar(query) or 0)


async def build_extended_organization_health(
    session: AsyncSession,
) -> OrganizationHealthSnapshot:
    """Extend the core health snapshot with factual growth/career/opportunity signals.

    These indicators are derived from real platform records only. No My Vector
    traits, interests, notes or individual answers are added here; the Pulse
    remains exactly the privacy-safe current-state aggregate from the core
    organization health service.
    """

    base = await build_organization_health(session)
    now = datetime.now(timezone.utc)
    month_ago = now - timedelta(days=30)

    approved_total = next(
        (int(metric.value) for metric in base.metrics if metric.key == "approved"),
        0,
    )

    # Referral funnel: code accepted -> registration/chat reward -> first event.
    referral_total = await _count(session, ReferralRelationship)
    referrals_30d = await _count(
        session,
        ReferralRelationship,
        ReferralRelationship.created_at >= month_ago,
    )
    referral_registered_total = await _count(
        session,
        ReferralRelationship,
        ReferralRelationship.registration_rewarded_at.is_not(None),
    )
    referral_first_event_total = await _count(
        session,
        ReferralRelationship,
        ReferralRelationship.first_event_rewarded_at.is_not(None),
    )
    referral_registered_30d = await _count(
        session,
        ReferralRelationship,
        ReferralRelationship.registration_rewarded_at >= month_ago,
    )
    referral_first_event_30d = await _count(
        session,
        ReferralRelationship,
        ReferralRelationship.first_event_rewarded_at >= month_ago,
    )
    active_inviters_30d = int(
        await session.scalar(
            select(func.count(func.distinct(ReferralRelationship.inviter_id))).where(
                ReferralRelationship.created_at >= month_ago
            )
        )
        or 0
    )
    referral_registration_conversion = _pct(referral_registered_total, referral_total)
    referral_event_conversion = _pct(referral_first_event_total, referral_registered_total)

    # Opportunities: available inventory, demonstrated interest and applications.
    active_partners = await _count(
        session,
        Partner,
        Partner.is_active.is_(True),
        Partner.is_archived.is_(False),
    )
    active_opportunities = await _count(
        session,
        PartnerInitiative,
        PartnerInitiative.is_active.is_(True),
        PartnerInitiative.is_archived.is_(False),
        or_(PartnerInitiative.expires_at.is_(None), PartnerInitiative.expires_at >= now),
    )
    opportunity_saves_30d = await _count(
        session,
        SavedOpportunity,
        SavedOpportunity.created_at >= month_ago,
    )
    opportunity_applications_30d = await _count(
        session,
        PartnerOfferApplication,
        PartnerOfferApplication.created_at >= month_ago,
    )
    opportunity_approved_30d = await _count(
        session,
        PartnerOfferApplication,
        PartnerOfferApplication.created_at >= month_ago,
        PartnerOfferApplication.status == "approved",
    )
    opportunity_applicants_30d = int(
        await session.scalar(
            select(func.count(func.distinct(PartnerOfferApplication.user_id))).where(
                PartnerOfferApplication.created_at >= month_ago
            )
        )
        or 0
    )
    opportunity_approval_rate = _pct(opportunity_approved_30d, opportunity_applications_30d)
    opportunity_reach_rate = _pct(opportunity_applicants_30d, approved_total)
    opportunities_per_partner = round(active_opportunities / active_partners, 1) if active_partners else 0.0

    # Career value created by the ecosystem.
    career_profiles = await _count(session, CareerProfile)
    portfolio_total = await _count(session, CareerPortfolioItem)
    portfolio_verified = await _count(
        session,
        CareerPortfolioItem,
        CareerPortfolioItem.status == "verified",
    )
    portfolio_rejected = await _count(
        session,
        CareerPortfolioItem,
        CareerPortfolioItem.status == "rejected",
    )
    portfolio_verified_30d = await _count(
        session,
        CareerPortfolioItem,
        CareerPortfolioItem.status == "verified",
        CareerPortfolioItem.verified_at >= month_ago,
    )
    portfolio_pending = await _count(
        session,
        CareerPortfolioItem,
        CareerPortfolioItem.status == "pending",
    )
    recommendation_pending = await _count(
        session,
        RecommendationRequest,
        RecommendationRequest.status == "requested",
    )
    recommendation_approved_30d = await _count(
        session,
        RecommendationRequest,
        RecommendationRequest.status == "approved",
        RecommendationRequest.approved_at >= month_ago,
    )
    portfolio_verification_rate = _pct(portfolio_verified, portfolio_verified + portfolio_rejected)
    portfolio_per_profile = round(portfolio_total / career_profiles, 1) if career_profiles else 0.0

    added = [
        HealthMetric(
            "referrals_30d",
            "Рост",
            "Приглашений за 30 дней",
            referrals_30d,
            str(referrals_30d),
            "новые связи «пригласивший → новичок» по введённому коду",
        ),
        HealthMetric(
            "active_inviters_30d",
            "Рост",
            "Активных приглашающих",
            active_inviters_30d,
            str(active_inviters_30d),
            "уникальные участники, чей код использовали за 30 дней",
        ),
        HealthMetric(
            "referral_registered_30d",
            "Рост",
            "Дошли до регистрации и чата",
            referral_registered_30d,
            str(referral_registered_30d),
            "приглашённые, у которых за 30 дней подтверждён первый реферальный этап",
        ),
        HealthMetric(
            "referral_first_event_30d",
            "Рост",
            "Дошли до первого мероприятия",
            referral_first_event_30d,
            str(referral_first_event_30d),
            "приглашённые, подтвердившие первое мероприятие за 30 дней",
        ),
        HealthMetric(
            "referral_registration_conversion",
            "Рост",
            "Код → регистрация и чат",
            referral_registration_conversion,
            f"{referral_registration_conversion:.1f}%",
            f"награда регистрации подтверждена у {referral_registered_total} из {referral_total} приглашённых",
            _cap(referral_registration_conversion),
        ),
        HealthMetric(
            "referral_event_conversion",
            "Рост",
            "Приглашённый → первое мероприятие",
            referral_event_conversion,
            f"{referral_event_conversion:.1f}%",
            f"до первого подтверждённого события дошли {referral_first_event_total} из {referral_registered_total} получивших стартовую награду",
            _cap(referral_event_conversion),
        ),
        HealthMetric(
            "referral_rewards_30d",
            "Рост",
            "Реферальных этапов за 30 дней",
            referral_registered_30d + referral_first_event_30d,
            str(referral_registered_30d + referral_first_event_30d),
            f"регистрация/чат {referral_registered_30d} · первое мероприятие {referral_first_event_30d}",
        ),
        HealthMetric(
            "active_partners",
            "Возможности",
            "Активных партнёров",
            active_partners,
            str(active_partners),
            "действующие партнёры, доступные в базе возможностей",
        ),
        HealthMetric(
            "active_opportunities",
            "Возможности",
            "Доступных возможностей",
            active_opportunities,
            str(active_opportunities),
            "активные и не истёкшие предложения партнёров",
        ),
        HealthMetric(
            "opportunities_per_partner",
            "Возможности",
            "Возможностей на партнёра",
            opportunities_per_partner,
            f"{opportunities_per_partner:.1f}",
            "среднее число доступных предложений на одного активного партнёра",
        ),
        HealthMetric(
            "opportunity_saves_30d",
            "Возможности",
            "Сохранений возможностей",
            opportunity_saves_30d,
            str(opportunity_saves_30d),
            "сколько раз участники сохранили возможности за 30 дней",
        ),
        HealthMetric(
            "opportunity_applicants_30d",
            "Возможности",
            "Участников подали заявки",
            opportunity_applicants_30d,
            str(opportunity_applicants_30d),
            "уникальные участники с заявкой на партнёрскую возможность за 30 дней",
        ),
        HealthMetric(
            "opportunity_reach_rate",
            "Возможности",
            "Охват возможностями",
            opportunity_reach_rate,
            f"{opportunity_reach_rate:.1f}%",
            "доля одобренного сообщества, подавшая хотя бы одну заявку за 30 дней",
            _cap(opportunity_reach_rate) if approved_total else None,
        ),
        HealthMetric(
            "opportunity_applications_30d",
            "Возможности",
            "Заявок на возможности",
            opportunity_applications_30d,
            str(opportunity_applications_30d),
            f"{opportunity_applicants_30d} уникальных участников за 30 дней",
        ),
        HealthMetric(
            "opportunity_approved_30d",
            "Возможности",
            "Одобрено заявок",
            opportunity_approved_30d,
            str(opportunity_approved_30d),
            "одобренные заявки на партнёрские возможности за 30 дней",
        ),
        HealthMetric(
            "opportunity_approval_rate",
            "Возможности",
            "Одобрение заявок на возможности",
            opportunity_approval_rate,
            f"{opportunity_approval_rate:.1f}%" if opportunity_applications_30d else "Нет заявок",
            f"одобрено {opportunity_approved_30d} из {opportunity_applications_30d} заявок за 30 дней",
            _cap(opportunity_approval_rate) if opportunity_applications_30d else None,
        ),
        HealthMetric(
            "career_profile_adoption",
            "Портфолио",
            "Создали карьерный профиль",
            _pct(career_profiles, approved_total),
            f"{career_profiles} · {_pct(career_profiles, approved_total):.1f}%",
            "доля сообщества, начавшая собирать профессиональный профиль",
            _cap(_pct(career_profiles, approved_total)) if approved_total else None,
        ),
        HealthMetric(
            "portfolio_total",
            "Портфолио",
            "Достижений в портфолио",
            portfolio_total,
            str(portfolio_total),
            "внешние и личные результаты, добавленные участниками",
        ),
        HealthMetric(
            "portfolio_per_profile",
            "Портфолио",
            "Достижений на профиль",
            portfolio_per_profile,
            f"{portfolio_per_profile:.1f}",
            "средняя глубина заполнения карьерного профиля",
        ),
        HealthMetric(
            "portfolio_verified",
            "Портфолио",
            "Подтверждено ЭРА",
            portfolio_verified,
            str(portfolio_verified),
            f"за последние 30 дней подтверждено {portfolio_verified_30d}",
        ),
        HealthMetric(
            "portfolio_verified_30d",
            "Портфолио",
            "Подтверждено за 30 дней",
            portfolio_verified_30d,
            str(portfolio_verified_30d),
            "достижения, получившие официальный статус ЭРА за 30 дней",
        ),
        HealthMetric(
            "portfolio_verification_rate",
            "Портфолио",
            "Доля подтверждений ЭРА",
            portfolio_verification_rate,
            f"{portfolio_verification_rate:.1f}%" if portfolio_verified + portfolio_rejected else "Нет решений",
            f"подтверждено {portfolio_verified} · отклонено {portfolio_rejected}",
            _cap(portfolio_verification_rate) if portfolio_verified + portfolio_rejected else None,
        ),
        HealthMetric(
            "portfolio_pending",
            "Портфолио",
            "Достижений ждут проверки",
            portfolio_pending,
            str(portfolio_pending),
            "очередь подтверждения документов и достижений",
        ),
        HealthMetric(
            "recommendation_pending",
            "Портфолио",
            "Рекомендаций ждут решения",
            recommendation_pending,
            str(recommendation_pending),
            "запрошенные официальные рекомендательные письма",
        ),
        HealthMetric(
            "recommendation_approved_30d",
            "Портфолио",
            "Рекомендаций утверждено за 30 дней",
            recommendation_approved_30d,
            str(recommendation_approved_30d),
            "официальные рекомендательные письма, утверждённые за 30 дней",
        ),
    ]

    risks = list(base.risks)
    if referral_registered_total >= 5 and referral_event_conversion < 35:
        risks.append(
            "Реферальная регистрация работает, но менее 35% приглашённых доходят до первого подтверждённого мероприятия."
        )
    if active_opportunities == 0:
        risks.append("В приложении сейчас нет активных партнёрских возможностей.")
    if portfolio_pending >= 10:
        risks.append(
            f"Очередь подтверждения портфолио выросла до {portfolio_pending}: участники дольше ждут официальный статус достижения."
        )
    if recommendation_pending >= 5:
        risks.append(
            f"Официальных рекомендаций ждут решения: {recommendation_pending}."
        )

    return replace(
        base,
        metrics=[*base.metrics, *added],
        risks=risks[:10],
        data_note=(
            base.data_note
            + " Рост, возможности и портфолио считаются отдельно по фактическим действиям платформы и do not affect Pulse."
        ),
    )
