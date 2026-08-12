from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import Department, Direction, User, UserDepartment, UserDirection
from app.services.admin_broadcast_service import (
    BroadcastError,
    department_options,
    direction_options,
    preview_recipient_count,
    send_chat_broadcast,
    send_personal_broadcast,
)
from app.utils.constants import ApplicationStatus


class FakeBot:
    """Mirrors tests/test_broadcast_service.py's FakeBot."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.sent.append((chat_id, text))


class AdminBroadcastServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _seed_users(self, session):
        department = Department(name="Медиа")
        session.add(department)
        await session.flush()
        direction = Direction(name="Соцсети", department_id=department.id)
        session.add(direction)
        await session.flush()

        # ASCII city names — SQLite's LOWER() only folds ASCII case (no ICU
        # extension loaded in tests), so a Cyrillic name would make the
        # case-insensitivity assertion an artifact of the test DB rather
        # than of the matching logic itself (same func.lower() the bot
        # handler used before extraction — see app/handlers/admin/panel.py).
        approved_media = User(
            telegram_id=1, first_name="A", application_status=ApplicationStatus.APPROVED,
            role="participant", city="Moscow", age=20,
        )
        approved_leader = User(
            telegram_id=2, first_name="B", application_status=ApplicationStatus.APPROVED,
            role="leader", city="Kazan", age=30,
        )
        pending = User(telegram_id=3, first_name="C", application_status=ApplicationStatus.PENDING)
        blocked = User(
            telegram_id=4, first_name="D", application_status=ApplicationStatus.APPROVED, is_blocked=True
        )
        session.add_all([approved_media, approved_leader, pending, blocked])
        await session.flush()
        session.add(UserDepartment(user_id=approved_media.id, department_id=department.id))
        session.add(UserDirection(user_id=approved_media.id, direction_id=direction.id))
        await session.commit()
        return department, direction, approved_media, approved_leader

    async def test_all_audience_excludes_pending_and_blocked(self) -> None:
        async with self.session_factory() as session:
            await self._seed_users(session)
            count = await preview_recipient_count(session, "all", None)
            self.assertEqual(count, 2)

    async def test_role_audience_filters(self) -> None:
        async with self.session_factory() as session:
            await self._seed_users(session)
            count = await preview_recipient_count(session, "role", "leader")
            self.assertEqual(count, 1)

    async def test_department_audience_filters(self) -> None:
        async with self.session_factory() as session:
            department, _, _, _ = await self._seed_users(session)
            count = await preview_recipient_count(session, "department", str(department.id))
            self.assertEqual(count, 1)

    async def test_direction_audience_filters(self) -> None:
        async with self.session_factory() as session:
            _, direction, _, _ = await self._seed_users(session)
            count = await preview_recipient_count(session, "direction", str(direction.id))
            self.assertEqual(count, 1)

    async def test_city_audience_is_case_insensitive(self) -> None:
        async with self.session_factory() as session:
            await self._seed_users(session)
            count = await preview_recipient_count(session, "city", "MOSCOW")
            self.assertEqual(count, 1)

    async def test_age_audience_range(self) -> None:
        async with self.session_factory() as session:
            await self._seed_users(session)
            count = await preview_recipient_count(session, "age", "25_34")
            self.assertEqual(count, 1)

    async def test_role_audience_without_filter_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(BroadcastError):
                await preview_recipient_count(session, "role", None)

    async def test_invalid_audience_raises(self) -> None:
        async with self.session_factory() as session:
            with self.assertRaises(BroadcastError):
                await preview_recipient_count(session, "bogus", None)

    async def test_send_personal_broadcast_delivers_and_audits(self) -> None:
        async with self.session_factory() as session:
            await self._seed_users(session)
            bot = FakeBot()
            result = await send_personal_broadcast(
                bot, session, audience="all", filter_value=None, text="Привет!", author_id=1,
            )
            self.assertEqual(result.total, 2)
            self.assertEqual(result.sent, 2)
            self.assertEqual(len(bot.sent), 2)

    async def test_send_personal_broadcast_rejects_empty_text(self) -> None:
        async with self.session_factory() as session:
            bot = FakeBot()
            with self.assertRaises(BroadcastError):
                await send_personal_broadcast(
                    bot, session, audience="all", filter_value=None, text="   ", author_id=1,
                )

    async def test_department_and_direction_options(self) -> None:
        async with self.session_factory() as session:
            department, direction, _, _ = await self._seed_users(session)
            deps = await department_options(session)
            dirs = await direction_options(session)
            self.assertEqual(deps[0].label, "Медиа")
            self.assertEqual(dirs[0].label, "Соцсети")

    async def test_send_chat_broadcast_requires_bound_chat(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token")
            bot = FakeBot()
            with self.assertRaises(BroadcastError) as ctx:
                await send_chat_broadcast(
                    bot, settings, session, chat_key="general", text="Привет", actor_id=1
                )
            self.assertEqual(ctx.exception.code, "chat_not_bound")

    async def test_send_chat_broadcast_delivers_when_bound(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100123)
            bot = FakeBot()
            await send_chat_broadcast(bot, settings, session, chat_key="general", text="Привет", actor_id=1)
            self.assertEqual(bot.sent, [(-100123, "Привет")])

    async def test_send_chat_broadcast_rejects_unknown_chat_key(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token")
            bot = FakeBot()
            with self.assertRaises(BroadcastError):
                await send_chat_broadcast(bot, settings, session, chat_key="bogus", text="Привет", actor_id=1)


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


def _build_app(user, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class AdminBroadcastApiTests(unittest.TestCase):
    def test_participant_cannot_read_audience_options(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/broadcast/audience-options")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_send_broadcast(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.post("/api/v1/admin/broadcast", json={"audience": "all", "text": "hi"})
        self.assertEqual(response.status_code, 403)

    def test_admin_sends_personal_broadcast(self) -> None:
        app = _build_app(_admin(), bot=FakeBot())
        client = TestClient(app)
        fake_result = SimpleNamespace(
            total=3, sent=3, failed=0, duplicates=0, temporary_failed=0, permanent_failed=0
        )
        with patch("app.api.v1.admin.send_personal_broadcast", new=AsyncMock(return_value=fake_result)):
            response = client.post("/api/v1/admin/broadcast", json={"audience": "all", "text": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 3)

    def test_admin_broadcast_without_bot_is_unavailable(self) -> None:
        app = _build_app(_admin(), bot=None)
        client = TestClient(app)
        response = client.post("/api/v1/admin/broadcast", json={"audience": "all", "text": "hi"})
        self.assertEqual(response.status_code, 503)

    def test_admin_sends_chat_broadcast(self) -> None:
        app = _build_app(_admin(), bot=FakeBot())
        client = TestClient(app)
        with patch("app.api.v1.admin.send_chat_broadcast", new=AsyncMock(return_value=None)):
            response = client.post("/api/v1/admin/broadcast/chat", json={"chat_key": "general", "text": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
