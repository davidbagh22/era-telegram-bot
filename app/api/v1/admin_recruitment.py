from __future__ import annotations

from datetime import datetime
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.recruitment_model_extensions  # noqa: F401
from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import Office, PortfolioItem, PositionApplication, User, UserOffice
from app.services import office_management_service, position_management_service
from app.services.authorization_service import can_manage_people
from app.services.notification_service import safe_send
from app.services.points_service import total_points
from app.utils.constants import STATUS_LABELS

router = APIRouter(prefix="/admin/recruitment", tags=["admin-recruitment"])


async def require_recruitment_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_people(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="people_manage_required")
    return user


async def rate_limit_recruitment(request: Request) -> None:
    await enforce_rate_limit(
        request,
        key_prefix="admin_recruitment_action",
        limit=30,
        window_seconds=60,
    )


class AssignmentOut(BaseModel):
    assignment_id: int
    user_id: int
    user_name: str
    starts_at: str
    ends_at: str | None


class RecruitmentOfficeOut(BaseModel):
    id: int
    title: str
    description: str | None
    responsibilities: list[str]
    requirements: str | None
    expected_result: str | None
    workload: str | None
    capacity: int | None
    occupied: int
    free_slots: int | None
    recruitment_mode: str
    application_enabled: bool
    application_deadline: str | None
    is_public: bool
    application_count: int
    assignments: list[AssignmentOut]


async def _office_out(session: AsyncSession, office: Office) -> RecruitmentOfficeOut:
    rows = await office_management_service.list_assignments(session, office.id)
    occupied = len(rows)
    capacity = office.max_holders
    return RecruitmentOfficeOut(
        id=office.id,
        title=office.title,
        description=office.description,
        responsibilities=list(office.responsibilities or []),
        requirements=office.requirements,
        expected_result=getattr(office, "expected_result", None),
        workload=getattr(office, "workload", None),
        capacity=capacity,
        occupied=occupied,
        free_slots=None if capacity is None else max(0, capacity - occupied),
        recruitment_mode=office_management_service.normalize_recruitment_mode(getattr(office, "recruitment_mode", None)),
        application_enabled=bool(office.application_enabled),
        application_deadline=office.application_deadline.isoformat() if office.application_deadline else None,
        is_public=office.is_public,
        application_count=await position_management_service.application_count(session, office.id),
        assignments=[
            AssignmentOut(
                assignment_id=assignment.id,
                user_id=holder.id,
                user_name=f"{holder.first_name} {holder.last_name or ''}".strip(),
                starts_at=assignment.starts_at.isoformat(),
                ends_at=assignment.ends_at.isoformat() if assignment.ends_at else None,
            )
            for assignment, holder in rows
        ],
    )


@router.get("/offices", response_model=list[RecruitmentOfficeOut])
async def list_recruitment_offices(
    _manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
) -> list[RecruitmentOfficeOut]:
    offices = await office_management_service.list_offices(session)
    return [await _office_out(session, office) for office in offices]


class RecruitmentSettingsIn(BaseModel):
    recruitment_mode: Literal["auto", "manual", "closed"]
    capacity: int | None = None
    application_enabled: bool | None = None
    responsibilities: list[str] | None = None
    requirements: str | None = None
    expected_result: str | None = None
    workload: str | None = None
    application_deadline: str | None = None
    is_public: bool | None = None


