#!/usr/bin/env python3
"""Prove point idempotency under real PostgreSQL concurrency.

This is intentionally not a SQLite/unit test: PostgreSQL unique-index waiting,
SAVEPOINT rollback and row visibility are the production semantics we need to
verify for duplicate Telegram/webhook/scheduler requests.
"""

from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import PointTransaction, User
from app.services.points_service import add_points
from app.utils.constants import ApplicationStatus


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    nonce = uuid.uuid4().hex[:12]
    key = f"ci:points-race:{nonce}"

    async with factory() as session:
        user = User(
            telegram_id=8_000_000_000 + int(nonce[:7], 16),
            first_name="CI",
            last_name="PointsRace",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    async def worker(index: int) -> int:
        async with factory() as session:
            transaction = await add_points(
                session,
                user_id=user_id,
                points=37,
                reason="CI concurrent idempotency verification",
                approved_by=None,
                source_type="ci_race",
                source_id=1,
                idempotency_key=key,
            )
            await session.commit()
            return transaction.id

    transaction_ids = await asyncio.wait_for(
        asyncio.gather(*(worker(index) for index in range(8))),
        timeout=30,
    )

    async with factory() as session:
        count = int(
            await session.scalar(
                select(func.count(PointTransaction.id)).where(
                    PointTransaction.idempotency_key == key
                )
            )
            or 0
        )
        points = int(
            await session.scalar(
                select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                    PointTransaction.idempotency_key == key
                )
            )
            or 0
        )

    await engine.dispose()

    if count != 1:
        raise AssertionError(f"expected exactly one transaction, got {count}")
    if points != 37:
        raise AssertionError(f"expected exactly 37 points, got {points}")
    if len(set(transaction_ids)) != 1:
        raise AssertionError(
            f"all workers must resolve to the same transaction id, got {transaction_ids}"
        )

    print("postgres points concurrency verification passed")
    print("workers=8 transactions=1 points=37")


if __name__ == "__main__":
    asyncio.run(main())
