from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.era_pro_models import EraProApplication
from app.database.models import User
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.services.points_service import total_points

router = APIRouter(tags=["era-pro"])

ERA_PRO_THRESHOLD = 8_000
ERA_PRO_DIRECTIONS = {
    "diplomacy",
    "international_relations",
    "entrepreneurship",
    "management",
    "public_speaking",
    "culture",
    "education",
    "media",
    "social_projects",
    "project_work",
    "other",
}
ACTIVE_APPLICATION_STATUSES = {"submitted", "needs_info", "approved"}


class EraProApplicationIn(BaseModel):
    motivation: str = Field(min_length=20, max_length=4000)
    directions: list[str] = Field(min_length=1, max_length=6)
    target_result: str = Field(min_length=20, max_length=4000)
    community_value: str = Field(min_length=20, max_length=4000)
    portfolio_url: str | None = Field(default=None, max_length=1000)


class EraProApplicationOut(BaseModel):
    id: int
    status: str
    motivation: str
    directions: list[str]
    target_result: str
    community_value: str
    portfolio_url: str | None
    admin_comment: str | None
    submitted_at: str
    updated_at: str


class EraProMeOut(BaseModel):
    threshold: int
    points: int
    remaining_points: int
    eligible: bool
    status: Literal["locked", "available", "submitted", "needs_info", "approved", "declined"]
    has_access: bool
    application: EraProApplicationOut | None


class EraProAdminApplicationOut(EraProApplicationOut):
    user_id: int
    full_name: str
    username: str | None
    points: int
    participation_status: str | None


class EraProDecisionIn(BaseModel):
    decision: Literal["needs_info", "approved", "declined"]
    comment: str | None = Field(default=None, max_length=4000)


def _validate_directions(directions: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(item.strip() for item in directions if item.strip()))
    invalid = [item for item in normalized if item not in ERA_PRO_DIRECTIONS]
    if invalid or not normalized or len(normalized) > 6:
        raise HTTPException(status_code=422, detail="invalid_era_pro_directions")
    return normalized


