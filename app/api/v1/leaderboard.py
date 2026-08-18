from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import User
from app.services.leaderboard_service import (
    DEFAULT_TOP_LIMIT,
    MAX_TOP_LIMIT,
    WEEKLY_TOP_LIMIT,
    build_leaderboard,
    build_weekly_leaderboard,
)

router = APIRouter(tags=["leaderboard"])


class LeaderboardEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    display_name: str
    points: int
    growth_level: str
    is_you: bool


class LeaderboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entries: list[LeaderboardEntryOut]
    me: LeaderboardEntryOut | None


@router.get("/leaderboard", response_model=LeaderboardOut)
async def read_leaderboard(
    limit: int = Query(default=DEFAULT_TOP_LIMIT, ge=1, le=MAX_TOP_LIMIT),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LeaderboardOut:
    snapshot = await build_leaderboard(session, user, limit=limit)
    return LeaderboardOut.model_validate(snapshot)


@router.get("/leaderboard/weekly", response_model=LeaderboardOut)
async def read_weekly_leaderboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LeaderboardOut:
    """DELTA ToR §52-54: Топ недели for Home -- always the fixed top-5,
    Monday 00:00 Asia/Yerevan through now."""
    snapshot = await build_weekly_leaderboard(session, user, limit=WEEKLY_TOP_LIMIT)
    return LeaderboardOut.model_validate(snapshot)
