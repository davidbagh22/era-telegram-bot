from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import Task, User
from app.services import task_service
from app.services.activity_service import TaskScope, list_tasks
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


async def _to_task_out(
    session: AsyncSession, task: Task, user: User, settings: Settings
) -> TaskOut:
    joined_ids = await task_service.joined_task_ids(session, user, [task])
    can_submit = await task_service.can_submit(session, task, user)
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
    )


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
