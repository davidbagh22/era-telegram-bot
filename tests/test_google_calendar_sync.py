"""#664 Google Calendar adapter — OFF by default; idempotent when enabled."""
from __future__ import annotations

import json
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import google_calendar_sync_service as sync
from app.utils.constants import EventStatus


def settings(**overrides):
    base = dict(
        google_calendar_sync_enabled=False,
        google_calendar_id="",
        google_calendar_service_account_json="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def event(**overrides):
    fields = dict(
        id=7,
        title="ЭРА встреча",
        description="d",
        location="Ереван",
        event_date=date(2026, 12, 12),
        event_time=time(18, 0),
        status=EventStatus.REGISTRATION_OPEN,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def experience(**overrides):
    fields = dict(end_time=time(20, 0))
    fields.update(overrides)
    return SimpleNamespace(**fields)


class GoogleCalendarSyncTests(IsolatedAsyncioTestCase):
    def test_sync_disabled_without_credentials(self):
        self.assertFalse(sync.sync_enabled(settings()))
        self.assertFalse(
            sync.sync_enabled(settings(google_calendar_sync_enabled=True, google_calendar_id="x"))
        )

    async def test_sync_noop_when_disabled(self):
        session = AsyncMock()
        self.assertIsNone(await sync.sync_published_event(session, settings(), event(), experience()))
        session.scalar.assert_not_awaited()

    async def test_sync_skips_without_end_time(self):
        cfg = settings(
            google_calendar_sync_enabled=True,
            google_calendar_id="cal",
            google_calendar_service_account_json='{"client_email":"a@b","private_key":"x"}',
        )
        session = AsyncMock()
        self.assertIsNone(
            await sync.sync_published_event(session, cfg, event(), experience(end_time=None))
        )

    async def test_insert_then_patch_idempotent(self):
        sa = {
            "client_email": "sa@era.test",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----",
        }
        cfg = settings(
            google_calendar_sync_enabled=True,
            google_calendar_id="primary",
            google_calendar_service_account_json=json.dumps(sa),
        )
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()

        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"id": "gcal-1"}
        token_resp = MagicMock()
        token_resp.raise_for_status = MagicMock()
        token_resp.json.return_value = {"access_token": "tok"}

        client = AsyncMock()
        client.post = AsyncMock(side_effect=[token_resp, post_resp])
        client.patch = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(sync.httpx, "AsyncClient", return_value=client), patch.object(
            sync.jwt, "encode", return_value="assertion"
        ):
            google_id = await sync.sync_published_event(session, cfg, event(), experience())
        self.assertEqual(google_id, "gcal-1")
        session.add.assert_called_once()

        row = SimpleNamespace(value={"google_event_id": "gcal-1"})
        session.scalar = AsyncMock(return_value=row)
        patch_resp = MagicMock()
        patch_resp.raise_for_status = MagicMock()
        patch_resp.json.return_value = {"id": "gcal-1"}
        client.post = AsyncMock(return_value=token_resp)
        client.patch = AsyncMock(return_value=patch_resp)
        with patch.object(sync.httpx, "AsyncClient", return_value=client), patch.object(
            sync.jwt, "encode", return_value="assertion"
        ):
            self.assertEqual(
                await sync.sync_published_event(session, cfg, event(), experience()), "gcal-1"
            )
        client.patch.assert_awaited()
        self.assertEqual(client.patch.await_args.kwargs["params"], {"sendUpdates": "none"})