def _application_out(row: EraProApplication) -> EraProApplicationOut:
    return EraProApplicationOut(
        id=row.id,
        status=row.status,
        motivation=row.motivation,
        directions=list(row.directions or []),
        target_result=row.target_result,
        community_value=row.community_value,
        portfolio_url=row.portfolio_url,
        admin_comment=row.admin_comment,
        submitted_at=row.submitted_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


async def _latest_application(session: AsyncSession, user_id: int) -> EraProApplication | None:
    return await session.scalar(
        select(EraProApplication)
        .where(EraProApplication.user_id == user_id)
        .order_by(EraProApplication.id.desc())
        .limit(1)
    )


async def _me_payload(session: AsyncSession, user: User) -> EraProMeOut:
    points = await total_points(session, user.id)
    application = await _latest_application(session, user.id)
    eligible = points >= ERA_PRO_THRESHOLD
    if application is None:
        status: str = "available" if eligible else "locked"
        has_access = False
    else:
        status = application.status
        has_access = application.status == "approved"
    return EraProMeOut(
        threshold=ERA_PRO_THRESHOLD,
        points=points,
        remaining_points=max(0, ERA_PRO_THRESHOLD - points),
        eligible=eligible,
        status=status,  # type: ignore[arg-type]
        has_access=has_access,
        application=_application_out(application) if application else None,
    )


async def require_era_pro_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


@router.get("/era-pro/me", response_model=EraProMeOut)
async def read_era_pro(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EraProMeOut:
    return await _me_payload(session, user)


@router.post("/era-pro/apply", response_model=EraProMeOut)
async def apply_era_pro(
    payload: EraProApplicationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> EraProMeOut:
    # Lock the user so simultaneous taps cannot create parallel applications.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())
    points = await total_points(session, user.id)
    if points < ERA_PRO_THRESHOLD:
        raise HTTPException(status_code=403, detail="era_pro_threshold_not_reached")

    latest = await _latest_application(session, user.id)
    if latest is not None and latest.status in ACTIVE_APPLICATION_STATUSES:
        raise HTTPException(status_code=409, detail="era_pro_application_already_active")

    directions = _validate_directions(payload.directions)
    application = EraProApplication(
        user_id=user.id,
        status="submitted",
        motivation=payload.motivation.strip(),
        directions=directions,
        target_result=payload.target_result.strip(),
        community_value=payload.community_value.strip(),
        portfolio_url=payload.portfolio_url.strip() if payload.portfolio_url else None,
    )
    session.add(application)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="era_pro.application_submitted",
        entity_type="era_pro_application",
        entity_id=application.id,
        new_value={"status": "submitted", "points_at_submission": points},
    )
    if bot is not None:
        await notify_admins(
            bot,
            settings,
            "Новая заявка в ЭРА PRO\n\n"
            f"Участник: {user.first_name} {user.last_name or ''}\n"
            f"Баллы: {points}\n"
            f"Заявка: #{application.id}\n\n"
            "Откройте админ-панель → Заявки ЭРА PRO.",
        )
    return await _me_payload(session, user)


@router.post("/era-pro/resubmit", response_model=EraProMeOut)
async def resubmit_era_pro(
    payload: EraProApplicationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> EraProMeOut:
    application = await session.scalar(
        select(EraProApplication)
        .where(EraProApplication.user_id == user.id)
        .order_by(EraProApplication.id.desc())
        .limit(1)
        .with_for_update()
    )
    if application is None or application.status != "needs_info":
        raise HTTPException(status_code=409, detail="era_pro_application_not_editable")

    application.motivation = payload.motivation.strip()
    application.directions = _validate_directions(payload.directions)
    application.target_result = payload.target_result.strip()
    application.community_value = payload.community_value.strip()
    application.portfolio_url = payload.portfolio_url.strip() if payload.portfolio_url else None
    application.status = "submitted"
    application.admin_comment = None
    application.reviewed_by = None
    application.reviewed_at = None
    application.submitted_at = datetime.now(timezone.utc)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="era_pro.application_resubmitted",
        entity_type="era_pro_application",
        entity_id=application.id,
        new_value={"status": "submitted"},
    )
    if bot is not None:
        await notify_admins(
            bot,
            settings,
            f"Заявка ЭРА PRO #{application.id} дополнена участником и снова ждёт проверки.",
        )
    return await _me_payload(session, user)


@router.get("/admin/era-pro/applications", response_model=list[EraProAdminApplicationOut])
async def admin_era_pro_applications(
    _admin: User = Depends(require_era_pro_admin),
    session: AsyncSession = Depends(get_session),
) -> list[EraProAdminApplicationOut]:
    rows = (
        await session.execute(
            select(EraProApplication, User)
            .join(User, User.id == EraProApplication.user_id)
            .where(EraProApplication.status.in_(["submitted", "needs_info"]))
            .order_by(EraProApplication.submitted_at.desc(), EraProApplication.id.desc())
        )
    ).all()
    out: list[EraProAdminApplicationOut] = []
    for application, user in rows:
        points = await total_points(session, user.id)
        base = _application_out(application)
        out.append(
            EraProAdminApplicationOut(
                **base.model_dump(),
                user_id=user.id,
                full_name=f"{user.first_name} {user.last_name or ''}".strip(),
                username=user.username,
                points=points,
                participation_status=getattr(user, "participation_status", None),
            )
        )
    return out


@router.post("/admin/era-pro/applications/{application_id}/decision", response_model=EraProAdminApplicationOut)
async def decide_era_pro_application(
    application_id: int,
    payload: EraProDecisionIn,
    admin: User = Depends(require_era_pro_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> EraProAdminApplicationOut:
    application = await session.scalar(
        select(EraProApplication)
        .where(EraProApplication.id == application_id)
        .with_for_update()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="era_pro_application_not_found")
    if application.status != "submitted":
        raise HTTPException(status_code=409, detail="era_pro_application_not_pending")
    if payload.decision == "needs_info" and not (payload.comment or "").strip():
        raise HTTPException(status_code=422, detail="era_pro_comment_required")

    old_status = application.status
    application.status = payload.decision
    application.admin_comment = (payload.comment or "").strip() or None
    application.reviewed_by = admin.id
    application.reviewed_at = datetime.now(timezone.utc)
    if payload.decision == "approved":
        application.access_granted_at = datetime.now(timezone.utc)
    await session.flush()

    await audit(
        session,
        actor_id=admin.id,
        action=f"era_pro.application_{payload.decision}",
        entity_type="era_pro_application",
        entity_id=application.id,
        old_value={"status": old_status},
        new_value={"status": application.status},
    )

    applicant = await session.get(User, application.user_id)
    if applicant is None:
        raise HTTPException(status_code=404, detail="era_pro_user_not_found")
    if bot is not None:
        text = {
            "approved": "Ваша заявка в ЭРА PRO одобрена. Доступ к закрытому уровню открыт в Mini App.",
            "needs_info": f"Заявку в ЭРА PRO нужно дополнить.\n\nКомментарий: {application.admin_comment}",
            "declined": "Рассмотрение заявки в ЭРА PRO завершено. Сейчас доступ не выдан. Вы сможете подать новую заявку позже.",
        }[payload.decision]
        try:
            await bot.send_message(applicant.telegram_id, text)
        except Exception:
            # The decision is authoritative even if Telegram delivery fails.
            pass

    points = await total_points(session, applicant.id)
    base = _application_out(application)
    return EraProAdminApplicationOut(
        **base.model_dump(),
        user_id=applicant.id,
        full_name=f"{applicant.first_name} {applicant.last_name or ''}".strip(),
        username=applicant.username,
        points=points,
        participation_status=getattr(applicant, "participation_status", None),
    )
