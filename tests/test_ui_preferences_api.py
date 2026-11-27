from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import User
from app.services.ui_preferences_service import InvalidAccentColor, normalize_accent_color


class AccentColorNormalizationTests(unittest.TestCase):
    def test_accepts_six_digit_hex_and_lowercases(self) -> None:
        self.assertEqual(normalize_accent_color("#BC2184"), "#bc2184")
        self.assertEqual(normalize_accent_color("  #00FFaa "), "#00ffaa")

    def test_none_resets_to_default(self) -> None:
        self.assertIsNone(normalize_accent_color(None))

    def test_rejects_malformed_values(self) -> None:
        for bad in ("", "red", "#fff", "bc2184", "#bc218", "#bc21845", "#gggggg", "rgb(1,2,3)", "#bc2184;x"):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidAccentColor):
                    normalize_accent_color(bad)


class UiPreferencesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        url = f"sqlite+aiosqlite:///{Path(self._tmp.name, 'prefs.db').as_posix()}"
        self.engine = create_async_engine(url, poolclass=NullPool)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async def _prepare() -> None:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with self.factory() as session:
                session.add_all([
                    User(telegram_id=1001, first_name="Анна"),
                    User(telegram_id=1002, first_name="Борис"),
                ])
                await session.commit()

        asyncio.run(_prepare())

        app = FastAPI()
        app.include_router(api_router)
        factory = self.factory

        async def _session_override():
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        async def _user_override(x_test_user: int = Header(...)):
            async with factory() as session:
                from sqlalchemy import select

                return (await session.execute(select(User).where(User.telegram_id == x_test_user))).scalar_one()

        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_current_user] = _user_override
        self.client = TestClient(app)

    def tearDown(self) -> None:
        asyncio.run(self.engine.dispose())
        self._tmp.cleanup()

    def _get(self, telegram_id: int):
        return self.client.get("/api/v1/me/preferences", headers={"X-Test-User": str(telegram_id)})

    def _put(self, telegram_id: int, body: dict):
        return self.client.put(
            "/api/v1/me/preferences", json=body, headers={"X-Test-User": str(telegram_id)}
        )

    def test_default_is_null(self) -> None:
        response = self._get(1001)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["accent_color"])

    def test_put_persists_and_normalizes(self) -> None:
        response = self._put(1001, {"accent_color": "#1E90FF"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accent_color"], "#1e90ff")
        self.assertEqual(self._get(1001).json()["accent_color"], "#1e90ff")

    def test_two_users_are_isolated(self) -> None:
        self._put(1001, {"accent_color": "#22aa66"})
        self._put(1002, {"accent_color": "#aa2222"})
        self.assertEqual(self._get(1001).json()["accent_color"], "#22aa66")
        self.assertEqual(self._get(1002).json()["accent_color"], "#aa2222")
        self._put(1001, {"accent_color": None})
        self.assertIsNone(self._get(1001).json()["accent_color"])
        self.assertEqual(self._get(1002).json()["accent_color"], "#aa2222")

    def test_reset_with_null(self) -> None:
        self._put(1001, {"accent_color": "#123456"})
        response = self._put(1001, {"accent_color": None})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["accent_color"])
        self.assertIsNone(self._get(1001).json()["accent_color"])

    def test_invalid_values_are_rejected_and_do_not_overwrite(self) -> None:
        self._put(1001, {"accent_color": "#123456"})
        for bad in ("red", "#12345", "#zzzzzz", "javascript:alert(1)", "#12345678", ""):
            with self.subTest(bad=bad):
                response = self._put(1001, {"accent_color": bad})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self._get(1001).json()["accent_color"], "#123456")

    def test_non_string_is_rejected(self) -> None:
        self.assertEqual(self._put(1001, {"accent_color": 123456}).status_code, 422)

    def test_requires_authentication(self) -> None:
        app = FastAPI()
        app.include_router(api_router)
        app.state.session_factory = self.factory
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token", miniapp_auth_secret="test-secret"
        )
        self.assertEqual(TestClient(app).get("/api/v1/me/preferences").status_code, 401)


if __name__ == "__main__":
    unittest.main()
