"""E09 Mini App channel approval API — exact day/target/digest, fail closed."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1 import admin_channel_approval as api
from app.services import daily_public_content_service as daily


class AdminChannelApprovalApiTests(IsolatedAsyncioTestCase):
    async def test_preview_and_approve_round_trip(self):
        day = datetime.now(daily.MOSCOW).date().isoformat()
        settings = SimpleNamespace(era_channel_id="@era_leaders1", era_channel_username="era_leaders1")
        admin = SimpleNamespace(id=7, telegram_id=100)
        session = AsyncMock()
        session.commit = AsyncMock()

        with patch.object(api, "text_for_day", return_value="Текст дня ЭРА"), patch.object(
            api, "approve_channel_publication", new_callable=AsyncMock
        ) as approve, patch.object(
            api, "has_channel_publication_approval", new_callable=AsyncMock, return_value=False
        ):
            approve.return_value = (daily._publication_digest("Текст дня ЭРА"), False)
            preview = await api.channel_approval_preview(admin, session, settings)
            self.assertEqual(preview.day, day)
            self.assertEqual(preview.target, "@era_leaders1")
            self.assertFalse(preview.approved)
            result = await api.channel_approval_confirm(
                api.ChannelApprovalIn(day=day, digest=preview.digest),
                admin,
                session,
                settings,
            )
            self.assertEqual(result.digest, preview.digest)
            self.assertFalse(result.already)
            approve.assert_awaited()

    async def test_rejects_stale_day_and_changed_text(self):
        settings = SimpleNamespace(era_channel_id="@era_leaders1", era_channel_username="era_leaders1")
        admin = SimpleNamespace(id=7, telegram_id=100)
        session = AsyncMock()
        with self.assertRaises(HTTPException) as stale:
            await api.channel_approval_confirm(
                api.ChannelApprovalIn(day="2020-01-01", digest="a" * 64),
                admin,
                session,
                settings,
            )
        self.assertEqual(stale.exception.status_code, 409)

        day = datetime.now(daily.MOSCOW).date().isoformat()
        with patch.object(api, "text_for_day", return_value="Живой текст"), self.assertRaises(
            HTTPException
        ) as changed:
            await api.channel_approval_confirm(
                api.ChannelApprovalIn(day=day, digest="b" * 64),
                admin,
                session,
                settings,
            )
        self.assertEqual(changed.exception.status_code, 409)
        self.assertEqual(changed.exception.detail, "channel_approval_text_changed")
