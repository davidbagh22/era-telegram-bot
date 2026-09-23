from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database.recruitment_model_extensions  # noqa: F401
from app.database.models import Office, User, UserOffice
from app.services.audit_service import audit
from app.utils.constants import AppointmentType

RECRUITMENT_AUTO = "auto"
RECRUITMENT_MANUAL = "manual"
RECRUITMENT_CLOSED = "closed"
RECRUITMENT_MODES = {RECRUITMENT_AUTO, RECRUITMENT_MANUAL, RECRUITMENT_CLOSED}


class OfficeCapacityReached(HTTPException):
    """409 raised when a locked Office no longer has a free assignment slot."""

    def __init__(self) -> None:
        super().__init__(status_code=409, detail="office_capacity_reached")


def normalize_recruitment_mode(value: str | None) -> str:
    mode = (value or RECRUITMENT_CLOSED).strip().lower()
    if mode not in RECRUITMENT_MODES:
        raise ValueError("invalid_recruitment_mode")
    return mode


async def list_offices(session: AsyncSession, *, include_inactive: bool = False) -> list[Office]:
    conditions = [] if include_inactive else [Office.is_active.is_(True)]
    return list((await session.scalars(select(Office).where(*conditions).order_by(Office.sort_order, Office.title))).all())


async def active_assignment_count(session: AsyncSession, office_id: int) -> int:
    return int(await session.scalar(select(func.count(UserOffice.id)).where(UserOffice.office_id == office_id, UserOffice.is_active.is_(True))) or 0)


async def reconcile_office_vacancy(session: AsyncSession, office: Office) -> bool:
    mode = normalize_recruitment_mode(getattr(office, "recruitment_mode", None))
    occupied = await active_assignment_count(session, office.id)
    capacity = office.max_holders
    has_slot = capacity is None or occupied < max(0, capacity)
    if mode == RECRUITMENT_CLOSED:
        office.application_enabled = False
    elif mode == RECRUITMENT_AUTO:
        office.application_enabled = bool(office.is_active and office.is_public and has_slot)
    elif not has_slot:
        office.application_enabled = False
    return bool(office.application_enabled)


async def create_office(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    permission_template: list[str] | None = None,
    scope_type: str | None = None,
    department_id: int | None = None,
    direction_id: int | None = None,
    application_enabled: bool = False,
    application_deadline=None,
    requirements: str | None = None,
    default_term_days: int | None = None,
    probation_days: int | None = None,
    is_public: bool = True,
    max_holders: int | None = None,
    recruitment_mode: str = RECRUITMENT_CLOSED,
    responsibilities: list[str] | None = None,
    expected_result: str | None = None,
    workload: str | None = None,
) -> Office:
    mode = normalize_recruitment_mode(recruitment_mode)
    if max_holders is not None and max_holders < 1:
        raise ValueError("invalid_capacity")
    office = Office(
        title=title,
        description=description,
        permission_template=permission_template or [],
        scope_type=scope_type or "community",
        department_id=department_id,
        direction_id=direction_id,
        application_enabled=(application_enabled if mode == RECRUITMENT_MANUAL else False),
        application_deadline=application_deadline,
        requirements=requirements,
        default_term_days=default_term_days,
        probation_days=probation_days,
        is_public=is_public,
        max_holders=max_holders,
        responsibilities=responsibilities or [],
        recruitment_mode=mode,
        expected_result=expected_result,
        workload=workload,
    )
    session.add(office)
    await session.flush()
    await reconcile_office_vacancy(session, office)
    return office


async def update_office(
    session: AsyncSession,
    office: Office,
    *,
    title: str | None = None,
    description: str | None = None,
    permission_template: list[str] | None = None,
    application_enabled: bool | None = None,
    application_deadline=None,
    requirements: str | None = None,
    default_term_days: int | None = None,
    probation_days: int | None = None,
    is_public: bool | None = None,
    max_holders: int | None = None,
    set_max_holders: bool = False,
    recruitment_mode: str | None = None,
    responsibilities: list[str] | None = None,
    expected_result: str | None = None,
    set_expected_result: bool = False,
    workload: str | None = None,
    set_workload: bool = False,
) -> Office:
    if title is not None:
        office.title = title
    if description is not None:
        office.description = description
    if permission_template is not None:
        office.permission_template = permission_template
    if application_deadline is not None:
        office.application_deadline = application_deadline
    if requirements is not None:
        office.requirements = requirements
    if default_term_days is not None:
        office.default_term_days = default_term_days
    if probation_days is not None:
        office.probation_days = probation_days
    if is_public is not None:
        office.is_public = is_public
    if set_max_holders:
        if max_holders is not None and max_holders < 1:
            raise ValueError("invalid_capacity")
        office.max_holders = max_holders
    if recruitment_mode is not None:
        office.recruitment_mode = normalize_recruitment_mode(recruitment_mode)
    if responsibilities is not None:
        office.responsibilities = responsibilities
    if set_expected_result:
        office.expected_result = expected_result
    if set_workload:
        office.workload = workload
    mode = normalize_recruitment_mode(getattr(office, "recruitment_mode", None))
    if application_enabled is not None and mode == RECRUITMENT_MANUAL:
        office.application_enabled = application_enabled
    await reconcile_office_vacancy(session, office)
    return office


