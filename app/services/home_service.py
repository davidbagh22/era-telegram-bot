from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, PointTransaction, Project, Task, User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.repositories.users import user_stats
from app.services.activity_service import list_tasks
from app.services.development_service import VectorHomeSummary, vector_home_summary
from app.services.growth_service import GrowthProgress, growth_progress_for
from app.services.opportunity_service import (
    ACTIVE_APPLICATION_STATUSES,
    RECOGNITION_TYPES,
    EligibilityCheck,
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

ERA_TIMEZONE = ZoneInfo("Asia/Yerevan")
ACTIVE_TASK_STATUSES = (TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE)
ACTIVE_REGISTRATION_STATUSES = (RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME)
ACTION_NEEDED_PROJECT_STATUSES = (ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION)


@dataclass(frozen=True)
class NextStep:
    kind: str
    title: str
    description: str
    # DELTA ToR §6: a next_step the frontend can't act on is a dead card.
    # entity_id/route are alternate ways to point at the same target --
    # entity_id lets the frontend reuse its existing onOpenTask/onOpenEvent/
    # etc. callbacks (preferred, matches how every other Home card already
    # navigates), route is the literal path per the ToR's API contract for
    # any future generic router. action_label is the CTA text; kinds with
    # no single entity ("growth") leave entity_id/route unset and the
    # frontend falls back to its kind-specific handler (e.g. onOpenDevelopment).
    entity_id: int | None = None
    route: str | None = None
    action_label: str = "Открыть"


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
    """The same activity totals Profile already exposes through user_stats()."""

    points: int
    projects: int
    completed_tasks: int
    portfolio_items: int


@dataclass(frozen=True)
class RankProgress:
    rank: str
    rank_label: str
    next_rank_label: str | None


@dataclass(frozen=True)
class OpportunityProgress:
    id: int
    title: str
    issuer: str
    points_needed: int
    display_state: str
    progress_text: str


@dataclass(frozen=True)
class HomeSnapshot:
    growth: GrowthProgress
    rank: RankProgress
    points_balance: int
    points_today: int
    points_month: int
    activity: ActivityStats
    next_step: NextStep | None
    nearest_event: EventSummary | None
    active_task: TaskSummary | None
    active_project: ProjectSummary | None
    opportunities: list[OpportunitySummary]
    new_opportunity: OpportunityProgress | None
    almost_opportunity: OpportunityProgress | None
    locked_opportunity: OpportunityProgress | None
    nearest_locked_opportunity: OpportunityProgress | None
    # DELTA ToR §15: the compact "Задания" entry card on Home --
    # "N доступны · M в работе" -- counts only, no row payload duplication.
    tasks_available_count: int
    tasks_in_progress_count: int
    # DELTA ToR §2-5: safe "Мой вектор" summary; None means never checked in.
    vector: VectorHomeSummary | None


def _period_starts(now: datetime) -> tuple[datetime, datetime]:
    """Return Yerevan-local day/month starts converted to UTC for DB queries."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(ERA_TIMEZONE)
    day_start_local = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        tzinfo=ERA_TIMEZONE,
    )
    month_start_local = datetime(
        local_now.year,
        local_now.month,
        1,
        tzinfo=ERA_TIMEZONE,
    )
    return (
        day_start_local.astimezone(timezone.utc),
        month_start_local.astimezone(timezone.utc),
    )


async def _earned_points_periods(
    session: AsyncSession,
    user_id: int,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Positive points earned today and this month; spending never reduces earned progress."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    day_start, month_start = _period_starts(current)

    async def earned_since(start: datetime) -> int:
        return int(
            await session.scalar(
                select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                    PointTransaction.user_id == user_id,
                    PointTransaction.points > 0,
                    PointTransaction.created_at >= start,
                    PointTransaction.created_at <= current,
                )
            )
            or 0
        )

    today = await earned_since(day_start)
    month = await earned_since(month_start)
    return today, month


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
    today = datetime.now(ERA_TIMEZONE).date()
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


def _numeric_gap(check: EligibilityCheck) -> int | None:
    try:
        return max(0, int(check.required) - int(check.current))
    except (TypeError, ValueError):
        return None


def _check_progress_text(check: EligibilityCheck) -> str:
    if check.key == "points":
        gap = _numeric_gap(check)
        return f"осталось {gap} баллов" if gap is not None else "нужны дополнительные баллы"
    if check.key.startswith("metric:") and check.key != "metric:any":
        gap = _numeric_gap(check)
        return f"ещё {gap} {check.label}" if gap is not None else f"нужно: {check.label}"
    if check.key == "rank":
        return f"нужен ранг: {check.required}"
    if check.key == "prerequisite_document":
        return "нужен предыдущий документ"
    if check.key == "metric:any":
        return "нужен подтверждённый профиль деятельности"
    return f"нужно выполнить: {check.label}"


def _progress_text(failed: list[EligibilityCheck]) -> str:
    if not failed:
        return "все условия выполнены"
    parts = [_check_progress_text(check) for check in failed[:2]]
    if len(failed) == 1:
        return parts[0]
    suffix = "" if len(failed) <= 2 else f" · ещё условий: {len(failed) - 2}"
    return "ещё нужно: " + " · ".join(parts) + suffix


def _opportunity_progress(
    offer: PartnerInitiative,
    partner: Partner,
    *,
    failed: list[EligibilityCheck],
) -> OpportunityProgress:
    points_check = next((check for check in failed if check.key == "points"), None)
    points_needed = _numeric_gap(points_check) if points_check is not None else 0
    state = "available" if not failed else ("almost" if len(failed) == 1 else "locked")
    return OpportunityProgress(
        id=offer.id,
        title=offer.title,
        issuer=partner.name,
        points_needed=points_needed or 0,
        display_state=state,
        progress_text=_progress_text(failed),
    )


async def _recognition_progress(
    session: AsyncSession, user: User
) -> tuple[
    OpportunityProgress | None,
    OpportunityProgress | None,
    OpportunityProgress | None,
]:
    """Return one truthful available/almost/locked recognition opportunity.

    Eligibility itself remains owned by opportunity_service. Home only projects
    its existing checks into concise progress text, so rank/metrics/prerequisites
    can never be replaced by a misleading points-only countdown.
    """

    now = datetime.now(timezone.utc)
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
                Partner.is_active.is_(True),
                Partner.is_archived.is_(False),
                PartnerInitiative.id.not_in(applied_subquery),
                (PartnerInitiative.expires_at.is_(None)) | (PartnerInitiative.expires_at >= now),
            )
            .order_by(PartnerInitiative.point_cost.asc(), PartnerInitiative.id.asc())
        )
    ).all()

    available: OpportunityProgress | None = None
    almost: OpportunityProgress | None = None
    locked: OpportunityProgress | None = None
    locked_missing_count: int | None = None

    for offer, partner in rows:
        eligibility = await evaluate_eligibility(session, offer, user)
        failed = [check for check in eligibility.checks if not check.ok]
        progress = _opportunity_progress(offer, partner, failed=failed)
        if not failed:
            if available is None:
                available = progress
            continue
        if len(failed) == 1:
            if almost is None:
                almost = progress
            continue
        if locked is None or locked_missing_count is None or len(failed) < locked_missing_count:
            locked = progress
            locked_missing_count = len(failed)

    return available, almost, locked


def _build_next_step(
    *,
    active_task: Task | None,
    nearest_event_row: tuple[Event, EventRegistration] | None,
    active_project: Project | None,
    growth: GrowthProgress,
    opportunities: list[PartnerInitiative],
) -> NextStep | None:
    if active_task is not None:
        return NextStep(
            kind="task",
            title=f"Задача: {active_task.title}",
            description="Проверьте требования и отправьте результат до дедлайна.",
            entity_id=active_task.id,
            route=f"/tasks/{active_task.id}",
        )
    if nearest_event_row is not None:
        event, _ = nearest_event_row
        return NextStep(
            kind="event",
            title=f"Мероприятие: {event.title}",
            description=f"{event.event_date.isoformat()} · {event.location}",
            entity_id=event.id,
            route=f"/events/{event.id}",
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
            entity_id=active_project.id,
            route=f"/projects/{active_project.id}",
        )
    if growth.level != "leader":
        return NextStep(
            kind="growth",
            title="Продолжайте расти в ЭРА",
            description="Участвуйте в мероприятиях и задачах, чтобы перейти на следующий уровень.",
            route="/development",
            action_label="Пройти",
        )
    if opportunities:
        return NextStep(
            kind="opportunity",
            title=f"Возможность: {opportunities[0].title}",
            description="Подходит вам — откройте «Возможности», чтобы подать заявку.",
            entity_id=opportunities[0].id,
            route=f"/opportunities/{opportunities[0].id}",
        )
    return None


async def build_home_snapshot(session: AsyncSession, user: User) -> HomeSnapshot:
    active_task = await _active_task(session, user.id)
    nearest_event_row = await _nearest_event(session, user.id)
    active_project = await _active_project(session, user.id)
    growth = growth_progress_for(user)
    opportunities = await _top_opportunities(session, user.id)
    stats = await user_stats(session, user.id)
    points_today, points_month = await _earned_points_periods(session, user.id)
    activity = ActivityStats(
        points=stats["points"],
        projects=stats["projects"],
        completed_tasks=stats["tasks"],
        portfolio_items=stats["portfolio"],
    )
    rank = _rank_progress(user)
    available_opportunity, almost_opportunity, locked_opportunity = await _recognition_progress(
        session, user
    )
    tasks_available_count = len(await list_tasks(session, user, "available"))
    tasks_in_progress_count = len(await list_tasks(session, user, "mine"))
    vector = await vector_home_summary(session, user.id)

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
        points_today=points_today,
        points_month=points_month,
        activity=activity,
        next_step=next_step,
        nearest_event=nearest_event_summary,
        active_task=active_task_summary,
        active_project=active_project_summary,
        new_opportunity=available_opportunity,
        almost_opportunity=almost_opportunity,
        locked_opportunity=locked_opportunity,
        nearest_locked_opportunity=almost_opportunity or locked_opportunity,
        opportunities=[
            OpportunitySummary(
                id=o.id,
                title=o.title,
                point_cost=o.point_cost,
                expires_at=o.expires_at.isoformat() if o.expires_at else None,
            )
            for o in opportunities
        ],
        tasks_available_count=tasks_available_count,
        tasks_in_progress_count=tasks_in_progress_count,
        vector=vector,
    )
