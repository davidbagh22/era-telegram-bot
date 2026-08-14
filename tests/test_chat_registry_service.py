from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, ChatGreeting
from app.services.admin_broadcast_service import BroadcastError, send_chat_broadcast
from app.services.chat_registry_service import CHAT_KEYS, check_chats_health, list_chat_registry


class FakeBot:
    id = 42

    def __init__(self, member_status: str = "administrator", raise_on_get_member: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.member_status = member_status
        self.raise_on_get_member = raise_on_get_member

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.sent.append((chat_id, text))

    async def get_chat_member(self, chat_id: int, user_id: int):
        if self.raise_on_get_member:
            from aiogram.exceptions import TelegramBadRequest

            raise TelegramBadRequest(method=None, message="chat not found")
        return SimpleNamespace(status=self.member_status)


class ChatRegistryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_registry_covers_all_four_chats_even_when_none_bound(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token")
            entries = await list_chat_registry(session, settings)
            self.assertEqual({e.chat_key for e in entries}, set(CHAT_KEYS))
            self.assertTrue(all(not e.is_bound for e in entries))
            self.assertTrue(all(e.last_sent_at is None for e in entries))

    async def test_registry_reflects_binding_and_greeting_state(self) -> None:
        async with self.session_factory() as session:
            session.add(ChatGreeting(chat_key="general", chat_id=-100999, title="Общий чат", text="Привет!", is_enabled=True))
            await session.commit()
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
            entries = {e.chat_key: e for e in await list_chat_registry(session, settings)}
            self.assertTrue(entries["general"].is_bound)
            self.assertEqual(entries["general"].chat_id, -100999)
            self.assertTrue(entries["general"].greeting_enabled)
            self.assertIsNone(entries["internal"].greeting_enabled)

    async def test_registry_shows_last_send_from_audit_trail(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
            bot = FakeBot()
            await send_chat_broadcast(bot, settings, session, chat_key="general", text="Привет", actor_id=1)
            await session.commit()
            entries = {e.chat_key: e for e in await list_chat_registry(session, settings)}
            self.assertIsNotNone(entries["general"].last_sent_at)
            self.assertIsNone(entries["general"].last_error_at)

    async def test_registry_shows_last_error_after_a_failed_send(self) -> None:
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)

            class FailingBot(FakeBot):
                async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
                    from aiogram.exceptions import TelegramNetworkError

                    raise TelegramNetworkError(method=None, message="simulated Telegram outage")

            with self.assertRaises(BroadcastError) as ctx:
                await send_chat_broadcast(FailingBot(), settings, session, chat_key="general", text="Привет", actor_id=1)
            self.assertEqual(ctx.exception.code, "delivery_failed")
            # send_chat_broadcast() stages the failure audit row but does not
            # commit it (see app/api/v1/admin.py's endpoint, which must) --
            # simulate that commit here to test the read side in isolation.
            await session.commit()
            entries = {e.chat_key: e for e in await list_chat_registry(session, settings)}
            self.assertIsNotNone(entries["general"].last_error_at)

    async def test_health_check_reports_ok_for_bound_admin_chat(self) -> None:
        settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
        results = {r.chat_key: r for r in await check_chats_health(FakeBot(), settings)}
        self.assertTrue(results["general"].ok)
        self.assertFalse(results["internal"].ok)
        self.assertEqual(results["internal"].detail, "not_bound")

    async def test_health_check_flags_bot_not_admin(self) -> None:
        settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
        results = {r.chat_key: r for r in await check_chats_health(FakeBot(member_status="member"), settings)}
        self.assertFalse(results["general"].ok)
        self.assertEqual(results["general"].detail, "not_admin")

    async def test_health_check_flags_telegram_api_error(self) -> None:
        settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
        results = {
            r.chat_key: r for r in await check_chats_health(FakeBot(raise_on_get_member=True), settings)
        }
        self.assertFalse(results["general"].ok)

    async def test_health_check_never_writes_to_the_database(self) -> None:
        # The registry's own read query is untouched by running a health
        # check -- this is the "read-only until pressed, and even then
        # doesn't persist anything by itself" guarantee from the spec.
        async with self.session_factory() as session:
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
            await check_chats_health(FakeBot(), settings)
            count = len((await session.execute(AuditLog.__table__.select())).all())
            self.assertEqual(count, 0)


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


class ChatRegistryApiRbacTests(unittest.TestCase):
    def _build_app(self, user, bot=None) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
        app.dependency_overrides[get_bot] = lambda: bot
        return app

    def test_participant_cannot_read_chat_registry(self) -> None:
        client = TestClient(self._build_app(_participant()))
        response = client.get("/api/v1/admin/chats")
        self.assertEqual(response.status_code, 403)

    def test_participant_cannot_run_health_check(self) -> None:
        client = TestClient(self._build_app(_participant()))
        response = client.post("/api/v1/admin/chats/health-check")
        self.assertEqual(response.status_code, 403)

    def test_health_check_without_bot_is_unavailable(self) -> None:
        client = TestClient(self._build_app(_admin(), bot=None))
        response = client.post("/api/v1/admin/chats/health-check")
        self.assertEqual(response.status_code, 503)


class ChatBroadcastFailureAuditPersistsThroughRealEndpointTests(unittest.IsolatedAsyncioTestCase):
    """The one thing worth a real, DB-backed round trip here: does the
    chat.broadcast_failed audit row app/api/v1/admin.py's endpoint commits
    on a delivery failure actually survive being followed by an
    HTTPException, or does get_session's request-scope rollback erase it
    (the exact bug shape this endpoint was written to avoid)."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_failed_chat_broadcast_leaves_a_readable_audit_row(self) -> None:
        class FailingBot:
            async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
                from aiogram.exceptions import TelegramNetworkError

                raise TelegramNetworkError(method=None, message="simulated outage")

        app = FastAPI()
        app.include_router(api_router)
        # Real get_session (app/api/deps.py) reads request.app.state
        # directly rather than being overridden -- exercises the exact
        # commit-on-clean-exit / rollback-on-exception behavior the fix
        # depends on, not a simplified stand-in for it.
        app.state.session_factory = self.session_factory

        app.dependency_overrides[get_current_user] = lambda: _admin()
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token", general_chat_id=-100999
        )
        app.dependency_overrides[get_bot] = lambda: FailingBot()
        client = TestClient(app)

        response = client.post("/api/v1/admin/broadcast/chat", json={"chat_key": "general", "text": "Привет"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "delivery_failed")

        async with self.session_factory() as session:
            entries = {
                e.chat_key: e
                for e in await list_chat_registry(
                    session, Settings(bot_token="1234567890:test-token", general_chat_id=-100999)
                )
            }
            self.assertIsNotNone(
                entries["general"].last_error_at,
                "the failed send's audit row did not survive the request -- "
                "the commit-before-raise fix in admin.py regressed",
            )


if __name__ == "__main__":
    unittest.main()
