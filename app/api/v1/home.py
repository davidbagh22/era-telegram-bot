from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.home_service import build_home_snapshot

router = APIRouter(tags=["home"])


class GrowthProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    label: str
    level_index: int
    level_count: int


class NextStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    title: str
    description: str


class EventSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    event_date: str
    event_time: str
    location: str


class TaskSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    deadline: str
    points: int
    status: str


class ProjectSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str


class OpportunitySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    point_cost: int
    expires_at: str | None


class HomeSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    growth: GrowthProgressOut
    points_balance: int
    next_step: NextStepOut | None
    nearest_event: EventSummaryOut | None
    active_task: TaskSummaryOut | None
    active_project: ProjectSummaryOut | None
    opportunities: list[OpportunitySummaryOut]


@router.get("/home", response_model=HomeSnapshotOut)
async def read_home(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HomeSnapshotOut:
    snapshot = await build_home_snapshot(session, user)
    return HomeSnapshotOut.model_validate(snapshot)
