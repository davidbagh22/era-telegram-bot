from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_session, get_settings
from app.api.security import create_session_token
from app.api.v1.router import api_router
from app.config import Settings

SECRET = "test-miniapp-secret"


def _settings(**overrides) -> Settings:
    defaults = dict(
        bot_token="1234567890:test-token",
        miniapp_auth_secret=SECRET,
        dev_auth_enabled=True,
        admin_ids=[],
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        telegram_id=555,
        first_name="Dev",
        last_name="User",
        role="participant",
        application_status="approved",
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = lambda: iter([SimpleNamespace()])
    return app


class MiniAppAuthEndpointTests(unittest.TestCase):
    def test_dev_bypass_issues_token_for_existing_user(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user()),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 555}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["token"])
        self.assertEqual(body["user"]["telegram_id"], 555)
        self.assertEqual(body["user"]["application_status"], "approved")

    def test_dev_bypass_disabled_falls_back_to_init_data_verification(self) -> None:
        settings = _settings(dev_auth_enabled=False)
        app = _build_app(settings)
        client = TestClient(app)
        response = client.post("/api/v1/miniapp/auth", json={"devTelegramId": 555})
        self.assertEqual(response.status_code, 401)

    def test_invalid_init_data_is_rejected(self) -> None:
        settings = _settings(dev_auth_enabled=False)
        app = _build_app(settings)
        client = TestClient(app)
        response = client.post(
            "/api/v1/miniapp/auth", json={"initData": "hash=deadbeef"}
        )
        self.assertEqual(response.status_code, 401)

    def test_unregistered_user_gets_404(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=None),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 999}
            )
        self.assertEqual(response.status_code, 404)

    def test_blocked_user_is_rejected(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user(is_blocked=True)),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 555}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "user_blocked")

    def test_archived_user_is_rejected(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user(is_archived=True)),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 555}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "user_archived")

    def test_pending_application_still_gets_a_token(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user(application_status="pending")),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 555}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["application_status"], "pending")

    def test_missing_secret_returns_server_error(self) -> None:
        settings = _settings(miniapp_auth_secret="")
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.v1.auth.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user()),
        ):
            response = client.post(
                "/api/v1/miniapp/auth", json={"devTelegramId": 555}
            )
        self.assertEqual(response.status_code, 500)


class MeEndpointTests(unittest.TestCase):
    def test_valid_token_returns_profile(self) -> None:
        settings = _settings()
        token, _ = create_session_token(
            telegram_id=555, secret=SECRET, ttl_seconds=3600
        )
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.deps.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user()),
        ):
            response = client.get(
                "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["telegram_id"], 555)

    def test_missing_token_is_rejected(self) -> None:
        settings = _settings()
        app = _build_app(settings)
        client = TestClient(app)
        response = client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self) -> None:
        settings = _settings()
        token, _ = create_session_token(
            telegram_id=555, secret=SECRET, ttl_seconds=-10
        )
        app = _build_app(settings)
        client = TestClient(app)
        response = client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_token_signed_with_other_secret_is_rejected(self) -> None:
        settings = _settings()
        token, _ = create_session_token(
            telegram_id=555, secret="wrong-secret", ttl_seconds=3600
        )
        app = _build_app(settings)
        client = TestClient(app)
        response = client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_blocked_user_is_rejected_on_me(self) -> None:
        settings = _settings()
        token, _ = create_session_token(
            telegram_id=555, secret=SECRET, ttl_seconds=3600
        )
        app = _build_app(settings)
        client = TestClient(app)
        with patch(
            "app.api.deps.get_user_by_telegram_id",
            new=AsyncMock(return_value=_user(is_blocked=True)),
        ):
            response = client.get(
                "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
            )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
