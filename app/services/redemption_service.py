from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RewardItem, RewardRedemption, User
from app.services.points_service import add_points, total_points

# Points-shop catalog ("Каталог возможностей" in the Bot) — a fixed-cost
# reward redeemed against a participant's point balance, reviewed by an
# admin before points are ever debited. Distinct from Auctions
# (app/services/auction_service.py): a reward's cost is fixed up front,
# not decided by bidding, and every redemption goes through an admin
# reply before the exchange can be confirmed.

OPEN_REDEMPTION_STATUSES = {"pending", "answered"}
ACTIVE_REDEMPTION_STATUSES = {"pending", "answered", "exchanged"}


# -- Participant-facing (Mini App equivalent of app/handlers/participant/growth.py's reward_* handlers) --


async def list_visible_rewards(session: AsyncSession) -> list[RewardItem]:
    return list(
        (
            await session.scalars(
                select(RewardItem).where(RewardItem.is_active.is_(True)).order_by(RewardItem.point_cost)
            )
        ).all()
    )


async def get_user_redemption(session: AsyncSession, reward_id: int, user_id: int) -> RewardRedemption | None:
    """Most recent active (non-closed) redemption a user has open for a
    reward — mirrors the Bot's own duplicate-request check exactly."""
    return await session.scalar(
        select(RewardRedemption)
        .where(
            RewardRedemption.reward_id == reward_id,
            RewardRedemption.user_id == user_id,
            RewardRedemption.status.in_(ACTIVE_REDEMPTION_STATUSES),
        )
        .order_by(RewardRedemption.created_at.desc())
    )


async def redeem_reward(session: AsyncSession, reward: RewardItem, user: User) -> RewardRedemption:
    """Raises ValueError with a code the caller maps to a message — same
    codes as the Bot's own validation order in growth.py::reward_redeem."""
    if not reward.is_active or reward.quantity == 0:
        raise ValueError("reward_unavailable")
    if await get_user_redemption(session, reward.id, user.id):
        raise ValueError("already_requested")
    balance = await total_points(session, user.id)
    if balance < reward.point_cost:
        raise ValueError("insufficient_points")
    redemption = RewardRedemption(
        reward_id=reward.id, user_id=user.id, points_spent=reward.point_cost, status="pending"
    )
    session.add(redemption)
    await session.flush()
    return redemption


# -- Admin-facing (Mini App equivalent of the admin:reward*/admin:redemption* handlers in app/handlers/admin/panel.py) --


async def list_rewards_admin(session: AsyncSession, *, include_inactive: bool = False) -> list[RewardItem]:
    conditions = [] if include_inactive else [RewardItem.is_active.is_(True)]
    return list(
        (await session.scalars(select(RewardItem).where(*conditions).order_by(RewardItem.point_cost))).all()
    )


async def create_reward(
    session: AsyncSession, *, name: str, description: str, point_cost: int, quantity: int | None, created_by_id: int
) -> RewardItem:
    reward = RewardItem(
        name=name, description=description, point_cost=point_cost, quantity=quantity, created_by=created_by_id
    )
    session.add(reward)
    await session.flush()
    return reward


def disable_reward(reward: RewardItem) -> None:
    reward.is_active = False


async def list_open_redemptions(session: AsyncSession) -> list[tuple[RewardRedemption, RewardItem, User]]:
    result = await session.execute(
        select(RewardRedemption, RewardItem, User)
        .join(RewardItem, RewardItem.id == RewardRedemption.reward_id)
        .join(User, User.id == RewardRedemption.user_id)
        .where(RewardRedemption.status.in_(OPEN_REDEMPTION_STATUSES))
        .order_by(RewardRedemption.created_at)
    )
    return list(result.all())


async def answer_redemption(
    session: AsyncSession, redemption: RewardRedemption, *, answer: str, admin_id: int | None
) -> None:
    """Records the admin's reply — the Bot only lets the final exchange
    happen after this step, so points are never debited sight-unseen."""
    redemption.status = "answered"
    redemption.admin_comment = answer
    redemption.reviewed_by = admin_id
    await session.flush()


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
        source_type="reward_redemption",
        source_id=redemption.id,
        idempotency_key=f"reward_redemption:{redemption.id}",
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
