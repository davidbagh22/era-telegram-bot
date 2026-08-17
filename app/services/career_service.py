from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.career_models import CareerPortfolioItem, CareerProfile, RecommendationRequest
from app.database.models import (
    EventRegistration,
    Office,
    Project,
    ProjectMember,
    TaskSubmission,
    User,
    UserOffice,
)
from app.utils.constants import ProjectStatus, RegistrationStatus

CAREER_ITEM_TYPES = {
    "education",
    "work",
    "internship",
    "project",
    "achievement",
    "certificate",
    "course",
    "publication",
    "speech",
    "volunteer",
    "award",
    "language",
    "skill",
    "other",
}
RESUME_PURPOSES = {"work", "internship", "university", "grant", "volunteer", "universal"}
RECOMMENDATION_STATUSES = {"requested", "approved", "rejected"}


def utcnow() -> datetime:
    return datetime.now().astimezone()


def clean_text(value: str | None, *, max_length: int | None = None) -> str:
    text = (value or "").strip()
    if max_length is not None:
        text = text[:max_length]
    return text


async def get_or_create_profile(session: AsyncSession, user_id: int) -> CareerProfile:
    profile = await session.get(CareerProfile, user_id)
    if profile is None:
        profile = CareerProfile(user_id=user_id, languages=[])
        session.add(profile)
        await session.flush()
    return profile


async def update_profile(
    session: AsyncSession,
    user_id: int,
    *,
    headline: str | None,
    about: str | None,
    languages: list[dict[str, Any]] | None,
) -> CareerProfile:
    profile = await get_or_create_profile(session, user_id)
    profile.headline = clean_text(headline, max_length=180) or None
    profile.about = clean_text(about, max_length=1200) or None
    if languages is not None:
        normalized: list[dict[str, str]] = []
        for item in languages[:12]:
            name = clean_text(str(item.get("name", "")), max_length=80)
            level = clean_text(str(item.get("level", "")), max_length=50)
            if name:
                normalized.append({"name": name, "level": level})
        profile.languages = normalized
    await session.commit()
    await session.refresh(profile)
    return profile


async def list_items(session: AsyncSession, user_id: int) -> list[CareerPortfolioItem]:
    return list(
        (
            await session.scalars(
                select(CareerPortfolioItem)
                .where(CareerPortfolioItem.user_id == user_id)
                .order_by(desc(CareerPortfolioItem.issued_at), desc(CareerPortfolioItem.created_at))
            )
        ).all()
    )


