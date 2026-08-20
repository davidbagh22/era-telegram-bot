from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_session, get_settings
from app.api.v1.leader import require_leader
from app.config import Settings
from app.database.leadership_models import LeadershipFeedback
from app.database.models import LeadershipAttentionItem, LeadershipGoal, LeadershipReport, Task, User
from app.services import (
    leader_service,
    leadership_goal_service,
    leadership_report_service,
    leadership_weekly_service,
)
from app.services.leadership_permission_service import active_office_assignments
from app.utils.constants import TaskStatus

router = APIRouter(prefix="/leadership", tags=["leadership"])


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

    week_start, _ = leadership_weekly_service.week_bounds()
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
        current_week_report_submitted=bool(current_report and current_report.submitted_at),
        open_attention_items=len(open_items),
        team_size=len(team),
    )


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


class ReportOut(BaseModel):
    id: int
    period_start: str
    period_end: str
    scope_type: str
    scope_id: int | None
    office_assignment_id: int | None
    status: str
    main_result: str | None
    blocker_type: str | None
    blocker_note: str | None
    next_priorities: list[str]
    needs_help: bool
    submitted_at: str | None
    system_snapshot: dict
    pace_score: int | None
    clarity_score: int | None
    load_score: int | None
    attention_text: str | None


def _to_report_out(view: leadership_weekly_service.WeeklyReportView) -> ReportOut:
    report, pulse = view.report, view.pulse
    return ReportOut(
        id=report.id,
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        scope_type=report.scope_type,
        scope_id=report.scope_id,
        office_assignment_id=report.office_assignment_id,
        status=report.status,
        main_result=report.main_result,
        blocker_type=report.blocker_type,
        blocker_note=report.blocker_note,
        next_priorities=list(report.next_priorities or []),
        needs_help=report.needs_help,
        submitted_at=report.submitted_at.isoformat() if report.submitted_at else None,
        system_snapshot=dict(pulse.system_snapshot or {}),
        pace_score=pulse.pace_score,
        clarity_score=pulse.clarity_score,
        load_score=pulse.load_score,
        attention_text=pulse.attention_text,
    )


@router.get("/reports/current", response_model=ReportOut)
async def read_current_report(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> ReportOut:
    week_start, _ = leadership_weekly_service.week_bounds()
    try:
        view = await leadership_weekly_service.ensure_weekly_report(
            session, owner_id=leader.id, period_start=week_start
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await session.commit()
    return _to_report_out(view)


@router.get("/reports/history", response_model=list[ReportOut])
async def read_report_history(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[ReportOut]:
    reports = await leadership_report_service.list_reports(session, owner_id=leader.id)
    output: list[ReportOut] = []
    for report in reports:
        view = await leadership_weekly_service.ensure_weekly_report(
            session,
            owner_id=leader.id,
            period_start=report.period_start,
            office_assignment_id=report.office_assignment_id,
        )
        output.append(_to_report_out(view))
    return output


class ReportSubmitIn(BaseModel):
    status: Literal["green", "yellow", "red"]
    main_result: str = ""
    blocker_type: str | None = None
    blocker_note: str = ""
    next_priorities: list[str] = Field(default_factory=list, max_length=3)
    needs_help: bool = False
    office_assignment_id: int | None = None
    pace_score: int | None = Field(default=None, ge=1, le=5)
    clarity_score: int | None = Field(default=None, ge=1, le=5)
    load_score: int | None = Field(default=None, ge=1, le=5)
    attention_text: str = ""
    scope_type: str | None = None
    scope_id: int | None = None


@router.post("/reports", response_model=ReportOut)
async def submit_report(
    payload: ReportSubmitIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> ReportOut:
    week_start, _ = leadership_weekly_service.week_bounds()
    try:
        view = await leadership_weekly_service.submit_weekly_pulse(
            session,
            owner_id=leader.id,
            period_start=week_start,
            status=payload.status,
            office_assignment_id=payload.office_assignment_id,
            main_result=payload.main_result,
            blocker_type=payload.blocker_type,
            blocker_note=payload.blocker_note,
            next_priorities=payload.next_priorities,
            needs_help=payload.needs_help,
            pace_score=payload.pace_score,
            clarity_score=payload.clarity_score,
            load_score=payload.load_score,
            attention_text=payload.attention_text,
            bot=bot,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return _to_report_out(view)


class FeedbackOut(BaseModel):
    id: int
    report_id: int
    reviewer_id: int
    status: str
    comment: str | None
    created_at: str


def _to_feedback_out(item: LeadershipFeedback) -> FeedbackOut:
    return FeedbackOut(
        id=item.id,
        report_id=item.report_id,
        reviewer_id=item.reviewer_id,
        status=item.status,
        comment=item.comment,
        created_at=item.created_at.isoformat(),
    )


class FeedbackCreateIn(BaseModel):
    status: Literal["acknowledged", "follow_up", "resolved"] = "acknowledged"
    comment: str = Field(default="", max_length=2000)


@router.get("/reports/{report_id}/feedback", response_model=list[FeedbackOut])
async def read_report_feedback(
    report_id: int,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[FeedbackOut]:
    report = await session.get(LeadershipReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report_not_found")
    if report.owner_id != leader.id and not await leadership_weekly_service.can_review_report(
        session, reviewer=leader, report=report
    ):
        raise HTTPException(status_code=403, detail="feedback_scope_forbidden")
    return [
        _to_feedback_out(item)
        for item in await leadership_weekly_service.list_feedback(session, report_id=report.id)
    ]


@router.post("/reports/{report_id}/feedback", response_model=FeedbackOut)
async def create_report_feedback(
    report_id: int,
    payload: FeedbackCreateIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> FeedbackOut:
    report = await session.get(LeadershipReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report_not_found")
    try:
        item = await leadership_weekly_service.add_feedback(
            session,
            report=report,
            reviewer=leader,
            status=payload.status,
            comment=payload.comment,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await session.commit()
    return _to_feedback_out(item)


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
    if item.responsible_id is not None and item.responsible_id != leader.id and leader.role != "admin":
        raise HTTPException(status_code=403, detail="attention_scope_forbidden")
    await leadership_report_service.resolve_attention_item(
        session, item, resolver_id=leader.id, resolution=payload.resolution
    )
    await session.commit()
    return _to_attention_item_out(item)
