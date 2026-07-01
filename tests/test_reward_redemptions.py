import unittest
from unittest.mock import AsyncMock, patch

from app.database.models import RewardItem, RewardRedemption
from app.services.redemption_service import (
    exchange_redemption,
    reject_redemption,
)


class RewardRedemptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.redemption = RewardRedemption(
            id=7,
            reward_id=3,
            user_id=11,
            points_spent=40,
            status="pending",
        )
        self.reward = RewardItem(
            id=3,
            name="Встреча с экспертом",
            description="Персональная консультация",
            point_cost=40,
            quantity=2,
            created_by=1,
        )
        self.session = AsyncMock()
        self.session.scalar.return_value = self.redemption
        self.session.get.return_value = self.reward

    @patch("app.services.redemption_service.add_points", new_callable=AsyncMock)
    @patch("app.services.redemption_service.total_points", new_callable=AsyncMock)
    async def test_points_are_not_debited_before_admin_answer(
        self, total_points_mock: AsyncMock, add_points_mock: AsyncMock
    ) -> None:
        total_points_mock.return_value = 100

        result = await exchange_redemption(
            self.session, redemption_id=7, admin_id=1
        )

        self.assertEqual(result.code, "answer_required")
        self.assertEqual(self.redemption.status, "pending")
        add_points_mock.assert_not_awaited()
        self.assertEqual(self.reward.quantity, 2)

    @patch("app.services.redemption_service.add_points", new_callable=AsyncMock)
    @patch("app.services.redemption_service.total_points", new_callable=AsyncMock)
    async def test_exchange_debits_exactly_once(
        self, total_points_mock: AsyncMock, add_points_mock: AsyncMock
    ) -> None:
        self.redemption.status = "answered"
        total_points_mock.return_value = 100

        first = await exchange_redemption(
            self.session, redemption_id=7, admin_id=1
        )
        second = await exchange_redemption(
            self.session, redemption_id=7, admin_id=1
        )

        self.assertEqual(first.code, "exchanged")
        self.assertEqual(second.code, "already_exchanged")
        self.assertEqual(self.redemption.status, "exchanged")
        self.assertEqual(self.reward.quantity, 1)
        add_points_mock.assert_awaited_once()
        self.assertEqual(add_points_mock.await_args.kwargs["points"], -40)

    @patch("app.services.redemption_service.add_points", new_callable=AsyncMock)
    async def test_rejection_never_changes_points(
        self, add_points_mock: AsyncMock
    ) -> None:
        result = await reject_redemption(
            self.session, redemption_id=7, admin_id=1
        )

        self.assertEqual(result.code, "rejected")
        self.assertEqual(self.redemption.status, "rejected")
        self.assertEqual(self.reward.quantity, 2)
        add_points_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
