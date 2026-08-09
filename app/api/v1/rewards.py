from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import RewardItem, User
from app.services import redemption_service

# Points-shop catalog — the participant-facing half of the reward_*
# handlers in app/handlers/participant/growth.py. Distinct from
# /api/v1/auctions and /api/v1/opportunities: a reward's cost is fixed
# up front, and every redemption goes through an admin reply before
# points are ever debited.

router = APIRouter(prefix="/rewards", tags=["rewards"])


class RewardOut(BaseModel):
    id: int
    name: str
    description: str
    point_cost: int
    quantity: int | None
    my_status: str | None


async def _to_reward_out(session: AsyncSession, reward: RewardItem, user: User) -> RewardOut:
    redemption = await redemption_service.get_user_redemption(session, reward.id, user.id)
    return RewardOut(
        id=reward.id,
        name=reward.name,
        description=reward.description,
        point_cost=reward.point_cost,
        quantity=reward.quantity,
        my_status=redemption.status if redemption else None,
    )


@router.get("", response_model=list[RewardOut])
async def list_rewards(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RewardOut]:
    rewards = await redemption_service.list_visible_rewards(session)
    return [await _to_reward_out(session, reward, user) for reward in rewards]


@router.post("/{reward_id}/redeem", response_model=RewardOut)
async def redeem_reward(
    reward_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RewardOut:
    reward = await session.get(RewardItem, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="reward_not_found")
    try:
        await redemption_service.redeem_reward(session, reward, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _to_reward_out(session, reward, user)
