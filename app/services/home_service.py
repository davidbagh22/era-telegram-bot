from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, Project, Task, User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.repositories.users import user_stats
from app.services.growth_service import GrowthProgress, growth_progress_for
from app.services.opportunity_service import (
    ACTIVE_APPLICATION_STATUSES,
    RECOGNITION_TYPES,
    evaluate_eligibility,
)
from app.services.progression_service import RANK_ORDER
from app.utils.constants import (
    STATUS_LABELS,
    ParticipationStatus,
    ProjectStatus,
    RegistrationStatus,
    TaskStatus,
)

# Home only covers what can be computed from data that actually exists
# today. "Attention items" for participants would just restate next_step,
# and "recent activity" needs the UserActivityEvent model planned for the
# Analytics PR — both are deliberately left out rather than faked.
ACTIVE_TASK_STATUSES = (TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE)
ACTIVE_REGISTRATION_STATUSES = (RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME)
ACTION_NEEDED_PROJECT_STATUSES = (ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION)


@dataclass(frozen=True)
class NextStep:
    kind: str
    title: str
    description: str


@dataclass(frozen=True)
class EventSummary:
    id: int
    title: str
    event_date: str
    event_time: str
    location: str


@dataclass(frozen=True)
class TaskSummary:
    id: int
    title: str
    deadline: str
    points: int
    status: str


@dataclass(frozen=True)
class ProjectSummary:
    id: int
    title: str
    status: str


@dataclass(frozen=True)
class OpportunitySummary:
    id: int
    title: str
    point_cost: int
    expires_at: str | None


@dataclass(frozen=True)
class ActivityStats:
    """Powers Home's "Моя активность" section (PR 38) — the exact same
    numbers profile_service/portfolio_service already compute for the
    Profile screen's stat grid (app/repositories/users.py::user_stats()),
    reused rather than duplicated so the two screens can never disagree.

    `portfolio_items` is a total count of everything recorded to the
    portfolio (projects/events/tasks/badges/certificates/etc — see
    ProfileScreen's PortfolioSection groupings), not just badges. There's
    no separate "achievement count" query anywhere in the app; rather
    than invent one just for this stat (and risk it disagreeing with what
    Profile itself shows), this reuses the same "В портфолио" number
    Profile already displays."""

    points: int
    projects: int
    completed_tasks: int
    portfolio_items: int


@dataclass(frozen=True)
class RankProgress:
    """Points/Ranks ToR section 39/49's Home card: current rank + the name
    of the next one. Deliberately no "N points until next rank" number --
    rank is metrics-based, not points-linear (ToR section 24), so a points
    countdown here would be fabricated. The honestly computable countdown
    is to the nearest Opportunity, in `nearest_opportunity` below."""

    rank: str
    rank_label: str
    next_rank_label: str | None


@dataclass(frozen=True)
class OpportunityProgress:
    id: int
    title: str
    issuer: str
    points_needed: int


@dataclass(frozen=True)
class HomeSnapshot:
    growth: GrowthProgress
    rank: RankProgress
    points_balance: int
    activity: ActivityStats
    next_step: NextStep | None
    nearest_event: EventSummary | None
    active_task: TaskSummary | None
    active_project: ProjectSummary | None
    opportunities: list[OpportunitySummary]
    new_opportunity: OpportunityProgress | None
    nearest_locked_opportunity: OpportunityProgress | None


async def _active_task(session: AsyncSession, user_id: int) -> Task | None:
    return await session.scalar(
        select(Task)
        .where(Task.assignee_id == user_id, Task.status.in_(ACTIVE_TASK_STATUSES))
        .order_by(Task.deadline.asc())
        .limit(1)
    )