async def create_item(
    session: AsyncSession,
    user_id: int,
    *,
    item_type: str,
    title: str,
    organization: str | None = None,
    description: str | None = None,
    issued_at=None,
    url: str | None = None,
    include_in_resume: bool = True,
) -> CareerPortfolioItem:
    if item_type not in CAREER_ITEM_TYPES:
        raise ValueError("invalid_item_type")
    title = clean_text(title, max_length=255)
    if not title:
        raise ValueError("title_required")
    item = CareerPortfolioItem(
        user_id=user_id,
        item_type=item_type,
        title=title,
        organization=clean_text(organization, max_length=255) or None,
        description=clean_text(description, max_length=3000) or None,
        issued_at=issued_at,
        url=clean_text(url, max_length=500) or None,
        status="self_reported",
        include_in_resume=include_in_resume,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_item(
    session: AsyncSession,
    item: CareerPortfolioItem,
    **changes: Any,
) -> CareerPortfolioItem:
    if item.status == "verified":
        raise ValueError("verified_item_locked")
    if "item_type" in changes and changes["item_type"] is not None:
        if changes["item_type"] not in CAREER_ITEM_TYPES:
            raise ValueError("invalid_item_type")
        item.item_type = changes["item_type"]
    if "title" in changes and changes["title"] is not None:
        title = clean_text(changes["title"], max_length=255)
        if not title:
            raise ValueError("title_required")
        item.title = title
    if "organization" in changes:
        item.organization = clean_text(changes["organization"], max_length=255) or None
    if "description" in changes:
        item.description = clean_text(changes["description"], max_length=3000) or None
    if "issued_at" in changes:
        item.issued_at = changes["issued_at"]
    if "url" in changes:
        item.url = clean_text(changes["url"], max_length=500) or None
    if "include_in_resume" in changes and changes["include_in_resume"] is not None:
        item.include_in_resume = bool(changes["include_in_resume"])
    if item.status in {"pending", "rejected"}:
        item.status = "self_reported"
        item.admin_comment = None
        item.submitted_at = None
    await session.commit()
    await session.refresh(item)
    return item


async def attach_file(
    session: AsyncSession,
    item: CareerPortfolioItem,
    *,
    file_id: str,
    file_name: str,
) -> CareerPortfolioItem:
    if item.status == "verified":
        raise ValueError("verified_item_locked")
    item.file_id = file_id
    item.file_name = clean_text(file_name, max_length=255) or "document"
    if item.status in {"pending", "rejected"}:
        item.status = "self_reported"
        item.admin_comment = None
        item.submitted_at = None
    await session.commit()
    await session.refresh(item)
    return item


async def request_verification(
    session: AsyncSession, item: CareerPortfolioItem
) -> CareerPortfolioItem:
    if item.status == "verified":
        return item
    if not item.file_id and not item.url:
        raise ValueError("evidence_required")
    item.status = "pending"
    item.submitted_at = utcnow()
    item.admin_comment = None
    await session.commit()
    await session.refresh(item)
    return item


async def review_item(
    session: AsyncSession,
    item: CareerPortfolioItem,
    *,
    reviewer_id: int,
    decision: str,
    comment: str | None,
) -> CareerPortfolioItem:
    if decision not in {"approve", "reject"}:
        raise ValueError("invalid_decision")
    if item.status != "pending":
        raise ValueError("item_not_pending")
    if decision == "approve":
        item.status = "verified"
        item.verified_by = reviewer_id
        item.verified_at = utcnow()
        item.admin_comment = clean_text(comment, max_length=1000) or None
    else:
        item.status = "rejected"
        item.verified_by = reviewer_id
        item.verified_at = utcnow()
        item.admin_comment = clean_text(comment, max_length=1000) or "Не подтверждено"
    await session.commit()
    await session.refresh(item)
    return item


async def confirmed_activity_facts(session: AsyncSession, user: User) -> dict[str, Any]:
    attended = int(
        await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.user_id == user.id,
                EventRegistration.status == RegistrationStatus.ATTENDED,
            )
        )
        or 0
    )
    completed_tasks = int(
        await session.scalar(
            select(func.count())
            .select_from(TaskSubmission)
            .where(
                TaskSubmission.user_id == user.id,
                TaskSubmission.status.in_(["approved", "completed"]),
            )
        )
        or 0
    )
    authored_projects = int(
        await session.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.author_id == user.id,
                Project.status.in_(
                    [ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS, ProjectStatus.COMPLETED]
                ),
            )
        )
        or 0
    )
    contributions = int(
        await session.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.user_id == user.id,
                ProjectMember.contribution_status == "confirmed",
            )
        )
        or 0
    )
    leadership_rows = list(
        (
            await session.scalars(
                select(Office.title)
                .join(UserOffice, UserOffice.office_id == Office.id)
                .where(UserOffice.user_id == user.id, UserOffice.is_active.is_(True))
                .order_by(Office.sort_order, Office.title)
            )
        ).all()
    )
    verified_items = list(
        (
            await session.scalars(
                select(CareerPortfolioItem)
                .where(
                    CareerPortfolioItem.user_id == user.id,
                    CareerPortfolioItem.status == "verified",
                )
                .order_by(desc(CareerPortfolioItem.issued_at), desc(CareerPortfolioItem.id))
            )
        ).all()
    )
    return {
        "attended_events": attended,
        "completed_tasks": completed_tasks,
        "authored_projects": authored_projects,
        "confirmed_project_contributions": contributions,
        "leadership_roles": leadership_rows,
        "verified_items": verified_items,
    }


def _full_name(user: User) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip()


