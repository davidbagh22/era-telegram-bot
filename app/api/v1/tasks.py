from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.community_models import CommunityMissionTemplate, TaskSquad, TaskSubtask
from app.database.models import Task, TaskParticipant, User
from app.services import task_service
from app.services.activity_service import TaskScope, list_tasks
from app.services.community_mission_service import (
    assign_subtask,
    confirm_squad_plan,
    launch_all_pending_missions,
    launch_mission,
    launched_template_ids,
    list_mission_templates,
)
from app.utils.constants import PRIVILEGED_ROLES
from app.utils.deep_links import task_submit_deep_link

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    deadline: str
    points: int
    status: str
    task_type: str
    is_joined_or_assigned: bool
    can_submit: bool
    submit_deep_link: str | None
    mission_code: str | None = None
    claim_mode: str | None = None
    min_people: int | None = None
    max_people: int | None = None
    workspace_chat_key: str | None = None
    deliverable: str | None = None
    squad_size: int = 0
    squad_status: str | None = None


class MissionTemplateOut(BaseModel):
    id: int
    code: str
    month: int
    title: str
    description: str
    category: str
    claim_mode: str
    min_people: int
    max_people: int
    workspace_chat_key: str
    deadline_days: int
    deliverable: str
    points: int
    counts_toward: list[str]
    repeatable: bool
    is_launched: bool


class SubtaskOut(BaseModel):
    id: int
    role_key: str
    title: str
    assignee_id: int | None
    deadline: str | None
    status: str
    deliverable: str | None


class SquadOut(BaseModel):
    id: int
    task_id: int
    responsible_user_id: int | None
    workspace_chat_key: str
    status: str
    checkpoint_at: str | None
    participant_ids: list[int]
    subtasks: list[SubtaskOut]


class SubtaskAssignIn(BaseModel):
    assignee_id: int | None


def _mission_meta(task: Task) -> dict:
    """Return Community Mission metadata without changing legacy Task behavior."""
    return (getattr(task, "reward_json", None) or {}).get("community_mission") or {}


async def _to_task_out(
    session: AsyncSession, task: Task, user: User, settings: Settings
) -> TaskOut:
    joined_ids = await task_service.joined_task_ids(session, user, [task])
    can_submit = await task_service.can_submit(session, task, user)
    meta = _mission_meta(task)
    squad = (
        await session.scalar(select(TaskSquad).where(TaskSquad.task_id == task.id))
        if meta
        else None
    )
    squad_size = 0
    if meta:
        squad_size = int(
            len(
                (
                    await session.scalars(
                        select(TaskParticipant.id).where(
                            TaskParticipant.task_id == task.id,
                            TaskParticipant.status.in_(["accepted", "joined"]),
                        )
                    )
                ).all()
            )
        )
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        deadline=task.deadline.isoformat(),
        points=task.points,
        status=task.status,
        task_type=task.task_type,
        is_joined_or_assigned=task_service.is_joined_or_assigned(task, joined_ids, user),
        can_submit=can_submit,
        submit_deep_link=(
            task_submit_deep_link(settings.bot_username, task.id)
            if can_submit and settings.bot_username
            else None
        ),
        mission_code=meta.get("code"),
        claim_mode=meta.get("claim_mode"),
        min_people=meta.get("min_people"),
        max_people=meta.get("max_people"),
        workspace_chat_key=meta.get("workspace_chat_key"),
        deliverable=meta.get("deliverable"),
        squad_size=squad_size,
        squad_status=squad.status if squad else None,
    )


def _template_out(item: CommunityMissionTemplate, launched_ids: set[int]) -> MissionTemplateOut:
    return MissionTemplateOut(
        id=item.id,
        code=item.code,
        month=item.month,
        title=item.title,
        description=item.description,
        category=item.category,
        claim_mode=item.claim_mode,
        min_people=item.min_people,
        max_people=item.max_people,
        workspace_chat_key=item.workspace_chat_key,
        deadline_days=item.deadline_days,
        deliverable=item.deliverable,
        points=item.points,
        counts_toward=list(item.counts_toward or []),
        repeatable=item.repeatable,
        is_launched=item.id in launched_ids,
    )


def _can_manage_squad(user: User, squad: TaskSquad) -> bool:
    return user.id == squad.responsible_user_id or user.role in PRIVILEGED_ROLES


async def _squad_out(session: AsyncSession, squad: TaskSquad) -> SquadOut:
    participant_ids = list(
        (
            await session.scalars(
                select(TaskParticipant.user_id).where(
                    TaskParticipant.task_id == squad.task_id,
                    TaskParticipant.status.in_(["accepted", "joined"]),
                )
            )
        ).all()
    )
    subtasks = list(
        (
            await session.scalars(
                select(TaskSubtask)
                .where(TaskSubtask.squad_id == squad.id)
                .order_by(TaskSubtask.id)
            )
        ).all()
    )
    return SquadOut(
        id=squad.id,
        task_id=squad.task_id,
        responsible_user_id=squad.responsible_user_id,
        workspace_chat_key=squad.workspace_chat_key,
        status=squad.status,
        checkpoint_at=squad.checkpoint_at.isoformat() if squad.checkpoint_at else None,
        participant_ids=participant_ids,
        subtasks=[
            SubtaskOut(
                id=item.id,
                role_key=item.role_key,
                title=item.title,
                assignee_id=item.assignee_id,
                deadline=item.deadline.isoformat() if item.deadline else None,
                status=item.status,
                deliverable=item.deliverable,
            )
            for item in subtasks
        ],
    )


