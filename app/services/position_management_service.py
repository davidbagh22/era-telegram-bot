from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventRegistration,
    Office,
    PositionApplication,
    Project,
    ProjectMember,
    Task,
    User,
    UserOffice,
)
from app.services import office_management_service
from app.services.audit_service import audit
from app.services.leadership_permission_service import detect_appointment_conflicts
from app.services.leadership_recurring_service import sync_recurring_tasks
from app.utils.constants import (
    PositionApplicationStatus,
    ProjectStatus,
    RegistrationStatus,
    TaskStatus,
)

# Leadership OS ToR sections 18-23: vacancies -> applications -> decision ->
# appoint. Reuses office_management_service.assign_office/remove_assignment
# for the actual UserOffice mutation (section 23's "автоматически
# создаёт/активирует UserOffice") rather than duplicating that logic.

_OPEN_STATUSES = {
    PositionApplicationStatus.DRAFT,
    PositionApplicationStatus.SUBMITTED,
    PositionApplicationStatus.REVIEWING,
    PositionApplicationStatus.INTERVIEW,
    PositionApplicationStatus.RESERVE,
}


def _is_past(deadline: datetime | None, *, now: datetime) -> bool:
    """SQLite (used in tests, and by aiosqlite generally) round-trips
    DateTime(timezone=True) columns as naive UTC, so a value freshly
    assigned in Python (tz-aware) and one just reloaded from the DB (naive)
    aren't directly comparable -- strip tzinfo from both before comparing,
    since everything in this codebase is UTC already."""
    if deadline is None:
        return False
    return deadline.replace(tzinfo=None) < now.replace(tzinfo=None)


_REVIEW_TRANSITIONS = {
    PositionApplicationStatus.REVIEWING,
    PositionApplicationStatus.INTERVIEW,
    PositionApplicationStatus.RESERVE,
    PositionApplicationStatus.APPROVED,
    PositionApplicationStatus.REJECTED,
}


class PositionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def list_open_positions(session: AsyncSession) -> list[Office]:
    """Public vacancy listing (ToR section 18) -- open for applications,
    not just any office."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.scalars(
            select(Office)
            .where(
                Office.is_active.is_(True),
                Office.is_public.is_(True),
                Office.application_enabled.is_(True),
                or_(Office.application_deadline.is_(None), Office.application_deadline >= now),
            )
            .order_by(Office.sort_order, Office.title)
        )
    ).all()
    return list(rows)


async def list_public_offices(session: AsyncSession) -> list[Office]:
    """"Команда" directory (ToR section 9): every publicly-listed office,
    occupied or vacant, regardless of whether it's currently accepting
    applications."""
    return list(
        (
            await session.scalars(
                select(Office)
                .where(Office.is_active.is_(True), Office.is_public.is_(True))
                .order_by(Office.sort_order, Office.title)
            )
        ).all()
    )


async def application_count(session: AsyncSession, office_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PositionApplication)
            .where(
                PositionApplication.office_id == office_id,
                PositionApplication.status != PositionApplicationStatus.WITHDRAWN,
            )
        )
        or 0
    )


async def list_my_applications(session: AsyncSession, user_id: int) -> list[PositionApplication]:
    return list(
        (
            await session.scalars(
                select(PositionApplication)
                .where(PositionApplication.user_id == user_id)
                .order_by(PositionApplication.created_at.desc())
            )
        ).all()
    )


async def list_applications_for_office(
    session: AsyncSession, office_id: int
) -> list[PositionApplication]:
    return list(
        (
            await session.scalars(
                select(PositionApplication)
                .where(PositionApplication.office_id == office_id)
                .order_by(PositionApplication.created_at.desc())
            )
        ).all()
    )


async def list_all_applications(session: AsyncSession, *, limit: int = 1000) -> list[PositionApplication]:
    """Org-wide listing for the Leadership OS export (ToR section 80)."""
    return list(
        (
            await session.scalars(
                select(PositionApplication).order_by(PositionApplication.created_at.desc()).limit(limit)
            )
        ).all()
    )


async def submit_application(
    session: AsyncSession,
    *,
    office: Office,
    user: User,
    motivation: str,
    plan: str | None,
    availability: str | None,
) -> PositionApplication:
    if not office.is_active or not office.application_enabled:
        raise PositionError("applications_closed")
    if _is_past(office.application_deadline, now=datetime.now(timezone.utc)):
        raise PositionError("deadline_passed")
    existing = await session.scalar(
        select(PositionApplication).where(
            PositionApplication.office_id == office.id,
            PositionApplication.user_id == user.id,
            PositionApplication.status.in_(_OPEN_STATUSES),
        )
    )
    if existing is not None:
        raise PositionError("duplicate_application")
    already_holds = await session.scalar(
        select(UserOffice).where(
            UserOffice.office_id == office.id,
            UserOffice.user_id == user.id,
            UserOffice.is_active.is_(True),
        )
    )
    if already_holds is not None:
        raise PositionError("already_appointed")
    if not motivation.strip():
        raise PositionError("motivation_required")

    now = datetime.now(timezone.utc)
    application = PositionApplication(
        office_id=office.id,
        user_id=user.id,
        status=PositionApplicationStatus.SUBMITTED,
        motivation=motivation.strip()[:4000],
        plan=(plan or "").strip()[:4000] or None,
        availability=(availability or "").strip()[:100] or None,
        submitted_at=now,
    )
    session.add(application)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="position_application.submitted",
        entity_type="position_application",
        entity_id=application.id,
        old_value=None,
        new_value={"office_id": office.id, "status": application.status},
    )
    return application


async def withdraw_application(
    session: AsyncSession, application: PositionApplication, *, user_id: int
) -> None:
    if application.user_id != user_id:
        raise PermissionError("not_owner")
    if application.status not in _OPEN_STATUSES:
        raise PositionError("not_withdrawable")
    application.status = PositionApplicationStatus.WITHDRAWN
    await audit(
        session,
        actor_id=user_id,
        action="position_application.withdrawn",
        entity_type="position_application",
        entity_id=application.id,
        old_value=None,
        new_value={"status": application.status},
    )


async def review_application(
    session: AsyncSession,
    application: PositionApplication,
    *,
    status: str,
    reviewer_id: int,
    note: str | None = None,
) -> PositionApplication:
    if status not in _REVIEW_TRANSITIONS:
        raise PositionError("invalid_status")
    if application.status in (
        PositionApplicationStatus.WITHDRAWN,
        PositionApplicationStatus.APPOINTED,
    ):
        raise PositionError("already_final")
    application.status = status
    application.reviewed_by = reviewer_id
    application.reviewed_at = datetime.now(timezone.utc)
    if note is not None:
        application.review_note = note.strip()[:2000] or None
    await audit(
        session,
        actor_id=reviewer_id,
        action="position_application.reviewed",
        entity_type="position_application",
        entity_id=application.id,
        old_value=None,
        new_value={"status": status},
    )
    return application


@dataclass(frozen=True, slots=True)
class AppointmentResult:
    assignment: UserOffice
    conflict_warnings: list[str]


async def appoint_from_application(
    session: AsyncSession,
    application: PositionApplication,
    office: Office,
    *,
    appointed_by_id: int,
    appointment_type: str = "regular",
    starts_at: date | None = None,
    ends_at: date | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
) -> AppointmentResult:
    """ToR section 23: approve + appoint in one action -- creates the
    UserOffice, flips the application to 'appointed', and returns
    non-blocking conflict warnings (section 28) for the caller to surface."""
    if application.office_id != office.id:
        raise PositionError("office_mismatch")
    if application.status == PositionApplicationStatus.APPOINTED:
        raise PositionError("already_appointed")

    resolved_starts_at = starts_at or date.today()
    resolved_ends_at = ends_at
    probation_ends_at = None
    if resolved_ends_at is None and office.default_term_days:
        resolved_ends_at = resolved_starts_at + timedelta(days=office.default_term_days)
    if office.probation_days:
        probation_ends_at = resolved_starts_at + timedelta(days=office.probation_days)

    assignment = await office_management_service.assign_office(
        session,
        office_id=office.id,
        user_id=application.user_id,
        appointed_by_id=appointed_by_id,
        appointment_type=appointment_type,
        starts_at=resolved_starts_at,
        ends_at=resolved_ends_at,
        probation_ends_at=probation_ends_at,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if assignment is None:
        raise PositionError("already_appointed")

    application.status = PositionApplicationStatus.APPOINTED
    application.reviewed_by = appointed_by_id
    application.reviewed_at = datetime.now(timezone.utc)

    # ToR section 23 item 9: appointment activates recurring responsibilities
    # automatically -- one Task per active template for the current period.
    await sync_recurring_tasks(session, assignment, today=resolved_starts_at)

    await audit(
        session,
        actor_id=appointed_by_id,
        action="position_application.appointed",
        entity_type="position_application",
        entity_id=application.id,
        old_value=None,
        new_value={"office_id": office.id, "user_office_id": assignment.id},
    )

    warnings = await detect_appointment_conflicts(session, application.user_id)
    return AppointmentResult(assignment=assignment, conflict_warnings=warnings)


async def end_appointment(
    session: AsyncSession,
    assignment: UserOffice,
    *,
    ended_by_id: int,
    reason: str | None = None,
) -> None:
    office_management_service.remove_assignment(assignment, ended_by_id=ended_by_id, reason=reason)
    await audit(
        session,
        actor_id=ended_by_id,
        action="appointment.ended",
        entity_type="user_office",
        entity_id=assignment.id,
        old_value=None,
        new_value={"reason": reason},
    )


async def extend_appointment(
    session: AsyncSession, assignment: UserOffice, *, new_ends_at: date, actor_id: int
) -> None:
    assignment.ends_at = new_ends_at
    await audit(
        session,
        actor_id=actor_id,
        action="appointment.extended",
        entity_type="user_office",
        entity_id=assignment.id,
        old_value=None,
        new_value={"ends_at": new_ends_at.isoformat()},
    )


# --- Objective candidate summary (ToR section 21) ---------------------------
# Deliberately excludes My Vector / any subjective assessment data (section
# 22/50) -- every field here is a plain count from an existing source table.


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    completed_projects: int
    tasks_completed_on_time: int
    tasks_completed_total: int
    on_time_rate: float | None
    events_attended: int
    past_offices: int


async def candidate_summary(session: AsyncSession, user_id: int) -> CandidateSummary:
    completed_projects = int(
        await session.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user_id, Project.status == ProjectStatus.COMPLETED)
        )
        or 0
    )
    tasks_completed_total = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.assignee_id == user_id, Task.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    tasks_completed_on_time = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assignee_id == user_id,
                Task.status == TaskStatus.COMPLETED,
                Task.updated_at <= Task.deadline,
            )
        )
        or 0
    )
    on_time_rate = (
        round(tasks_completed_on_time / tasks_completed_total * 100, 1)
        if tasks_completed_total
        else None
    )
    events_attended = int(
        await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .join(Event, Event.id == EventRegistration.event_id)
            .where(
                EventRegistration.user_id == user_id,
                EventRegistration.status == RegistrationStatus.ATTENDED,
            )
        )
        or 0
    )
    past_offices = int(
        await session.scalar(
            select(func.count())
            .select_from(UserOffice)
            .where(UserOffice.user_id == user_id, UserOffice.is_active.is_(False))
        )
        or 0
    )
    return CandidateSummary(
        completed_projects=completed_projects,
        tasks_completed_on_time=tasks_completed_on_time,
        tasks_completed_total=tasks_completed_total,
        on_time_rate=on_time_rate,
        events_attended=events_attended,
        past_offices=past_offices,
    )


# --- Progression / "Мой путь" / cadre reserve (ToR sections 76-78) ---------
# Rule-based thresholds only -- no composite/psychological score (section
# 105 explicitly forbids a "Candidate Score"). Each suggested role is a
# plain checklist match the admin still has to act on manually (section 76:
# "Не назначать автоматически").

_CURATOR_MIN_TASKS = 5
_CURATOR_MIN_ON_TIME_RATE = 70.0
_PROJECT_LEAD_MIN_PROJECTS = 1
_LEADER_MIN_PAST_OFFICES = 1


def suggested_roles(summary: CandidateSummary) -> list[str]:
    roles: list[str] = []
    if (
        summary.tasks_completed_total >= _CURATOR_MIN_TASKS
        and (summary.on_time_rate or 0) >= _CURATOR_MIN_ON_TIME_RATE
    ):
        roles.append("Куратор")
    if summary.completed_projects >= _PROJECT_LEAD_MIN_PROJECTS:
        roles.append("Руководитель проекта")
    if summary.past_offices >= _LEADER_MIN_PAST_OFFICES:
        roles.append("Лидер")
    return roles


@dataclass(frozen=True, slots=True)
class OfficeHistoryEntry:
    office_title: str
    starts_at: date
    ends_at: date | None
    is_active: bool


async def office_history(session: AsyncSession, user_id: int) -> list[OfficeHistoryEntry]:
    rows = (
        await session.execute(
            select(UserOffice, Office)
            .join(Office, Office.id == UserOffice.office_id)
            .where(UserOffice.user_id == user_id)
            .order_by(UserOffice.starts_at.desc())
        )
    ).all()
    return [
        OfficeHistoryEntry(
            office_title=office.title,
            starts_at=assignment.starts_at,
            ends_at=assignment.ends_at,
            is_active=assignment.is_active,
        )
        for assignment, office in rows
    ]


@dataclass(frozen=True, slots=True)
class CadreReserveEntry:
    user_id: int
    first_name: str
    last_name: str | None
    summary: CandidateSummary
    suggested_roles: list[str]


async def list_cadre_reserve(session: AsyncSession, *, limit: int = 100) -> list[CadreReserveEntry]:
    """Admin-facing reserve list (ToR section 76): every user who isn't
    already holding an active leadership office, ranked by suggested-role
    count. Kept simple on purpose -- not a scored ranking."""
    already_leading = {
        row[0]
        for row in (
            await session.execute(
                select(UserOffice.user_id)
                .join(Office, Office.id == UserOffice.office_id)
                .where(UserOffice.is_active.is_(True))
            )
        ).all()
    }
    candidates = list(
        (
            await session.scalars(
                select(User).where(User.is_archived.is_(False), User.is_blocked.is_(False))
            )
        ).all()
    )
    entries: list[CadreReserveEntry] = []
    for user in candidates:
        if user.id in already_leading:
            continue
        summary = await candidate_summary(session, user.id)
        roles = suggested_roles(summary)
        if roles:
            entries.append(
                CadreReserveEntry(
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    summary=summary,
                    suggested_roles=roles,
                )
            )
    entries.sort(key=lambda e: len(e.suggested_roles), reverse=True)
    return entries[:limit]
