from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services import data_rights_service
from app.services.growth_service import GrowthProgress, growth_progress_for
from app.services.portfolio_service import build_portfolio_data
from app.services.resume_service import build_era_resume

router = APIRouter(prefix="/profile", tags=["profile"])


class GrowthProgressOut(BaseModel):
    level: str
    label: str
    level_index: int
    level_count: int


class PortfolioEntryOut(BaseModel):
    title: str
    description: str = ""
    status: str = ""
    date_label: str = ""
    category: str = ""
    file_id: str | None = None
    url: str | None = None
    entity_kind: str | None = None
    entity_id: int | None = None


class ProfileOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    role: str
    growth: GrowthProgressOut
    full_name: str
    participation_status: str
    departments: list[str]
    directions: list[str]
    period: str
    city: str
    email: str
    education_work: str
    occupation: str
    experience: str
    motivation: str
    skills: list[str]
    stats: dict[str, int]
    projects: list[PortfolioEntryOut]
    events: list[PortfolioEntryOut]
    tasks: list[PortfolioEntryOut]
    volunteer: list[PortfolioEntryOut]
    leadership: list[PortfolioEntryOut]
    badges: list[PortfolioEntryOut]
    certificates: list[PortfolioEntryOut]
    recommendations: list[PortfolioEntryOut]


def _growth_out(growth: GrowthProgress) -> GrowthProgressOut:
    return GrowthProgressOut(level=growth.level, label=growth.label, level_index=growth.level_index, level_count=growth.level_count)


@router.get("", response_model=ProfileOut)
async def read_profile(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ProfileOut:
    portfolio = await build_portfolio_data(session, user)
    growth = growth_progress_for(user)
    return ProfileOut(
        id=user.id, telegram_id=user.telegram_id, first_name=user.first_name, last_name=user.last_name,
        role=user.role, growth=_growth_out(growth), full_name=portfolio.full_name,
        participation_status=portfolio.participation_status, departments=portfolio.departments,
        directions=portfolio.directions, period=portfolio.period, city=portfolio.city, email=portfolio.email,
        education_work=portfolio.education_work, occupation=portfolio.occupation, experience=portfolio.experience,
        motivation=portfolio.motivation, skills=portfolio.skills, stats=portfolio.stats,
        projects=[PortfolioEntryOut(**asdict(item)) for item in portfolio.projects],
        events=[PortfolioEntryOut(**asdict(item)) for item in portfolio.events],
        tasks=[PortfolioEntryOut(**asdict(item)) for item in portfolio.tasks],
        volunteer=[PortfolioEntryOut(**asdict(item)) for item in portfolio.volunteer],
        leadership=[PortfolioEntryOut(**asdict(item)) for item in portfolio.leadership],
        badges=[PortfolioEntryOut(**asdict(item)) for item in portfolio.badges],
        certificates=[PortfolioEntryOut(**asdict(item)) for item in portfolio.certificates],
        recommendations=[PortfolioEntryOut(**asdict(item)) for item in portfolio.recommendations],
    )


@router.get("/resume.pdf")
async def read_profile_resume(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Response:
    portfolio = await build_portfolio_data(session, user)
    pdf_bytes = build_era_resume(portfolio)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="ERA_portfolio_{user.id}.pdf"'})


@router.get("/export")
async def export_profile_data(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Response:
    data = await data_rights_service.export_user_data(session, user)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(content=body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="ERA_data_export_{user.id}.json"'})


class DeletionRequestIn(BaseModel):
    note: str | None = None


class DeletionRequestOut(BaseModel):
    id: int
    status: str
    created_at: str


@router.post("/delete-request", response_model=DeletionRequestOut)
async def request_account_deletion(payload: DeletionRequestIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> DeletionRequestOut:
    request = await data_rights_service.request_deletion(session, user, payload.note)
    return DeletionRequestOut(id=request.id, status=request.status, created_at=request.created_at.isoformat())