# Static mission routes must be declared before /{task_id} so FastAPI never
# tries to parse the word "missions" as an integer task ID.
@router.get("/missions/templates", response_model=list[MissionTemplateOut])
async def read_mission_templates(
    month: int | None = Query(None, ge=1, le=6),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MissionTemplateOut]:
    if user.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="forbidden")
    launched_ids = await launched_template_ids(session)
    return [
        _template_out(item, launched_ids)
        for item in await list_mission_templates(session, month=month)
    ]


@router.post("/missions/{template_id}/launch", response_model=TaskOut)
async def launch_community_mission(
    template_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    if user.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="forbidden")
    template = await session.get(CommunityMissionTemplate, template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=404, detail="mission_not_found")
    task = await launch_mission(session, template, creator_id=user.id)
    return await _to_task_out(session, task, user, settings)


@router.post("/missions/launch-all", response_model=list[TaskOut])
async def launch_all_missions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[TaskOut]:
    """DELTA ToR §13/§76 Phase 2 item 9: one action to make all 26 authored
    missions available at once, instead of 26 individual launch clicks."""
    if user.role not in PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="forbidden")
    tasks = await launch_all_pending_missions(session, creator_id=user.id)
    return [await _to_task_out(session, task, user, settings) for task in tasks]


@router.get("", response_model=list[TaskOut])
async def read_tasks(
    scope: TaskScope = Query("available"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[TaskOut]:
    tasks = await list_tasks(session, user, scope)
    return [await _to_task_out(session, task, user, settings) for task in tasks]


@router.get("/{task_id}", response_model=TaskOut)
async def read_task(
    task_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None or not await task_service.can_view(session, task, user):
        raise HTTPException(status_code=404, detail="task_not_found")
    return await _to_task_out(session, task, user, settings)


@router.post("/{task_id}/claim", response_model=TaskOut)
async def claim_task(
    task_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    _, reason = await task_service.claim(session, task, user)
    if reason == "closed":
        raise HTTPException(status_code=409, detail="task_closed")
    if reason == "full":
        raise HTTPException(status_code=409, detail="task_full")
    if reason == "already_joined":
        raise HTTPException(status_code=409, detail="already_joined")
    return await _to_task_out(session, task, user, settings)


@router.get("/{task_id}/squad", response_model=SquadOut)
async def read_task_squad(
    task_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SquadOut:
    task = await session.get(Task, task_id)
    if task is None or not await task_service.can_view(session, task, user):
        raise HTTPException(status_code=404, detail="task_not_found")
    squad = await session.scalar(select(TaskSquad).where(TaskSquad.task_id == task_id))
    if squad is None:
        raise HTTPException(status_code=404, detail="squad_not_found")
    return await _squad_out(session, squad)


@router.post("/{task_id}/squad/confirm-plan", response_model=SquadOut)
async def confirm_task_squad_plan(
    task_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SquadOut:
    squad = await session.scalar(select(TaskSquad).where(TaskSquad.task_id == task_id))
    if squad is None:
        raise HTTPException(status_code=404, detail="squad_not_found")
    if not _can_manage_squad(user, squad):
        raise HTTPException(status_code=403, detail="forbidden")
    await confirm_squad_plan(session, squad)
    return await _squad_out(session, squad)


@router.patch("/{task_id}/squad/subtasks/{subtask_id}", response_model=SquadOut)
async def update_task_subtask(
    task_id: int,
    subtask_id: int,
    payload: SubtaskAssignIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SquadOut:
    squad = await session.scalar(select(TaskSquad).where(TaskSquad.task_id == task_id))
    if squad is None:
        raise HTTPException(status_code=404, detail="squad_not_found")
    if not _can_manage_squad(user, squad):
        raise HTTPException(status_code=403, detail="forbidden")
    subtask = await session.get(TaskSubtask, subtask_id)
    if subtask is None or subtask.squad_id != squad.id:
        raise HTTPException(status_code=404, detail="subtask_not_found")
    if payload.assignee_id is not None:
        is_member = await session.scalar(
            select(TaskParticipant.id).where(
                TaskParticipant.task_id == task_id,
                TaskParticipant.user_id == payload.assignee_id,
                TaskParticipant.status.in_(["accepted", "joined"]),
            )
        )
        if is_member is None:
            raise HTTPException(status_code=409, detail="assignee_not_in_squad")
    await assign_subtask(session, subtask, assignee_id=payload.assignee_id)
    return await _squad_out(session, squad)
