"""Anonymous and forged Mini App sessions cannot access either media workspace.

This is a route-level regression: no real Telegram session, DB connection,
member record, role grant, or production side effect is needed.
"""
from types import SimpleNamespace
from unittest import TestCase

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_session, get_settings
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
