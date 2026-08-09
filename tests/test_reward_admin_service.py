from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, RewardItem, User
from app.services import redemption_service as svc


class RewardAdminServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def _grant_points(self, session, user_id: int, points: int) -> None:
        session.add(
            PointTransaction(
                user_id=user_id, points=points, reason="test", idempotency_key=f"test:{user_id}:{points}"
            )
        )
        await session.flush()

    # -- Participant-facing --

    async def test_list_visible_rewards_excludes_inactive(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            session.add(RewardItem(name="A", description="d", point_cost=10, created_by=admin.id, is_active=True))
            session.add(RewardItem(name="B", description="d", point_cost=20, created_by=admin.id, is_active=False))
            await session.flush()

            visible = await svc.list_visible_rewards(session)
            self.assertEqual([r.name for r in visible], ["A"])

    async def test_redeem_reward_rejects_insufficient_points(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=100, created_by=admin.id)
            session.add(reward)
            await session.flush()

            with self.assertRaises(ValueError) as ctx:
                await svc.redeem_reward(session, reward, user)
            self.assertEqual(str(ctx.exception), "insufficient_points")

    async def test_redeem_reward_rejects_duplicate_request(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=10, created_by=admin.id)
            session.add(reward)
            await session.flush()
            await self._grant_points(session, user.id, 100)

            await svc.redeem_reward(session, reward, user)
            with self.assertRaises(ValueError) as ctx:
                await svc.redeem_reward(session, reward, user)
            self.assertEqual(str(ctx.exception), "already_requested")

    async def test_redeem_reward_rejects_when_unavailable(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=10, quantity=0, created_by=admin.id)
            session.add(reward)
            await session.flush()
            await self._grant_points(session, user.id, 100)

            with self.assertRaises(ValueError) as ctx:
                await svc.redeem_reward(session, reward, user)
            self.assertEqual(str(ctx.exception), "reward_unavailable")

    async def test_redeem_reward_success_creates_pending_row(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=10, created_by=admin.id)
            session.add(reward)
            await session.flush()
            await self._grant_points(session, user.id, 100)

            redemption = await svc.redeem_reward(session, reward, user)
            self.assertEqual(redemption.status, "pending")
            self.assertEqual(redemption.points_spent, 10)

    # -- Admin-facing --

    async def test_create_and_disable_reward(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            reward = await svc.create_reward(
                session, name="A", description="d", point_cost=10, quantity=5, created_by_id=admin.id
            )
            self.assertTrue(reward.is_active)
            svc.disable_reward(reward)
            self.assertFalse(reward.is_active)

    async def test_list_open_redemptions_and_answer(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=10, created_by=admin.id)
            session.add(reward)
            await session.flush()
            await self._grant_points(session, user.id, 100)
            redemption = await svc.redeem_reward(session, reward, user)

            rows = await svc.list_open_redemptions(session)
            self.assertEqual(len(rows), 1)
            fetched_redemption, fetched_reward, fetched_user = rows[0]
            self.assertEqual(fetched_redemption.id, redemption.id)
            self.assertEqual(fetched_reward.id, reward.id)
            self.assertEqual(fetched_user.id, user.id)

            await svc.answer_redemption(session, redemption, answer="Свяжемся с Вами", admin_id=admin.id)
            self.assertEqual(redemption.status, "answered")
            self.assertEqual(redemption.admin_comment, "Свяжемся с Вами")
            self.assertEqual(redemption.reviewed_by, admin.id)

    async def test_answered_redemption_excluded_after_exchange(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            reward = RewardItem(name="A", description="d", point_cost=10, created_by=admin.id)
            session.add(reward)
            await session.flush()
            await self._grant_points(session, user.id, 100)
            redemption = await svc.redeem_reward(session, reward, user)
            await svc.answer_redemption(session, redemption, answer="ok", admin_id=admin.id)

            result = await svc.exchange_redemption(session, redemption_id=redemption.id, admin_id=admin.id)
            self.assertEqual(result.code, "exchanged")

            rows = await svc.list_open_redemptions(session)
            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
