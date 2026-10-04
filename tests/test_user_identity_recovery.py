from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.repositories.users import get_user_by_telegram_id


class TelegramIdentityRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_user_match_wins_without_fallback(self) -> None:
        user = SimpleNamespace(id=7, telegram_id=555, is_archived=False)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=user),
            get=AsyncMock(),
            flush=AsyncMock(),
        )

        resolved = await get_user_by_telegram_id(session, 555)

        self.assertIs(resolved, user)
        session.get.assert_not_awaited()
        session.flush.assert_not_awaited()

    async def test_verified_identity_restores_legacy_synthetic_user(self) -> None:
        identity = SimpleNamespace(user_id=10)
        user = SimpleNamespace(
            id=10,
            telegram_id=-1593868942000010,
            is_archived=True,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            get=AsyncMock(side_effect=[identity, user]),
            flush=AsyncMock(),
        )

        resolved = await get_user_by_telegram_id(session, 1593868942)

        self.assertIs(resolved, user)
        self.assertEqual(user.telegram_id, 1593868942)
        self.assertFalse(user.is_archived)
        session.flush.assert_awaited_once()

    async def test_normal_archived_identity_is_not_reactivated(self) -> None:
        identity = SimpleNamespace(user_id=11)
        user = SimpleNamespace(id=11, telegram_id=777, is_archived=True)
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            get=AsyncMock(side_effect=[identity, user]),
            flush=AsyncMock(),
        )

        resolved = await get_user_by_telegram_id(session, 555)

        self.assertIs(resolved, user)
        self.assertEqual(user.telegram_id, 777)
        self.assertTrue(user.is_archived)
        session.flush.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
