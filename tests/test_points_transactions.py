import unittest
from unittest.mock import AsyncMock, Mock

from app.database.models import PointTransaction
from app.services.points_service import InsufficientPointsError, add_points
from app.utils.constants import PointCategory


class PointsTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_idempotency_key_reuses_existing_transaction(self) -> None:
        existing = PointTransaction(
            id=10,
            user_id=3,
            points=25,
            reason="once",
            idempotency_key="event:1:user:3",
        )
        session = AsyncMock()
        session.scalar.return_value = existing
        session.add = Mock()

        result = await add_points(
            session,
            user_id=3,
            points=25,
            reason="once",
            approved_by=1,
            idempotency_key="event:1:user:3",
        )

        self.assertIs(result, existing)
        session.add.assert_not_called()
        session.flush.assert_not_awaited()

    async def test_negative_balance_is_rejected(self) -> None:
        session = AsyncMock()
        session.scalar.side_effect = [None, 3, 10]

        with self.assertRaises(InsufficientPointsError):
            await add_points(
                session,
                user_id=3,
                points=-15,
                reason="spend",
                approved_by=1,
                idempotency_key="spend:3:15",
            )

        session.add.assert_not_called()

    async def test_category_is_derived_from_source_type(self) -> None:
        session = AsyncMock()
        session.scalar.return_value = None
        session.add = Mock()

        await add_points(
            session,
            user_id=3,
            points=100,
            reason="Посещение мероприятия",
            approved_by=1,
            source_type="event_attendance",
            idempotency_key="event:1:user:3",
        )

        transaction = session.add.call_args_list[0][0][0]
        self.assertEqual(transaction.category, PointCategory.EVENT)

    async def test_category_falls_back_to_other_for_unknown_source_type(self) -> None:
        session = AsyncMock()
        session.scalar.return_value = None
        session.add = Mock()

        await add_points(
            session,
            user_id=3,
            points=10,
            reason="something new",
            approved_by=1,
            source_type="some_future_source_type",
            idempotency_key="future:1",
        )

        transaction = session.add.call_args_list[0][0][0]
        self.assertEqual(transaction.category, PointCategory.OTHER)

    async def test_explicit_category_overrides_source_type_mapping(self) -> None:
        session = AsyncMock()
        session.scalar.return_value = None
        session.add = Mock()

        await add_points(
            session,
            user_id=3,
            points=10,
            reason="explicit",
            approved_by=1,
            source_type="event_attendance",
            category=PointCategory.MANUAL,
            idempotency_key="explicit:1",
        )

        transaction = session.add.call_args_list[0][0][0]
        self.assertEqual(transaction.category, PointCategory.MANUAL)


if __name__ == "__main__":
    unittest.main()
