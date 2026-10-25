from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, PortfolioItem, User
from app.services.audit_service import audit
from app.utils.constants import SOURCE_TYPE_TO_CATEGORY, PointCategory

REGISTRATION_POINTS = 100


class InsufficientPointsError(ValueError):
    pass


def make_idempotency_key(*parts: object) -> str:
    raw = ":".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()


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
    source_type: str | None = None,
    source_id: int | None = None,
    category: str | None = None,
    idempotency_key: str | None = None,
) -> PointTransaction:
    """Add one ledger entry, returning the existing row on an idempotent retry.

    The optimistic lookup is only a fast path. Correctness comes from the DB
    unique constraint plus a SAVEPOINT around the insert: if two workers race,
    one wins and the other rolls back only its conflicting insert, then returns
    the committed row instead of aborting the caller's whole business
    transaction.
    """
    if idempotency_key:
        existing = await session.scalar(
            select(PointTransaction).where(
                PointTransaction.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing

    is_registration_bonus = (
        points <= 5
        and related_event_id is None
        and related_task_id is None
        and related_project_id is None
        and reason.casefold().startswith("рег")
    )
    if is_registration_bonus:
        points = REGISTRATION_POINTS
    if points < 0:
        # Serialize debits per user so two concurrent deductions cannot both
        # validate against the same stale balance and push it below zero.
        await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
        balance = await total_points(session, user_id)
        if balance + points < 0:
            raise InsufficientPointsError("points balance cannot become negative")

    transaction = PointTransaction(
        user_id=user_id,
        points=points,
        reason=reason,
        approved_by=approved_by,
        source_type=source_type,
        source_id=source_id,
        category=category or SOURCE_TYPE_TO_CATEGORY.get(source_type, PointCategory.OTHER),
        idempotency_key=idempotency_key,
        related_event_id=related_event_id,
        related_task_id=related_task_id,
        related_project_id=related_project_id,
    )

    if idempotency_key:
        try:
            # Add only after the SAVEPOINT has started. SQLAlchemy flushes any
            # pre-existing outer changes when begin_nested() opens; keeping this
            # row inside the savepoint ensures a uniqueness race cannot poison
            # the surrounding transaction.
            async with session.begin_nested():
                session.add(transaction)
                await session.flush()
        except IntegrityError:
            existing = await session.scalar(
                select(PointTransaction).where(
                    PointTransaction.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                return existing
            # A different integrity violation must remain visible. Never turn
            # arbitrary DB corruption/constraint failures into a fake success.
            raise
    else:
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
