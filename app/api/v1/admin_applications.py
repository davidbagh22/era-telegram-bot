from __future__ import annotations

import base64
import logging

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.database.socials import SocialLink, SocialProfile
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.consent_service import latest_consent
from app.utils.constants import ApplicationStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_application_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class ApplicationSocialLinkOut(BaseModel):
    platform: str
    url: str


class FullApplicationOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    birth_date: str | None
    age: int | None
    phone: str | None
    email: str | None
    city: str | None
    education_work: str | None
    occupation: str | None
    skills: list[str]
    experience: str | None
    motivation: str | None
    available_time: str | None
    desired_path: str | None
    departments: list[str]
    directions: list[str]
    social_links: list[ApplicationSocialLinkOut]
    personal_data_consent: bool
    consent_policy_version: str | None
    application_status: str
    photo_attached: bool
    photo_data_url: str | None
    created_at: str


async def _load_photo_data_url(
    bot: Bot | None,
    profile: SocialProfile | None,
    *,
    user_id: int,
) -> str | None:
    if bot is None or profile is None or not profile.photo_file_id:
        return None
    try:
        downloaded = await bot.download(profile.photo_file_id)
        if downloaded is None:
            return None
        if hasattr(downloaded, "getvalue"):
            raw = downloaded.getvalue()
        else:
            raw = downloaded.read()
        if not raw:
            return None
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        # Do not log exception details here: Telegram exceptions can contain
        # request metadata. Only the internal DB user id is safe and useful.
        logger.warning("Could not load registration photo for user_id=%s", user_id)
        return None


async def _application_out(
    session: AsyncSession,
    bot: Bot | None,
    user: User,
) -> FullApplicationOut:
    profile = await session.scalar(
        select(SocialProfile).where(SocialProfile.user_id == user.id)
    )
    social_rows = (
        await session.scalars(
            select(SocialLink)
            .where(SocialLink.user_id == user.id, SocialLink.is_active.is_(True))
            .order_by(SocialLink.platform, SocialLink.id)
        )
    ).all()
    consent = await latest_consent(
        session,
        user_id=user.id,
        consent_type="registration",
    )
    photo_data_url = await _load_photo_data_url(bot, profile, user_id=user.id)

    departments = [
        link.department.name
        for link in (user.departments or [])
        if getattr(link, "department", None) is not None
    ]
    directions = [
        link.direction.name
        for link in (user.directions or [])
        if getattr(link, "direction", None) is not None
    ]

    return FullApplicationOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date.isoformat() if user.birth_date else None,
        age=user.age,
        phone=user.phone,
        email=user.email,
        city=user.city,
        education_work=user.education_work,
        occupation=user.occupation,
        skills=list(user.skills or []),
        experience=user.experience,
        motivation=user.motivation,
        available_time=user.available_time,
        desired_path=user.desired_path,
        departments=departments,
        directions=directions,
        social_links=[
            ApplicationSocialLinkOut(platform=row.platform, url=row.url)
            for row in social_rows
        ],
        personal_data_consent=bool(user.personal_data_consent),
        consent_policy_version=consent.policy_version if consent else None,
        application_status=user.application_status,
        photo_attached=bool(profile and profile.photo_file_id),
        photo_data_url=photo_data_url,
        created_at=user.created_at.isoformat(),
    )


@router.get("/applications", response_model=list[FullApplicationOut])
async def read_full_applications(
    _admin: User = Depends(require_application_admin),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
) -> list[FullApplicationOut]:
    """Return the complete registration questionnaire for Admin Mode.

    This route intentionally precedes app.api.v1.admin's legacy compact GET
    route in api_router. POST decision routes remain in the existing admin
    module; only the read model is upgraded here so the admin UI can review
    exactly what the participant submitted, including the attached photo.
    """
    rows = await session.scalars(
        select(User)
        .where(
            User.application_status.in_(
                [ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]
            ),
            User.is_archived.is_(False),
        )
        .order_by(User.created_at)
    )
    return [await _application_out(session, bot, user) for user in rows.all()]