async def list_assignments(session: AsyncSession, office_id: int) -> list[tuple[UserOffice, User]]:
    result = await session.execute(select(UserOffice, User).join(User, User.id == UserOffice.user_id).where(UserOffice.office_id == office_id, UserOffice.is_active.is_(True)))
    return list(result.all())


async def reconcile_all_vacancies(session: AsyncSession) -> dict[str, int]:
    offices = list((await session.scalars(select(Office))).all())
    opened = closed = unchanged = 0
    for office in offices:
        before = office.application_enabled
        after = await reconcile_office_vacancy(session, office)
        if after == before:
            unchanged += 1
        elif after:
            opened += 1
        else:
            closed += 1
    await session.flush()
    return {"opened": opened, "closed": closed, "unchanged": unchanged, "total": len(offices)}


async def search_assignable_users(session: AsyncSession, query: str, *, limit: int = 8) -> list[User]:
    stripped = query.strip().lstrip("@")
    conditions = [User.first_name.ilike(f"%{stripped}%"), User.last_name.ilike(f"%{stripped}%"), User.username.ilike(f"%{stripped}%")]
    if stripped.isdigit():
        conditions.append(User.telegram_id == int(stripped))
    return list((await session.scalars(select(User).where(or_(*conditions)).limit(limit))).all())


async def assign_office(
    session: AsyncSession,
    *,
    office_id: int,
    user_id: int,
    appointed_by_id: int,
    appointment_type: str = AppointmentType.REGULAR,
    starts_at: date | None = None,
    ends_at: date | None = None,
    probation_ends_at: date | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> UserOffice | None:
    office = await session.scalar(select(Office).where(Office.id == office_id).with_for_update())
    if office is None or not office.is_active:
        return None
    existing = await session.scalar(select(UserOffice).where(UserOffice.office_id == office_id, UserOffice.user_id == user_id, UserOffice.is_active.is_(True)))
    if existing is not None:
        return None
    occupied = await active_assignment_count(session, office_id)
    if office.max_holders is not None and occupied >= max(0, office.max_holders):
        office.application_enabled = False
        raise OfficeCapacityReached()
    assignment = UserOffice(
        office_id=office_id,
        user_id=user_id,
        appointed_by=appointed_by_id,
        appointment_type=appointment_type,
        starts_at=starts_at or date.today(),
        ends_at=ends_at,
        probation_ends_at=probation_ends_at,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    session.add(assignment)
    await session.flush()
    await reconcile_office_vacancy(session, office)
    return assignment


def remove_assignment(assignment: UserOffice, *, ended_by_id: int | None = None, reason: str | None = None) -> None:
    assignment.is_active = False
    assignment.ends_at = date.today()
    if ended_by_id is not None:
        assignment.ended_by = ended_by_id
    if reason is not None:
        assignment.end_reason = reason[:255]


async def delete_office(session: AsyncSession, office: Office, *, actor_id: int | None) -> int:
    active_assignments = list((await session.scalars(select(UserOffice).where(UserOffice.office_id == office.id, UserOffice.is_active.is_(True)))).all())
    for assignment in active_assignments:
        remove_assignment(assignment)
    office.is_active = False
    office.application_enabled = False
    office.recruitment_mode = RECRUITMENT_CLOSED
    await audit(
        session,
        actor_id=actor_id,
        action="office.deleted",
        entity_type="office",
        entity_id=office.id,
        old_value={"title": office.title, "active_assignments": len(active_assignments)},
        new_value={"is_active": False, "recruitment_mode": RECRUITMENT_CLOSED},
    )
    return len(active_assignments)
