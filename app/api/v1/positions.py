from __future__ import annotations

import logging

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Office, PositionApplication, User
from app.services import office_management_service, position_management_service
from app.services.bot_notification_service import PrimaryAction, action_markup
from app.services.notification_service import notify_admins_once

logger = logging.getLogger(__name__)
router = APIRouter(tags=["positions"])


class PositionOut(BaseModel):
    id: int
    title: str
    description: str | None
    responsibilities: list[str]
    requirements: str | None
    expected_result: str | None
    workload: str | None
    application_deadline: str | None
    application_count: int
    default_term_days: int | None
    capacity: int | None
    occupied: int
    free_slots: int | None
    recruitment_mode: str


async def _to_position_out(session: AsyncSession, office: Office) -> PositionOut:
    occupied = await office_management_service.active_assignment_count(session, office.id)
    capacity = office.max_holders
    free_slots = None if capacity is None else max(0, capacity - occupied)
    kpi = office.kpi_template if isinstance(office.kpi_template, dict) else {}
    if not office.application_enabled:
        recruitment_mode = "closed"
    elif capacity is None:
        recruitment_mode = "manual"
    else:
        recruitment_mode = "auto"
    return PositionOut(
        id=office.id,
        title=office.title,
        description=office.description,
        responsibilities=list(office.responsibilities or []),
        requirements=office.requirements,
        expected_result=str(kpi.get("expected_result")) if kpi.get("expected_result") else None,
        workload=str(kpi.get("workload")) if kpi.get("workload") else None,
        application_deadline=(office.application_deadline.isoformat() if office.application_deadline else None),
        application_count=await position_management_service.application_count(session, office.id),
        default_term_days=office.default_term_days,
        capacity=capacity,
        occupied=occupied,
        free_slots=free_slots,
        recruitment_mode=recruitment_mode,
    )


@router.get("/positions", response_model=list[PositionOut])
async def read_open_positions(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PositionOut]:
    offices = await position_management_service.list_open_positions(session)
    return [await _to_position_out(session, office) for office in offices]


