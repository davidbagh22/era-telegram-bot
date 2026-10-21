from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session
from app.api.v1.community_users import router
from app.webapp import security_headers_middleware


class CommunityPrivacyTests(unittest.TestCase):
    def client_for(self, status: str):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        target = SimpleNamespace(
            id=9, first_name="Member", last_name="Example", role="participant",
            application_status="approved", participation_status="new_member",
            is_archived=False, is_blocked=False, departments=[],
            phone="private-phone", email="private-email",
        )
        session = SimpleNamespace(get=AsyncMock(return_value=target))

        async def session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(application_status=status)
        app.dependency_overrides[get_session] = session_override
        return TestClient(app), session

    def test_unapproved_viewer_cannot_enumerate_member_cards(self):
        for status in ("pending", "rejected"):
            with self.subTest(status=status):
                client, session = self.client_for(status)
                response = client.get("/api/v1/users/9")
                self.assertEqual(response.status_code, 403)
                session.get.assert_not_awaited()

    def test_approved_viewer_receives_only_community_fields(self):
        client, _ = self.client_for("approved")
        response = client.get("/api/v1/users/9")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("phone", response.json())
        self.assertNotIn("email", response.json())


class ApiCachePrivacyTests(unittest.TestCase):
    def test_miniapp_framing_is_limited_to_self_and_official_telegram_web(self):
        app = FastAPI()
        app.middleware("http")(security_headers_middleware)

        @app.get("/app/")
        def miniapp():
            from starlette.responses import HTMLResponse
            return HTMLResponse("<html>ERA</html>", headers={"X-Frame-Options": "SAMEORIGIN"})

        client = TestClient(app)
        response = client.get("/app/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("x-frame-options", response.headers)
        self.assertEqual(
            response.headers["content-security-policy"],
            "frame-ancestors 'self' https://web.telegram.org",
        )
        # Lookalike paths must not inherit the Mini App framing exception.
        for path in ("/api/v1/profile", "/application", "/health"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")
                self.assertNotIn("content-security-policy", response.headers)

    def test_api_data_and_auth_errors_are_not_stored_but_assets_keep_cache(self):
        app = FastAPI()
        app.middleware("http")(security_headers_middleware)

        @app.get("/api/v1/profile/export")
        def export():
            from starlette.responses import Response
            return Response("personal-data", headers={"Cache-Control": "public, max-age=3600"})

        @app.get("/app/assets/bundle.js")
        def asset():
            from starlette.responses import Response
            return Response("asset", headers={"Cache-Control": "public, max-age=31536000, immutable"})

        client = TestClient(app)
        for path in ("/api/v1/profile/export", "/api/v1/missing"):
            response = client.get(path)
            self.assertEqual(response.headers["cache-control"], "no-store, private")
            self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertIn("immutable", client.get("/app/assets/bundle.js").headers["cache-control"])
