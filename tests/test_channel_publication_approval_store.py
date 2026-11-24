"""Durable exact channel approvals via AppSetting (E09)."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from app.services import daily_public_content_service as daily


class ChannelPublicationApprovalStoreTests(IsolatedAsyncioTestCase):
    async def test_store_and_detect_exact_approval(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()
        digest, already = await daily.approve_channel_publication(
            session,
            day="2026-11-24",
            target="@era_leaders1",
            text="Текст дня",
            actor_id=1,
        )
        self.assertFalse(already)
        self.assertEqual(len(digest), 64)
        session.add.assert_called_once()
        setting = session.add.call_args.args[0]
        self.assertEqual(setting.key, daily.CHANNEL_APPROVALS_SETTING_KEY)
        self.assertEqual(setting.value[0]["digest"], digest)

        # Reload path: scalar returns the stored row.
        session.scalar = AsyncMock(return_value=setting)
        ok = await daily.has_channel_publication_approval(
            session, "2026-11-24", "@era_leaders1", "Текст дня"
        )
        self.assertTrue(ok)
        bad = await daily.has_channel_publication_approval(
            session, "2026-11-24", "@era_leaders1", "Другой текст"
        )
        self.assertFalse(bad)

    async def test_duplicate_approval_is_idempotent(self):
        existing = SimpleNamespace(
            key=daily.CHANNEL_APPROVALS_SETTING_KEY,
            value=[{
                "day": "2026-11-24",
                "target": "@era_leaders1",
                "digest": daily._publication_digest("Текст дня"),
            }],
            updated_by=None,
        )
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=existing)
        session.add = MagicMock()
        session.flush = AsyncMock()
        digest, already = await daily.approve_channel_publication(
            session,
            day="2026-11-24",
            target="@era_leaders1",
            text="Текст дня",
            actor_id=2,
        )
        self.assertTrue(already)
        session.add.assert_not_called()
        self.assertEqual(digest, existing.value[0]["digest"])