@router.get("/positions/{position_id}", response_model=PositionOut)
async def read_position(
    position_id: int,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PositionOut:
    office = await session.get(Office, position_id)
    if office is None or not office.is_active or not office.is_public:
        raise HTTPException(status_code=404, detail="position_not_found")
    return await _to_position_out(session, office)


class ApplicationSubmitIn(BaseModel):
    motivation: str
    relevant_experience: str = ""
    plan: str = ""
    availability: str = ""
    extra: str = ""


class MyApplicationOut(BaseModel):
    id: int
    office_id: int
    office_title: str
    status: str
    motivation: str | None
    plan: str | None
    availability: str | None
    submitted_at: str | None
    review_note: str | None


async def _to_my_application_out(
    session: AsyncSession, application: PositionApplication
) -> MyApplicationOut:
    office = await session.get(Office, application.office_id)
    return MyApplicationOut(
        id=application.id,
        office_id=application.office_id,
        office_title=office.title if office else "",
        status=application.status,
        motivation=application.motivation,
        plan=application.plan,
        availability=application.availability,
        submitted_at=application.submitted_at.isoformat() if application.submitted_at else None,
        review_note=application.review_note,
    )


def _admin_application_markup(settings: Settings, application_id: int):
    if not settings.effective_miniapp_url:
        return None
    return action_markup(
        PrimaryAction(
            label="Открыть в управлении ЭРА",
            web_app_url=f"{settings.effective_miniapp_url}#/admin?application={application_id}",
        )
    )


@router.post("/positions/{position_id}/applications", response_model=MyApplicationOut)
async def submit_position_application(
    position_id: int,
    payload: ApplicationSubmitIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> MyApplicationOut:
    office = await session.get(Office, position_id)
    if office is None or not office.is_active:
        raise HTTPException(status_code=404, detail="position_not_found")
    try:
        application = await position_management_service.submit_application(
            session,
            office=office,
            user=user,
            motivation=payload.motivation,
            relevant_experience=payload.relevant_experience,
            plan=payload.plan,
            availability=payload.availability,
            extra=payload.extra,
        )
    except position_management_service.PositionError as exc:
        status_code = 409 if exc.code in {"duplicate_application", "office_capacity_reached", "applications_closed"} else 422
        raise HTTPException(status_code=status_code, detail=exc.code) from exc

    # Commit business data before outbound delivery. The request-scoped
    # dependency will commit again harmlessly when it exits.
    await session.commit()

    if bot is not None:
        try:
            await notify_admins_once(
                bot,
                settings,
                f"Новая заявка на должность\n\n{office.title}\nЗаявка #{application.id}",
                delivery_key=f"admin:position_application:{application.id}:submitted",
                notification_type="position_application_submitted",
                reply_markup=_admin_application_markup(settings, application.id),
            )
        except Exception:
            logger.exception("Position application admin notification failed id=%s", application.id)

    return await _to_my_application_out(session, application)


@router.get("/me/position-applications", response_model=list[MyApplicationOut])
async def read_my_position_applications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MyApplicationOut]:
    applications = await position_management_service.list_my_applications(session, user.id)
    return [await _to_my_application_out(session, application) for application in applications]


@router.post("/me/position-applications/{application_id}/withdraw", response_model=MyApplicationOut)
async def withdraw_my_position_application(
    application_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyApplicationOut:
    application = await session.get(PositionApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application_not_found")
    try:
        await position_management_service.withdraw_application(session, application, user_id=user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except position_management_service.PositionError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return await _to_my_application_out(session, application)


class TeamOfficeHolderOut(BaseModel):
    user_id: int
    first_name: str
    last_name: str | None
    starts_at: str
    ends_at: str | None


class TeamOfficeOut(BaseModel):
    id: int
    title: str
    description: str | None
    holders: list[TeamOfficeHolderOut]
    is_vacant: bool
    application_enabled: bool


@router.get("/team", response_model=list[TeamOfficeOut])
async def read_team_directory(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TeamOfficeOut]:
    offices = await position_management_service.list_public_offices(session)
    out: list[TeamOfficeOut] = []
    for office in offices:
        rows = await office_management_service.list_assignments(session, office.id)
        out.append(
            TeamOfficeOut(
                id=office.id,
                title=office.title,
                description=office.description,
                holders=[
                    TeamOfficeHolderOut(
                        user_id=holder.id,
                        first_name=holder.first_name,
                        last_name=holder.last_name,
                        starts_at=assignment.starts_at.isoformat(),
                        ends_at=assignment.ends_at.isoformat() if assignment.ends_at else None,
                    )
                    for assignment, holder in rows
                ],
                is_vacant=(office.max_holders is not None and len(rows) < office.max_holders) or len(rows) == 0,
                application_enabled=office.application_enabled,
            )
        )
    return out


class PathCandidateSummaryOut(BaseModel):
    completed_projects: int
    tasks_completed_on_time: int
    tasks_completed_total: int
    on_time_rate: float | None
    events_attended: int
    past_offices: int


class PathHistoryEntryOut(BaseModel):
    office_title: str
    starts_at: str
    ends_at: str | None
    is_active: bool


class MyPathOut(BaseModel):
    participation_status: str
    summary: PathCandidateSummaryOut
    history: list[PathHistoryEntryOut]
    open_positions: list[PositionOut]


@router.get("/me/path", response_model=MyPathOut)
async def read_my_path(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MyPathOut:
    summary = await position_management_service.candidate_summary(session, user.id)
    history = await position_management_service.office_history(session, user.id)
    open_positions = await position_management_service.list_open_positions(session)
    return MyPathOut(
        participation_status=user.participation_status,
        summary=PathCandidateSummaryOut(
            completed_projects=summary.completed_projects,
            tasks_completed_on_time=summary.tasks_completed_on_time,
            tasks_completed_total=summary.tasks_completed_total,
            on_time_rate=summary.on_time_rate,
            events_attended=summary.events_attended,
            past_offices=summary.past_offices,
        ),
        history=[
            PathHistoryEntryOut(
                office_title=item.office_title,
                starts_at=item.starts_at.isoformat(),
                ends_at=item.ends_at.isoformat() if item.ends_at else None,
                is_active=item.is_active,
            )
            for item in history
        ],
        open_positions=[await _to_position_out(session, office) for office in open_positions],
    )
