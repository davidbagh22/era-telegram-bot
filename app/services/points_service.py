from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, PortfolioItem
from app.services.audit_service import audit

REGISTRATION_POINTS = 100


async def add_points(
    session: AsyncSession,
    *,
    user_id: int,
    points: int,
    reason: str,
    approved_by: int | None,
    related_event_id: int | None = None,
    related_task_id: int | None = None,
    related_project_id: int | None = None,
) -> PointTransaction:
    is_registration_bonus = (
        points <= 5
        and related_event_id is None
        and related_task_id is None
        and related_project_id is None
        and reason.casefold().startswith("рег")
    )
    if is_registration_bonus:
        points = REGISTRATION_POINTS
    transaction = PointTransaction(
        user_id=user_id,
        points=points,
        reason=reason,
        approved_by=approved_by,
        related_event_id=related_event_id,
        related_task_id=related_task_id,
        related_project_id=related_project_id,
    )
    session.add(transaction)
    await session.flush()
    await audit(
        session,
        actor_id=approved_by,
        action="points.added",
        entity_type="user",
        entity_id=user_id,
        new_value={"points": points, "reason": reason},
    )
    return transaction


async def total_points(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user_id
            )
        )
        or 0
    )


async def add_portfolio_item(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    item_type: str,
    description: str | None = None,
    issued_by: int | None = None,
    **relations,
) -> PortfolioItem:
    item = PortfolioItem(
        user_id=user_id,
        title=title,
        item_type=item_type,
        description=description,
        issued_by=issued_by,
        **relations,
    )
    session.add(item)
    await session.flush()
    await audit(
        session,
        actor_id=issued_by,
        action="portfolio.item_added",
        entity_type="portfolio_item",
        entity_id=item.id,
        new_value={"user_id": user_id, "title": title, "type": item_type},
    )
    return item
