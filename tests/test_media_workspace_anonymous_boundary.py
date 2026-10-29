"""Anonymous and forged Mini App sessions cannot access either media workspace.

This is a route-level regression: no real Telegram session, DB connection,
member record, role grant, or production side effect is needed.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_session, get_settings
from app.api.security import create_session_token
from app.api.v1.media_workspace import router


class MediaWorkspaceAnonymousBoundaryTests(TestCase):
    def test_all_read_and_write_routes_reject_missing_or_invalid_session(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_session] = lambda: SimpleNamespace()
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            miniapp_auth_secret="isolated-test-only-secret"
        )

        routes = (
            ("GET", "/media/workspaces", None),
            ("GET", "/media/workspaces/era/calendar", None),
            ("GET", "/media/workspaces/ksoors/calendar", None),
            ("GET", "/media/workspaces/era/team", None),
            ("GET", "/media/workspaces/ksoors/editors", None),
            ("POST", "/media/workspaces/era/calendar", {
                "request_key": "00000000-0000-4000-8000-000000000001",
                "title": "Тестовый материал",
            }),
            ("PATCH", "/media/workspaces/era/calendar/1", {
                "revision": 0,
                "status": "ready",
            }),
            ("POST", "/media/workspaces/ksoors/editors", {
                "user_id": 1,
                "enabled": True,
                "revision": 0,
            }),
        )

        with TestClient(app) as client:
            for headers, expected_detail in (
                ({}, "missing_token"),
                ({"Authorization": "Bearer forged-token"}, "malformed_token"),
            ):
                for method, path, payload in routes:
                    with self.subTest(method=method, path=path, headers=headers):
                        response = client.request(method, path, headers=headers, json=payload)
                        self.assertEqual(response.status_code, 401, response.text)
                        self.assertEqual(response.json()["detail"], expected_detail)

    def test_blocked_and_archived_accounts_cannot_reuse_signed_session(self):
        secret = "isolated-test-only-secret"
        token, _ = create_session_token(telegram_id=123456, secret=secret, ttl_seconds=600)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_session] = lambda: SimpleNamespace()
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
            miniapp_auth_secret=secret
        )
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.api.deps.get_user_by_telegram_id", new_callable=AsyncMock) as lookup:
            with TestClient(app) as client:
                for blocked, archived, expected in (
                    (True, False, "user_blocked"),
                    (False, True, "user_archived"),
                ):
                    lookup.return_value = SimpleNamespace(
                        is_blocked=blocked, is_archived=archived
                    )
                    for method, path, payload in (
                        ("GET", "/media/workspaces", None),
                        ("GET", "/media/workspaces/era/calendar", None),
                        ("GET", "/media/workspaces/ksoors/team", None),
                        ("POST", "/media/workspaces/era/calendar", {
                            "request_key": "00000000-0000-4000-8000-000000000002",
                            "title": "Недоступный материал",
                        }),
                        ("PATCH", "/media/workspaces/era/calendar/1", {
                            "revision": 0, "status": "ready",
                        }),
                        ("POST", "/media/workspaces/era/editors", {
                            "user_id": 1, "enabled": True, "revision": 0,
                        }),
                    ):
                        with self.subTest(blocked=blocked, archived=archived, path=path):
                            response = client.request(method, path, headers=headers, json=payload)
                            self.assertEqual(response.status_code, 403, response.text)
                            self.assertEqual(response.json()["detail"], expected)