def recommendation_text(user: User, facts: dict[str, Any], *, formal: bool) -> str:
    name = _full_name(user) or "Участник ЭРА"
    attended = facts["attended_events"]
    tasks = facts["completed_tasks"]
    projects = facts["authored_projects"]
    contributions = facts["confirmed_project_contributions"]
    roles: list[str] = facts["leadership_roles"]
    items: list[CareerPortfolioItem] = facts["verified_items"]

    evidence: list[str] = []
    if attended:
        evidence.append(f"подтверждённое участие в {attended} мероприятиях")
    if tasks:
        evidence.append(f"{tasks} выполненных и подтверждённых задач")
    if projects:
        evidence.append(f"{projects} собственных одобренных или реализованных проектов")
    if contributions:
        evidence.append(f"{contributions} подтверждённых вкладов в командные проекты")
    if roles:
        evidence.append("лидерские роли: " + ", ".join(roles[:4]))
    if items:
        evidence.append(f"{len(items)} внешних достижений, подтверждённых ЭРА документами")

    strengths: list[str] = []
    if tasks >= 3:
        strengths.append("последовательность в доведении задач до результата")
    if contributions or projects:
        strengths.append("практический проектный опыт")
    if roles:
        strengths.append("опыт ответственности и координации")
    if attended >= 5:
        strengths.append("устойчивую включённость в деятельность сообщества")
    if items:
        strengths.append("инициативность в развитии собственного профессионального портфолио")

    if formal:
        opening = (
            f"Объединение лидеров и культурных инициатив «ЭРА» рекомендует {name} как участника, "
            "чья характеристика основана на зафиксированной и подтверждённой деятельности внутри организации."
        )
    else:
        opening = (
            f"{name}: рекомендационный профиль ЭРА построен только на подтверждённой активности и результатах."
        )

    if evidence:
        activity = " За период участия зафиксированы: " + "; ".join(evidence) + "."
    else:
        activity = " Подтверждённой активности пока недостаточно для содержательной характеристики."

    if strengths:
        conclusion = " На основании этих фактов можно отметить " + ", ".join(strengths) + "."
    else:
        conclusion = " Рекомендация будет становиться содержательнее по мере появления подтверждённых результатов."

    if formal:
        conclusion += (
            " ЭРА считает этот опыт релевантным для образовательных, проектных, общественных и профессиональных возможностей, "
            "где ценятся инициатива, ответственность и работа с реальными задачами."
        )
    return opening + activity + conclusion


async def automatic_recommendation(session: AsyncSession, user: User) -> dict[str, Any]:
    facts = await confirmed_activity_facts(session, user)
    return {
        "text": recommendation_text(user, facts, formal=False),
        "facts": {
            "attended_events": facts["attended_events"],
            "completed_tasks": facts["completed_tasks"],
            "authored_projects": facts["authored_projects"],
            "confirmed_project_contributions": facts["confirmed_project_contributions"],
            "leadership_roles": facts["leadership_roles"],
            "verified_external_items": len(facts["verified_items"]),
        },
        "privacy_note": "Личные данные из «Моего вектора» и психологические ответы не используются.",
    }


async def latest_recommendation_request(
    session: AsyncSession, user_id: int
) -> RecommendationRequest | None:
    return await session.scalar(
        select(RecommendationRequest)
        .where(RecommendationRequest.user_id == user_id)
        .order_by(desc(RecommendationRequest.created_at), desc(RecommendationRequest.id))
        .limit(1)
    )


async def recommendation_by_token(
    session: AsyncSession, token: str
) -> RecommendationRequest | None:
    normalized = clean_text(token, max_length=96)
    if not normalized:
        return None
    return await session.scalar(
        select(RecommendationRequest)
        .where(RecommendationRequest.verification_token == normalized)
        .limit(1)
    )


