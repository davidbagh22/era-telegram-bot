from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RewardItem, RewardRedemption
from app.services.points_service import add_points, total_points


@dataclass(frozen=True)
class RedemptionDecision:
    code: str
    redemption: RewardRedemption | None = None
    reward: RewardItem | None = None


async def exchange_redemption(
    session: AsyncSession,
    *,
    redemption_id: int,
    admin_id: int | None,
) -> RedemptionDecision:
    """Atomically exchange an answered request and debit points exactly once."""
    redemption = await session.scalar(
        select(RewardRedemption)
        .where(RewardRedemption.id == redemption_id)
        .with_for_update()
    )
    if redemption is None:
        return RedemptionDecision("not_found")
    if redemption.status == "exchanged":
        return RedemptionDecision("already_exchanged", redemption=redemption)
    if redemption.status in {"rejected", "approved"}:
        return RedemptionDecision("already_closed", redemption=redemption)
    if redemption.status != "answered":
        return RedemptionDecision("answer_required", redemption=redemption)

    reward = await session.get(RewardItem, redemption.reward_id)
    if reward is None:
        return RedemptionDecision("reward_missing", redemption=redemption)
    if reward.quantity == 0:
        return RedemptionDecision(
            "unavailable", redemption=redemption, reward=reward
        )

    balance = await total_points(session, redemption.user_id)
    if balance < redemption.points_spent:
        return RedemptionDecision(
            "insufficient_points", redemption=redemption, reward=reward
        )

    # The row lock and terminal status make repeated clicks idempotent.
    redemption.status = "exchanged"
    redemption.reviewed_by = admin_id
    await add_points(
        session,
        user_id=redemption.user_id,
        points=-redemption.points_spent,
        reason=f"Обмен на возможность: {reward.name}",
        approved_by=admin_id,
    )
    if reward.quantity is not None:
        reward.quantity -= 1
    await session.flush()
    return RedemptionDecision("exchanged", redemption=redemption, reward=reward)


async def reject_redemption(
    session: AsyncSession,
    *,
    redemption_id: int,
    admin_id: int | None,
) -> RedemptionDecision:
    """Close a request without changing the participant's point balance."""
    redemption = await session.scalar(
        select(RewardRedemption)
        .where(RewardRedemption.id == redemption_id)
        .with_for_update()
    )
    if redemption is None:
        return RedemptionDecision("not_found")
    if redemption.status in {"exchanged", "rejected", "approved"}:
        return RedemptionDecision("already_closed", redemption=redemption)
    redemption.status = "rejected"
    redemption.reviewed_by = admin_id
    await session.flush()
    reward = await session.get(RewardItem, redemption.reward_id)
    return RedemptionDecision("rejected", redemption=redemption, reward=reward)
