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


class ActivityStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    points: int
    projects: int
    completed_tasks: int
    portfolio_items: int


class NextStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    title: str
    description: str
    entity_id: int | None = None
    route: str | None = None
    action_label: str = "Открыть"


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


class RankProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: str
    rank_label: str
    next_rank_label: str | None


class OpportunityProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    issuer: str
    points_needed: int
    display_state: str
    progress_text: str


class VectorAreaSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    area: str
    label: str
    value: int
    trend: str


class VectorHomeSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pulse: int
    updated_at: str
    areas: dict[str, int]
    signals: list[VectorAreaSignalOut]


class HomeSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    growth: GrowthProgressOut
    rank: RankProgressOut
    points_balance: int
    points_today: int
    points_month: int
    activity: ActivityStatsOut
    next_step: NextStepOut | None
    nearest_event: EventSummaryOut | None
    active_task: TaskSummaryOut | None
    active_project: ProjectSummaryOut | None
    opportunities: list[OpportunitySummaryOut]
    new_opportunity: OpportunityProgressOut | None
    almost_opportunity: OpportunityProgressOut | None
    locked_opportunity: OpportunityProgressOut | None
    nearest_locked_opportunity: OpportunityProgressOut | None
    tasks_available_count: int
    tasks_in_progress_count: int
    vector: VectorHomeSummaryOut | None


@router.get("/home", response_model=HomeSnapshotOut)
async def read_home(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HomeSnapshotOut:
    snapshot = await build_home_snapshot(session, user)
    return HomeSnapshotOut.model_validate(snapshot)
