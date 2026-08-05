from __future__ import annotations

from datetime import datetime
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session
from app.api.rate_limit import enforce_rate_limit
from app.database.models import Task, User
from app.services import leader_service
from app.utils.constants import PRIVILEGED_ROLES

router = APIRouter(prefix="/leader", tags=["leader"])

# Same rationale as app/api/v1/admin.py's ADMIN_ACTION_RATE_LIMIT — a
# stolen leader token shouldn't be able to spam task creation/decisions
# unbounded. See docs/PRODUCTION_READINESS_AUDIT.md finding #11.
LEADER_ACTION_RATE_LIMIT = 30
LEADER_ACTION_RATE_LIMIT_WINDOW_SECONDS = 60


async def enforce_leader_action_rate_limit(request: Request) -> None:
    await enforce_rate_limit(
        request,
        key_prefix="leader_action",
        limit=LEADER_ACTION_RATE_LIMIT,
        window_seconds=LEADER_ACTION_RATE_LIMIT_WINDOW_SECONDS,
    )


async def require_leader(user: User = Depends(get_current_user)) -> User:
    if user.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="leader_access_required")
    return user


class ParticipantOut(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    participation_status: str


class EventOut(BaseModel):
    id: int
    title: str
    status: str
    event_date: str
    event_time: str


class ProjectOut(BaseModel):
    id: int
    title: str
    status: str


class TaskOut(BaseModel):
    id: int
    title: str
    status: str
    deadline: str
    points: int
    assignee_id: int | None


class OverviewOut(BaseModel):
    departments: list[str]
    directions: list[str]
    participants: list[ParticipantOut]
    events: list[EventOut]
    projects: list[ProjectOut]
    tasks: list[TaskOut]


@router.get("/overview", response_model=OverviewOut)
async def read_overview(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> OverviewOut:
    participants = await leader_service.list_scope_participants(session, leader)
    events = await leader_service.list_scope_events(session, leader)
    projects = await leader_service.list_scope_projects(session, leader)
    tasks = await leader_service.list_created_tasks(session, leader)
    return OverviewOut(
        departments=[item.department.name for item in leader.departments],
        directions=[item.direction.name for item in leader.directions],
        participants=[
            ParticipantOut(
                id=p.id,
                first_name=p.first_name,
                last_name=p.last_name,
                participation_status=p.participation_status,
            )
            for p in participants
        ],
        events=[
            EventOut(
                id=e.id,
                title=e.title,
                status=e.status,
                event_date=e.event_date.isoformat(),
                event_time=e.event_time.isoformat(),
            )
            for e in events
        ],
        projects=[ProjectOut(id=p.id, title=p.title, status=p.status) for p in projects],
        tasks=[
            TaskOut(
                id=t.id,
                title=t.title,
                status=t.status,
                deadline=t.deadline.isoformat(),
                points=t.points,
                assignee_id=t.assignee_id,
            )
            for t in tasks
        ],
    )


class AssignedTaskCreateIn(BaseModel):
    assignee_id: int
    title: str
    description: str
    deadline: datetime
    points: int = 10


@router.post("/tasks", response_model=TaskOut)
async def create_assigned_task(
    payload: AssignedTaskCreateIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_leader_action_rate_limit),
) -> TaskOut:
    assignee = await session.get(User, payload.assignee_id)
    if assignee is None:
        raise HTTPException(status_code=404, detail="assignee_not_found")
    try:
        task = await leader_service.create_assigned_task(
            session,
            creator=leader,
            assignee=assignee,
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            points=payload.points,
            bot=bot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TaskOut(
        id=task.id,
        title=task.title,
        status=task.status,
        deadline=task.deadline.isoformat(),
        points=task.points,
        assignee_id=task.assignee_id,
    )


class ApplicationOut(BaseModel):
    user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    status: str


class OpenTaskOut(BaseModel):
    id: int
    title: str
    description: str
    deadline: str
    points: int
    max_participants: int | None
    applications: list[ApplicationOut]


def _to_open_task_out(result: leader_service.OpenTaskWithApplications) -> OpenTaskOut:
    task = result.task
    return OpenTaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        deadline=task.deadline.isoformat(),
        points=task.points,
        max_participants=task.max_participants,
        applications=[
            ApplicationOut(
                user_id=application.applicant.id,
                first_name=application.applicant.first_name,
                last_name=application.applicant.last_name,
                username=application.applicant.username,
                status=application.participant.status,
            )
            for application in result.applications
        ],
    )


@router.get("/open-tasks", response_model=list[OpenTaskOut])
async def read_open_tasks(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[OpenTaskOut]:
    results = await leader_service.list_open_tasks_with_applications(session, leader)
    return [_to_open_task_out(result) for result in results]


class OpenTaskCreateIn(BaseModel):
    title: str
    description: str
    deadline: datetime
    points: int = 10
    max_participants: int = 1


@router.post("/open-tasks", response_model=OpenTaskOut)
async def create_open_task(
    payload: OpenTaskCreateIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    _rate_limit: None = Depends(enforce_leader_action_rate_limit),
) -> OpenTaskOut:
    try:
        task = await leader_service.create_open_task(
            session,
            creator=leader,
            title=payload.title,
            description=payload.description,
            deadline=payload.deadline,
            points=payload.points,
            max_participants=payload.max_participants,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_open_task_out(leader_service.OpenTaskWithApplications(task=task, applications=[]))


class ApplicationDecisionIn(BaseModel):
    action: Literal["accept", "reject"]


@router.post("/open-tasks/{task_id}/applications/{user_id}/decide", response_model=OpenTaskOut)
async def decide_application(
    task_id: int,
    user_id: int,
    payload: ApplicationDecisionIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    _rate_limit: None = Depends(enforce_leader_action_rate_limit),
) -> OpenTaskOut:
    task = await session.get(Task, task_id)
    target = await session.get(User, user_id)
    if task is None or target is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        await leader_service.decide_task_application(
            session, task=task, target=target, action=payload.action, actor=leader, bot=bot
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        code = 409 if str(exc) == "capacity_reached" else 404
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    results = await leader_service.list_open_tasks_with_applications(session, leader)
    for result in results:
        if result.task.id == task.id:
            return _to_open_task_out(result)
    return _to_open_task_out(leader_service.OpenTaskWithApplications(task=task, applications=[]))
