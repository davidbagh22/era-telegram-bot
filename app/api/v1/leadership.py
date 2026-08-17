from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_session, get_settings
from app.api.v1.leader import require_leader
from app.config import Settings
from app.database.models import LeadershipAttentionItem, LeadershipGoal, Task, User
from app.services import leader_service, leadership_goal_service, leadership_report_service
from app.services.leadership_permission_service import active_office_assignments
from app.utils.constants import TaskStatus

# Leadership OS ToR sections 30-31 (workspace), 32-35 (goals), 40-42
# (quick reports + blockers). Reuses the existing role-based require_leader
# gate from app/api/v1/leader.py rather than introducing a second one.

router = APIRouter(prefix="/leadership", tags=["leadership"])


# --- "Сегодня" workspace summary (ToR section 31) ---------------------------


class OfficeAssignmentSummaryOut(BaseModel):
    id: int
    office_id: int
    office_title: str
    scope_type: str
    scope_id: int | None
    ends_at: str | None


class GoalSummaryOut(BaseModel):
    id: int
    title: str
    metric: str | None
    target: float | None
    progress: float
    progress_ratio: float | None
    status: str
    period_end: str


class LeadershipMeOut(BaseModel):
    assignments: list[OfficeAssignmentSummaryOut]
    tasks_due_today: int
    tasks_overdue: int
    active_goals: list[GoalSummaryOut]
    current_week_report_submitted: bool
    open_attention_items: int
    team_size: int


@router.get("/me", response_model=LeadershipMeOut)
async def read_leadership_me(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> LeadershipMeOut:
    assignments = await active_office_assignments(session, leader.id)
    now = datetime.now(timezone.utc)
    today_end = datetime.combine(date.today(), datetime.max.time(), tzinfo=timezone.utc)

    tasks_due_today = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assignee_id == leader.id,
                Task.status != TaskStatus.COMPLETED,
                Task.deadline <= today_end,
                Task.deadline >= now.replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )
        or 0
    )
    tasks_overdue = int(
        await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.assignee_id == leader.id,
                Task.status != TaskStatus.COMPLETED,
                Task.deadline < now,
            )
        )
        or 0
    )
    goals = await leadership_goal_service.list_goals(session, owner_id=leader.id, active_only=True)

    week_start = date.today() - timedelta(days=date.today().weekday())
    current_report = await leadership_report_service.current_report(
        session, owner_id=leader.id, period_start=week_start
    )
    open_items = await leadership_report_service.list_attention_items(
        session, status="open", responsible_id=leader.id
    )
    team = await leader_service.list_scope_participants(session, leader)

    return LeadershipMeOut(
        assignments=[
            OfficeAssignmentSummaryOut(
                id=a.id,
                office_id=o.id,
                office_title=o.title,
                scope_type=a.scope_type or o.scope_type,
                scope_id=a.scope_id if a.scope_id is not None else o.scope_id,
                ends_at=a.ends_at.isoformat() if a.ends_at else None,
            )
            for a, o in assignments
        ],
        tasks_due_today=tasks_due_today,
        tasks_overdue=tasks_overdue,
        active_goals=[
            GoalSummaryOut(
                id=g.id,
                title=g.title,
                metric=g.metric,
                target=g.target,
                progress=g.progress,
                progress_ratio=leadership_goal_service.progress_ratio(g),
                status=g.status,
                period_end=g.period_end.isoformat(),
            )
            for g in goals
        ],
        current_week_report_submitted=current_report is not None,
        open_attention_items=len(open_items),
        team_size=len(team),
    )


# --- Goals (ToR sections 32-35) ---------------------------------------------


class GoalOut(BaseModel):
    id: int
    owner_id: int
    scope_type: str
    scope_id: int | None
    period_type: str
    period_start: str
    period_end: str
    title: str
    metric: str | None
    target: float | None
    progress: float
    progress_ratio: float | None
    status: str


def _to_goal_out(goal: LeadershipGoal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        owner_id=goal.owner_id,
        scope_type=goal.scope_type,
        scope_id=goal.scope_id,
        period_type=goal.period_type,
        period_start=goal.period_start.isoformat(),
        period_end=goal.period_end.isoformat(),
        title=goal.title,
        metric=goal.metric,
        target=goal.target,
        progress=goal.progress,
        progress_ratio=leadership_goal_service.progress_ratio(goal),
        status=goal.status,
    )