@router.post("/offices/{office_id}", response_model=RecruitmentOfficeOut)
async def update_recruitment_office(
    office_id: int,
    payload: RecruitmentSettingsIn,
    _manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(rate_limit_recruitment),
) -> RecruitmentOfficeOut:
    office = await session.get(Office, office_id)
    if office is None or not office.is_active:
        raise HTTPException(status_code=404, detail="office_not_found")
    deadline = None
    if payload.application_deadline:
        try:
            deadline = datetime.fromisoformat(payload.application_deadline)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_deadline") from exc
    try:
        await office_management_service.update_office(
            session,
            office,
            recruitment_mode=payload.recruitment_mode,
            max_holders=payload.capacity,
            set_max_holders=True,
            application_enabled=payload.application_enabled,
            responsibilities=payload.responsibilities,
            requirements=payload.requirements,
            expected_result=payload.expected_result,
            set_expected_result=True,
            workload=payload.workload,
            set_workload=True,
            application_deadline=deadline,
            is_public=payload.is_public,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _office_out(session, office)


class CandidateFactsOut(BaseModel):
    participation_status: str
    participation_label: str
    current_offices: list[str]
    completed_projects: int
    tasks_completed_on_time: int
    tasks_completed_total: int
    on_time_rate: float | None
    events_attended: int
    portfolio_items: int
    points: int


class PositionApplicationAdminOut(BaseModel):
    id: int
    office_id: int
    office_title: str
    user_id: int
    user_name: str
    status: str
    motivation: str | None
    relevant_experience: str | None
    plan: str | None
    availability: str | None
    attachment_url: str | None
    submitted_at: str | None
    review_note: str | None
    facts: CandidateFactsOut


async def _application_out(session: AsyncSession, application: PositionApplication) -> PositionApplicationAdminOut:
    office = await session.get(Office, application.office_id)
    user = await session.get(User, application.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="applicant_not_found")
    summary = await position_management_service.candidate_summary(session, user.id)
    current_offices = list(
        (
            await session.scalars(
                select(Office.title)
                .join(UserOffice, UserOffice.office_id == Office.id)
                .where(UserOffice.user_id == user.id, UserOffice.is_active.is_(True))
                .order_by(Office.title)
            )
        ).all()
    )
    portfolio_items = int(
        await session.scalar(select(func.count(PortfolioItem.id)).where(PortfolioItem.user_id == user.id)) or 0
    )
    points = await total_points(session, user.id)
    return PositionApplicationAdminOut(
        id=application.id,
        office_id=application.office_id,
        office_title=office.title if office else "",
        user_id=user.id,
        user_name=f"{user.first_name} {user.last_name or ''}".strip(),
        status=application.status,
        motivation=application.motivation,
        relevant_experience=getattr(application, "relevant_experience", None),
        plan=application.plan,
        availability=application.availability,
        attachment_url=getattr(application, "attachment_url", None),
        submitted_at=application.submitted_at.isoformat() if application.submitted_at else None,
        review_note=application.review_note,
        facts=CandidateFactsOut(
            participation_status=user.participation_status,
            participation_label=STATUS_LABELS.get(user.participation_status, str(user.participation_status)),
            current_offices=current_offices,
            completed_projects=summary.completed_projects,
            tasks_completed_on_time=summary.tasks_completed_on_time,
            tasks_completed_total=summary.tasks_completed_total,
            on_time_rate=summary.on_time_rate,
            events_attended=summary.events_attended,
            portfolio_items=portfolio_items,
            points=points,
        ),
    )


@router.get("/offices/{office_id}/applications", response_model=list[PositionApplicationAdminOut])
async def list_role_applications(
    office_id: int,
    _manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
) -> list[PositionApplicationAdminOut]:
    applications = await position_management_service.list_applications_for_office(session, office_id)
    return [await _application_out(session, application) for application in applications]


@router.get("/applications/{application_id}", response_model=PositionApplicationAdminOut)
async def get_role_application(
    application_id: int,
    _manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
) -> PositionApplicationAdminOut:
    application = await session.get(PositionApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    return await _application_out(session, application)


class ApplicationDecisionIn(BaseModel):
    status: Literal["reviewing", "needs_info", "interview", "reserve", "approved", "rejected"]
    note: str = ""


@router.post("/applications/{application_id}/decision", response_model=PositionApplicationAdminOut)
async def decide_role_application(
    application_id: int,
    payload: ApplicationDecisionIn,
    manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(rate_limit_recruitment),
) -> PositionApplicationAdminOut:
    application = await session.get(PositionApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    try:
        await position_management_service.review_application(
            session,
            application,
            status=payload.status,
            reviewer_id=manager.id,
            note=payload.note or None,
        )
    except position_management_service.PositionError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    await session.commit()
    if bot is not None:
        applicant = await session.get(User, application.user_id)
        office = await session.get(Office, application.office_id)
        if applicant is not None:
            labels = {
                "reviewing": "Заявка взята в рассмотрение",
                "needs_info": "По заявке нужна дополнительная информация",
                "interview": "Следующий этап — интервью",
                "reserve": "Заявка перенесена в резерв",
                "approved": "Заявка одобрена",
                "rejected": "Заявка не прошла отбор",
            }
            text = f"{labels[payload.status]}\nРоль: {office.title if office else 'ЭРА'}"
            if payload.note.strip():
                text += f"\n\nКомментарий: {payload.note.strip()}"
            await safe_send(bot, applicant.telegram_id, text)
    return await _application_out(session, application)


class AppointIn(BaseModel):
    appointment_type: Literal["regular", "acting"] = "regular"
    ends_at: str | None = None


@router.post("/applications/{application_id}/appoint", response_model=PositionApplicationAdminOut)
async def appoint_role_application(
    application_id: int,
    payload: AppointIn,
    manager: User = Depends(require_recruitment_manager),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(rate_limit_recruitment),
) -> PositionApplicationAdminOut:
    application = await session.get(PositionApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    office = await session.get(Office, application.office_id)
    if office is None:
        raise HTTPException(status_code=404, detail="office_not_found")
    ends_at = None
    if payload.ends_at:
        try:
            ends_at = datetime.fromisoformat(payload.ends_at).date()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_ends_at") from exc
    try:
        await position_management_service.appoint_from_application(
            session,
            application,
            office,
            appointed_by_id=manager.id,
            appointment_type=payload.appointment_type,
            ends_at=ends_at,
        )
    except position_management_service.PositionError as exc:
        status_code = 409 if exc.code in {"office_capacity_reached", "already_appointed"} else 422
        raise HTTPException(status_code=status_code, detail=exc.code) from exc
    await session.commit()
    applicant = await session.get(User, application.user_id)
    if bot is not None and applicant is not None:
        await safe_send(bot, applicant.telegram_id, f"Вы назначены на роль «{office.title}».\n\nРабочие инструменты уже доступны в ЭРА.")
    return await _application_out(session, application)
