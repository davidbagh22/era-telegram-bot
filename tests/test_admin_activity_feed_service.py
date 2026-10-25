from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, User
from app.services.admin_activity_feed_service import recent_activity


class AdminActivityFeedServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_known_action_gets_a_readable_summary(self) -> None:
        async with self.session_factory() as session:
            actor = User(telegram_id=1, first_name="Анна", last_name="К.")
            session.add(actor)
            await session.flush()
            session.add(AuditLog(actor_id=actor.id, action="user.approved", entity_type="user"))
            await session.commit()

            entries = await recent_activity(session)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].actor_name, "Анна К.")
            self.assertEqual(entries[0].summary, "одобрил(а) заявку")

    async def test_unmapped_action_falls_back_to_a_humanized_string_not_a_blank(self) -> None:
        async with self.session_factory() as session:
            session.add(AuditLog(actor_id=None, action="some.made_up_action", entity_type="thing"))
            await session.commit()

            entries = await recent_activity(session)
            self.assertEqual(entries[0].actor_name, None)
            self.assertEqual(entries[0].summary, "made up action")

    async def test_most_recent_first_and_respects_limit(self) -> None:
        async with self.session_factory() as session:
            for i in range(5):
                session.add(AuditLog(actor_id=None, action=f"action.{i}", entity_type="thing"))
            await session.commit()

            entries = await recent_activity(session, limit=3)
            self.assertEqual(len(entries), 3)
            # Most recently inserted (highest id) comes first.
            self.assertTrue(entries[0].id > entries[1].id > entries[2].id)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=999, role="admin", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=555, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    return app


class AdminActivityFeedApiTests(unittest.TestCase):
    def test_participant_cannot_read_recent_activity(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/recent-activity")
        self.assertEqual(response.status_code, 403)

    def test_admin_reads_recent_activity(self) -> None:
        app = _build_app(_admin())
        client = TestClient(app)
        fake_entry = SimpleNamespace(
            id=1, actor_name="Анна", summary="одобрил(а) заявку", entity_type="user",
            created_at=SimpleNamespace(isoformat=lambda: "2026-08-13T10:00:00+00:00"),
        )
        with patch("app.api.v1.admin.recent_activity", new=AsyncMock(return_value=[fake_entry])):
            response = client.get("/api/v1/admin/recent-activity")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["summary"], "одобрил(а) заявку")


if __name__ == "__main__":
    unittest.main()
