from __future__ import annotations

from datetime import datetime
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import Event, EventActivitySubmission, Task, User
from app.keyboards.participant import open_app_button
from app.services import event_activity_service, leader_service
from app.utils.deep_links import miniapp_task_url
from app.services.notification_service import notify_admins, safe_send
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
    settings: Settings = Depends(get_settings),
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
            miniapp_url=settings.effective_miniapp_url,
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
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_leader_action_rate_limit),
) -> OpenTaskOut:
    task = await session.get(Task, task_id)
    target = await session.get(User, user_id)
    if task is None or target is None:
        raise HTTPException(status_code=404, detail="not_found")
    keyboard = (
        open_app_button(miniapp_task_url(settings.effective_miniapp_url, task.id))
        if payload.action == "accept" and settings.effective_miniapp_url
        else None
    )
    try:
        await leader_service.decide_task_application(
            session, task=task, target=target, action=payload.action, actor=leader, bot=bot, keyboard=keyboard
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


# ---------------------------------------------------------------------------
# Event Activities — the Mini App equivalent of the leader pre-review step
# in app/handlers/leader/event_activities_block7.py. A submission passes
# through here before an admin can do the final points award; a leader
# only ever sees submissions for events they're responsible for.
# ---------------------------------------------------------------------------


class ActivitySubmissionOut(BaseModel):
    id: int
    activity_id: int
    activity_title: str
    points: int
    event_title: str
    user_id: int
    user_name: str
    status: str
    text: str | None
    file_type: str | None


def _to_activity_submission_out(row) -> ActivitySubmissionOut:
    submission, activity, event, respondent = row
    return ActivitySubmissionOut(
        id=submission.id,
        activity_id=activity.id,
        activity_title=activity.title,
        points=activity.points,
        event_title=event.title,
        user_id=respondent.id,
        user_name=f"{respondent.first_name} {respondent.last_name or ''}".strip(),
        status=submission.status,
        text=submission.text,
        file_type=submission.file_type,
    )


@router.get("/activities", response_model=list[ActivitySubmissionOut])
async def read_leader_activities(
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
) -> list[ActivitySubmissionOut]:
    rows = await event_activity_service.list_leader_pending(session, leader.id)
    return [_to_activity_submission_out(row) for row in rows]


class ActivityDecisionIn(BaseModel):
    action: Literal["approve", "reject"]


@router.post("/activities/{submission_id}/decide", response_model=ActivitySubmissionOut)
async def decide_leader_activity(
    submission_id: int,
    payload: ActivityDecisionIn,
    leader: User = Depends(require_leader),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    _rate_limit: None = Depends(enforce_leader_action_rate_limit),
) -> ActivitySubmissionOut:
    submission = await session.get(EventActivitySubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    activity = await event_activity_service.leader_decide(
        session, submission, approve=payload.action == "approve", reviewer_id=leader.id
    )
    if activity is None:
        raise HTTPException(status_code=409, detail="already_reviewed")
    target = await session.get(User, submission.user_id)
    event = await session.get(Event, activity.event_id)
    event_title = event.title if event else ""
    if bot is not None:
        if payload.action == "approve":
            if target:
                await safe_send(
                    bot,
                    target.telegram_id,
                    f"Ваш результат «{activity.title}» принят лидером и передан админу на финальное подтверждение.",
                )
            await notify_admins(
                bot,
                settings,
                f"✨ Активность прошла лидерскую проверку\n\n{activity.title}\nТеперь админ может финально начислить баллы.",
                reply_markup=open_app_button(settings.effective_miniapp_url),
            )
        elif target:
            await safe_send(bot, target.telegram_id, f"Результат «{activity.title}» не прошёл лидерскую проверку.")
    return ActivitySubmissionOut(
        id=submission.id,
        activity_id=activity.id,
        activity_title=activity.title,
        points=activity.points,
        event_title=event_title,
        user_id=submission.user_id,
        user_name=f"{target.first_name} {target.last_name or ''}".strip() if target else "",
        status=submission.status,
        text=submission.text,
        file_type=submission.file_type,
    )