@router.get("/goals", response_model=list[GoalOut])
async def read_goals(
    scope_type: str | None = None,
    scope_id: int | None = None,
    mine_only: bool = True,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    goals = await leadership_goal_service.list_goals(
        session,
        owner_id=leader.id if mine_only else None,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return [_to_goal_out(g) for g in goals]


class GoalCreateIn(BaseModel):
    title: str
    period_start: str
    period_end: str
    scope_type: str = "global"
    scope_id: int | None = None
    period_type: str = "month"
    metric: str = ""
    target: float | None = None
    office_assignment_id: int | None = None


@router.post("/goals", response_model=GoalOut)
async def create_goal(
    payload: GoalCreateIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="title_required")
    try:
        period_start = date.fromisoformat(payload.period_start)
        period_end = date.fromisoformat(payload.period_end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_date") from exc
    goal = await leadership_goal_service.create_goal(
        session,
        owner_id=leader.id,
        created_by=leader.id,
        title=payload.title,
        period_start=period_start,
        period_end=period_end,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        period_type=payload.period_type,
        metric=payload.metric,
        target=payload.target,
        office_assignment_id=payload.office_assignment_id,
    )
    return _to_goal_out(goal)


class GoalProgressIn(BaseModel):
    progress: float


@router.patch("/goals/{goal_id}", response_model=GoalOut)
async def update_goal_progress(
    goal_id: int,
    payload: GoalProgressIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    goal = await session.get(LeadershipGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal_not_found")
    if goal.owner_id != leader.id:
        raise HTTPException(status_code=403, detail="not_owner")
    await leadership_goal_service.update_progress(session, goal, progress=payload.progress)
    return _to_goal_out(goal)


# --- Quick weekly report (ToR sections 40-42) --------------------------------


class ReportOut(BaseModel):
    id: int
    period_start: str
    period_end: str
    status: str
    main_result: str | None
    blocker_type: str | None
    blocker_note: str | None
    next_priorities: list[str]
    needs_help: bool
    submitted_at: str | None


def _to_report_out(report) -> ReportOut:
    return ReportOut(
        id=report.id,
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        status=report.status,
        main_result=report.main_result,
        blocker_type=report.blocker_type,
        blocker_note=report.blocker_note,
        next_priorities=list(report.next_priorities or []),
        needs_help=report.needs_help,
        submitted_at=report.submitted_at.isoformat() if report.submitted_at else None,
    )


@router.get("/reports/current", response_model=ReportOut | None)
async def read_current_report(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> ReportOut | None:
    week_start = date.today() - timedelta(days=date.today().weekday())
    report = await leadership_report_service.current_report(
        session, owner_id=leader.id, period_start=week_start
    )
    return _to_report_out(report) if report else None


class ReportSubmitIn(BaseModel):
    status: Literal["green", "yellow", "red"]
    main_result: str = ""
    blocker_type: str | None = None
    blocker_note: str = ""
    next_priorities: list[str] = []
    needs_help: bool = False
    scope_type: str = "global"
    scope_id: int | None = None
    office_assignment_id: int | None = None


@router.post("/reports", response_model=ReportOut)
async def submit_report(
    payload: ReportSubmitIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> ReportOut:
    week_start = date.today() - timedelta(days=date.today().weekday())
    result = await leadership_report_service.submit_quick_report(
        session,
        owner_id=leader.id,
        period_start=week_start,
        period_end=week_start + timedelta(days=6),
        status=payload.status,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        office_assignment_id=payload.office_assignment_id,
        main_result=payload.main_result,
        blocker_type=payload.blocker_type,
        blocker_note=payload.blocker_note,
        next_priorities=payload.next_priorities,
        needs_help=payload.needs_help,
        bot=bot,
        settings=settings,
    )
    return _to_report_out(result.report)


# --- Attention items (ToR section 41) ---------------------------------------


class AttentionItemOut(BaseModel):
    id: int
    type: str
    severity: str
    scope_type: str
    scope_id: int | None
    owner_id: int | None
    responsible_id: int | None
    status: str
    resolution: str | None


def _to_attention_item_out(item: LeadershipAttentionItem) -> AttentionItemOut:
    return AttentionItemOut(
        id=item.id,
        type=item.type,
        severity=item.severity,
        scope_type=item.scope_type,
        scope_id=item.scope_id,
        owner_id=item.owner_id,
        responsible_id=item.responsible_id,
        status=item.status,
        resolution=item.resolution,
    )


@router.get("/attention", response_model=list[AttentionItemOut])
async def read_my_attention_items(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[AttentionItemOut]:
    items = await leadership_report_service.list_attention_items(
        session, status="open", responsible_id=leader.id
    )
    return [_to_attention_item_out(i) for i in items]


class AttentionResolveIn(BaseModel):
    resolution: str = ""


@router.post("/attention/{item_id}/resolve", response_model=AttentionItemOut)
async def resolve_attention_item(
    item_id: int,
    payload: AttentionResolveIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> AttentionItemOut:
    item = await session.get(LeadershipAttentionItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="attention_item_not_found")
    await leadership_report_service.resolve_attention_item(
        session, item, resolver_id=leader.id, resolution=payload.resolution
    )
    return _to_attention_item_out(item)
