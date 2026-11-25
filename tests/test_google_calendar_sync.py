"""#664 Google Calendar adapter — OFF by default; durable outbox; idempotent sync."""
from __future__ import annotations

import json
import tempfile
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services import google_calendar_sync_service as sync
from app.utils.constants import ApplicationStatus, EventStatus, Role


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

        row = SimpleNamespace(value={"google_event_id": "gcal-1", "sync_status": "synced", "attempts": 0})
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
        self.assertEqual(row.value["sync_status"], "synced")


class GoogleCalendarOutboxTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        url = "sqlite+aiosqlite:///" + str(Path(self.tmp.name) / "gcal.db")
        self.engine = create_async_engine(url)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.tmp.cleanup()

    async def test_enqueue_survives_disabled_sync_and_worker_noops(self):
        async with self.factory() as session:
            user = User(
                telegram_id=1,
                first_name="A",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add(user)
            await session.flush()
            ev = Event(
                title="ЭРА",
                description="d",
                event_date=date(2026, 12, 12),
                event_time=time(18, 0),
                location="Ереван",
                format="Очно",
                access_type="all",
                points_for_visit=0,
                selfie_required=False,
                created_by=user.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(ev)
            await session.flush()
            session.add(
                EventExperience(
                    event_id=ev.id,
                    short_description="d",
                    full_description="d",
                    end_time=time(20, 0),
                    is_complete=True,
                )
            )
            await sync.enqueue_calendar_sync(session, ev.id)
            await session.commit()
            event_id = ev.id
        async with self.factory() as session:
            row = await session.get(AppSetting, sync._setting_key(event_id))
            # AppSetting PK may be key string — use scalar
            from sqlalchemy import select
            row = await session.scalar(
                select(AppSetting).where(AppSetting.key == sync._setting_key(event_id))
            )
            self.assertEqual(row.value["sync_status"], "pending")
        await sync.process_pending_calendar_syncs(settings(), self.factory)
        async with self.factory() as session:
            from sqlalchemy import select
            row = await session.scalar(
                select(AppSetting).where(AppSetting.key == sync._setting_key(event_id))
            )
            self.assertEqual(row.value["sync_status"], "pending")

    async def test_enqueue_on_cancel_keeps_pending_for_patch(self):
        async with self.factory() as session:
            await sync.enqueue_calendar_sync(session, 42)
            await sync.enqueue_calendar_sync(session, 42)
            from sqlalchemy import select
            row = await session.scalar(
                select(AppSetting).where(AppSetting.key == sync._setting_key(42))
            )
            self.assertEqual(row.value["sync_status"], "pending")
            self.assertEqual(row.value["era_event_id"], 42)