async def request_official_recommendation(
    session: AsyncSession, user: User, purpose: str
) -> RecommendationRequest:
    if purpose not in RESUME_PURPOSES:
        raise ValueError("invalid_purpose")
    existing = await latest_recommendation_request(session, user.id)
    if existing and existing.status == "requested":
        return existing
    facts = await confirmed_activity_facts(session, user)
    request = RecommendationRequest(
        user_id=user.id,
        purpose=purpose,
        status="requested",
        draft_text=recommendation_text(user, facts, formal=True),
        requested_at=utcnow(),
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def approve_recommendation(
    session: AsyncSession,
    request: RecommendationRequest,
    *,
    reviewer_id: int,
    final_text: str | None,
) -> RecommendationRequest:
    if request.status != "requested":
        raise ValueError("request_not_pending")
    text = clean_text(final_text, max_length=12000) or request.draft_text
    request.final_text = text
    request.status = "approved"
    request.approved_by = reviewer_id
    request.approved_at = utcnow()
    request.document_number = f"ERA-REC-{request.approved_at.year}-{request.id:06d}"
    request.verification_token = secrets.token_urlsafe(24)
    request.rejection_comment = None
    await session.commit()
    await session.refresh(request)
    return request


async def reject_recommendation(
    session: AsyncSession,
    request: RecommendationRequest,
    *,
    reviewer_id: int,
    comment: str | None,
) -> RecommendationRequest:
    if request.status != "requested":
        raise ValueError("request_not_pending")
    request.status = "rejected"
    request.approved_by = reviewer_id
    request.approved_at = utcnow()
    request.rejection_comment = clean_text(comment, max_length=1500) or "Запрос не одобрен"
    await session.commit()
    await session.refresh(request)
    return request


async def dashboard(session: AsyncSession, user: User) -> dict[str, Any]:
    profile = await get_or_create_profile(session, user.id)
    items = await list_items(session, user.id)
    facts = await confirmed_activity_facts(session, user)
    recommendation = {
        "text": recommendation_text(user, facts, formal=False),
        "facts": {
            "attended_events": facts["attended_events"],
            "completed_tasks": facts["completed_tasks"],
            "authored_projects": facts["authored_projects"],
            "confirmed_project_contributions": facts["confirmed_project_contributions"],
            "leadership_roles": facts["leadership_roles"],
            "verified_external_items": len(facts["verified_items"]),
        },
        "privacy_note": "Личные данные из «Моего вектора» и психологические ответы не используются.",
    }
    latest_request = await latest_recommendation_request(session, user.id)
    verified_user_items = [item for item in items if item.status == "verified"]
    pending = [item for item in items if item.status == "pending"]
    self_reported = [item for item in items if item.status in {"self_reported", "rejected"}]
    era_confirmed = (
        facts["attended_events"]
        + facts["completed_tasks"]
        + facts["authored_projects"]
        + facts["confirmed_project_contributions"]
        + len(facts["leadership_roles"])
    )
    return {
        "profile": {
            "headline": profile.headline or "",
            "about": profile.about or "",
            "languages": profile.languages or [],
        },
        "counts": {
            "confirmed": era_confirmed + len(verified_user_items),
            "added_by_me": len(self_reported),
            "pending": len(pending),
            "evidence_files": len([item for item in items if item.file_id]),
        },
        "items": [serialize_item(item) for item in items],
        "automatic_recommendation": recommendation,
        "official_recommendation": serialize_request(latest_request) if latest_request else None,
    }


def serialize_item(item: CareerPortfolioItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "title": item.title,
        "organization": item.organization or "",
        "description": item.description or "",
        "issued_at": item.issued_at.isoformat() if item.issued_at else None,
        "url": item.url,
        "file_name": item.file_name,
        "has_file": bool(item.file_id),
        "status": item.status,
        "include_in_resume": item.include_in_resume,
        "admin_comment": item.admin_comment,
    }


def serialize_request(request: RecommendationRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "purpose": request.purpose,
        "status": request.status,
        "draft_text": request.draft_text,
        "final_text": request.final_text,
        "document_number": request.document_number,
        "requested_at": request.requested_at.isoformat(),
        "approved_at": request.approved_at.isoformat() if request.approved_at else None,
        "rejection_comment": request.rejection_comment,
        "can_download": request.status == "approved" and bool(request.document_number),
    }