async def _nearest_event(
    session: AsyncSession, user_id: int
) -> tuple[Event, EventRegistration] | None:
    today = date.today()
    row = (
        await session.execute(
            select(Event, EventRegistration)
            .join(EventRegistration, EventRegistration.event_id == Event.id)
            .where(
                EventRegistration.user_id == user_id,
                EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                Event.event_date >= today,
            )
            .order_by(Event.event_date.asc(), Event.event_time.asc())
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def _active_project(session: AsyncSession, user_id: int) -> Project | None:
    return await session.scalar(
        select(Project)
        .where(
            Project.author_id == user_id,
            Project.status.in_(ACTION_NEEDED_PROJECT_STATUSES),
        )
        .order_by(Project.updated_at.desc())
        .limit(1)
    )


async def _top_opportunities(
    session: AsyncSession, user_id: int, limit: int = 3
) -> list[PartnerInitiative]:
    now = datetime.now(timezone.utc)
    applied_subquery = select(PartnerOfferApplication.initiative_id).where(
        PartnerOfferApplication.user_id == user_id
    )
    result = await session.scalars(
        select(PartnerInitiative)
        .where(
            PartnerInitiative.is_active.is_(True),
            PartnerInitiative.is_archived.is_(False),
            PartnerInitiative.id.not_in(applied_subquery),
            (PartnerInitiative.expires_at.is_(None)) | (PartnerInitiative.expires_at >= now),
        )
        .order_by(PartnerInitiative.expires_at.asc().nullslast())
        .limit(limit)
    )
    return list(result.all())


def _rank_progress(user: User) -> RankProgress:
    rank = user.participation_status or ParticipationStatus.NEW_MEMBER
    try:
        index = RANK_ORDER.index(rank)
    except ValueError:
        index = 0
    next_rank_label = (
        STATUS_LABELS[RANK_ORDER[index + 1]] if index + 1 < len(RANK_ORDER) else None
    )
    return RankProgress(
        rank=rank,
        rank_label=STATUS_LABELS.get(rank, str(rank)),
        next_rank_label=next_rank_label,
    )


async def _recognition_progress(
    session: AsyncSession, user: User, points: int
) -> tuple[OpportunityProgress | None, OpportunityProgress | None]:
    """The Home card's "Новая возможность" (already eligible, not yet
    applied) and "До следующей возможности X: N баллов" (closest by points
    gap among the ones still locked). Only recognition-type opportunities
    (certificates/letters) count here -- the old spend-based partner offers
    aren't "возможности" in the ToR's sense."""
    applied_subquery = select(PartnerOfferApplication.initiative_id).where(
        PartnerOfferApplication.user_id == user.id,
        PartnerOfferApplication.status.in_(ACTIVE_APPLICATION_STATUSES),
    )
    rows = (
        await session.execute(
            select(PartnerInitiative, Partner)
            .join(Partner, Partner.id == PartnerInitiative.partner_id)
            .where(
                PartnerInitiative.opportunity_type.in_(RECOGNITION_TYPES),
                PartnerInitiative.is_active.is_(True),
                PartnerInitiative.is_archived.is_(False),
                PartnerInitiative.id.not_in(applied_subquery),
            )
            .order_by(PartnerInitiative.point_cost.asc())
        )
    ).all()

    new_opportunity: OpportunityProgress | None = None
    nearest_locked: OpportunityProgress | None = None
    nearest_gap: int | None = None
    for offer, partner in rows:
        eligibility = await evaluate_eligibility(session, offer, user)
        if eligibility.eligible:
            if new_opportunity is None:
                new_opportunity = OpportunityProgress(
                    id=offer.id, title=offer.title, issuer=partner.name, points_needed=0
                )
            continue
        gap = max(0, int(offer.point_cost or 0) - points)
        if nearest_gap is None or gap < nearest_gap:
            nearest_gap = gap
            nearest_locked = OpportunityProgress(
                id=offer.id, title=offer.title, issuer=partner.name, points_needed=gap
            )
    return new_opportunity, nearest_locked


def _build_next_step(
    *,
    active_task: Task | None,
    nearest_event_row: tuple[Event, EventRegistration] | None,
    active_project: Project | None,
    growth: GrowthProgress,
    opportunities: list[PartnerInitiative],
) -> NextStep | None:
    # Priority order per the Home spec: active/overdue task, then nearest
    # registered event, then a project needing action, then a generic
    # growth nudge, then a matching opportunity.
    if active_task is not None:
        return NextStep(
            kind="task",
            title=f"Задача: {active_task.title}",
            description="Проверьте требования и отправьте результат до дедлайна.",
        )
    if nearest_event_row is not None:
        event, _ = nearest_event_row
        return NextStep(
            kind="event",
            title=f"Мероприятие: {event.title}",
            description=f"{event.event_date.isoformat()} · {event.location}",
        )
    if active_project is not None:
        description = (
            "Заполните оставшиеся блоки и отправьте на рассмотрение."
            if active_project.status == ProjectStatus.DRAFT
            else "Учтите замечания администратора и отправьте доработку."
        )
        return NextStep(
            kind="project",
            title=f"Проект: {active_project.title}",
            description=description,
        )
    if growth.level != "leader":
        return NextStep(
            kind="growth",
            title="Продолжайте расти в ЭРА",
            description="Участвуйте в мероприятиях и задачах, чтобы перейти на следующий уровень.",
        )
    if opportunities:
        return NextStep(
            kind="opportunity",
            title=f"Возможность: {opportunities[0].title}",
            description="Подходит вам — откройте «Возможности», чтобы подать заявку.",
        )
    return None


async def build_home_snapshot(session: AsyncSession, user: User) -> HomeSnapshot:
    active_task = await _active_task(session, user.id)
    nearest_event_row = await _nearest_event(session, user.id)
    active_project = await _active_project(session, user.id)
    growth = growth_progress_for(user)
    opportunities = await _top_opportunities(session, user.id)
    stats = await user_stats(session, user.id)
    activity = ActivityStats(
        points=stats["points"],
        projects=stats["projects"],
        completed_tasks=stats["tasks"],
        portfolio_items=stats["portfolio"],
    )
    rank = _rank_progress(user)
    new_opportunity, nearest_locked_opportunity = await _recognition_progress(
        session, user, activity.points
    )

    next_step = _build_next_step(
        active_task=active_task,
        nearest_event_row=nearest_event_row,
        active_project=active_project,
        growth=growth,
        opportunities=opportunities,
    )

    nearest_event_summary = None
    if nearest_event_row is not None:
        event = nearest_event_row[0]
        nearest_event_summary = EventSummary(
            id=event.id,
            title=event.title,
            event_date=event.event_date.isoformat(),
            event_time=event.event_time.isoformat(timespec="minutes"),
            location=event.location,
        )

    active_task_summary = None
    if active_task is not None:
        active_task_summary = TaskSummary(
            id=active_task.id,
            title=active_task.title,
            deadline=active_task.deadline.isoformat(),
            points=active_task.points,
            status=active_task.status,
        )

    active_project_summary = None
    if active_project is not None:
        active_project_summary = ProjectSummary(
            id=active_project.id,
            title=active_project.title,
            status=active_project.status,
        )

    return HomeSnapshot(
        growth=growth,
        rank=rank,
        points_balance=activity.points,
        activity=activity,
        next_step=next_step,
        nearest_event=nearest_event_summary,
        active_task=active_task_summary,
        active_project=active_project_summary,
        new_opportunity=new_opportunity,
        nearest_locked_opportunity=nearest_locked_opportunity,
        opportunities=[
            OpportunitySummary(
                id=o.id,
                title=o.title,
                point_cost=o.point_cost,
                expires_at=o.expires_at.isoformat() if o.expires_at else None,
            )
            for o in opportunities
        ],
    )
