from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.admin_analytics_service import build_analytics_payload
from app.services.admin_dashboard_service import has_dashboard_access

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics-details"])

AnalyticsDetailSection = Literal["users", "events", "projects", "contacts", "goals"]


async def require_dashboard_access(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not has_dashboard_access(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class AnalyticsDetailItemOut(BaseModel):
    id: int
    title: str
    subtitle: str | None = None
    status: str | None = None


class AnalyticsDetailsOut(BaseModel):
    section: AnalyticsDetailSection
    total: int
    items: list[AnalyticsDetailItemOut]


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


@router.get("/details/{section}", response_model=AnalyticsDetailsOut)
async def read_analytics_details(
    section: AnalyticsDetailSection,
    _admin: User = Depends(require_dashboard_access),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsDetailsOut:
    data = await build_analytics_payload(session)

    if section == "users":
        items = [
            AnalyticsDetailItemOut(
                id=user.id,
                title=" ".join(part for part in [user.first_name, user.last_name] if part).strip() or f"Участник #{user.id}",
                subtitle=" · ".join(
                    part
                    for part in [
                        _text(user.role),
                        f"@{user.username}" if user.username else None,
                    ]
                    if part
                )
                or None,
                status=_text(user.application_status),
            )
            for user in data.users
        ]
    elif section == "events":
        items = [
            AnalyticsDetailItemOut(
                id=event.id,
                title=event.title,
                subtitle=" · ".join(
                    part
                    for part in [
                        event.event_date.isoformat() if event.event_date else None,
                        event.event_time.strftime("%H:%M") if event.event_time else None,
                    ]
                    if part
                )
                or None,
                status=_text(event.status),
            )
            for event in data.events
        ]
    elif section == "projects":
        items = [
            AnalyticsDetailItemOut(
                id=project.id,
                title=project.title,
                subtitle=project.created_at.date().isoformat() if project.created_at else None,
                status=_text(project.status),
            )
            for project in data.projects
        ]
    elif section == "contacts":
        items = [
            AnalyticsDetailItemOut(
                id=contact.id,
                title=contact.organization_name,
                subtitle=None,
                status="active",
            )
            for contact in data.contacts
        ]
    else:
        items = [
            AnalyticsDetailItemOut(
                id=goal.id,
                title=goal.title,
                subtitle=f"{goal.scope_name} · {goal.current_value}/{goal.target_value}",
                status=goal.status,
            )
            for goal in data.goals
        ]

    return AnalyticsDetailsOut(section=section, total=len(items), items=items)
