from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
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
    season_id: str | None = Query(default=None, pattern=r"^[a-f0-9]{32}$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LeaderboardOut:
    if season_id:
        from app.services.ranking_season_service import season_leaderboard
        try:
            snapshot = await season_leaderboard(session, user, season_id, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        snapshot = await build_leaderboard(session, user, limit=limit)
    return LeaderboardOut.model_validate(snapshot)


@router.get("/ranking-seasons")
async def list_ranking_seasons(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    from app.services.ranking_season_service import seasons, status
    return [{key: row.value[key] for key in ('id','title','starts_at','ends_at','timezone','rules')} |
            {'status':status(row.value)} for row in await seasons(session)]


@router.get("/leaderboard/weekly", response_model=LeaderboardOut)
async def read_weekly_leaderboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LeaderboardOut:
    """DELTA ToR §52-54: Топ недели for Home -- always the fixed top-5,
    Monday 00:00 Asia/Yerevan through now."""
    snapshot = await build_weekly_leaderboard(session, user, limit=WEEKLY_TOP_LIMIT)
    return LeaderboardOut.model_validate(snapshot)
