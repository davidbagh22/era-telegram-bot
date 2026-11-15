"""Analytics, PDF/XLSX exports and delivery must deny unauthenticated callers.

Disposable FastAPI routes only. No production database, reports, Telegram
messages, delivery receipts, or real participant records are touched.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.admin_analytics_v2 import router as analytics_v2_router
from app.api.v1.admin_executive_export import router as executive_router
from app.config import Settings


ROUTES = (
    ("GET", "/api/v1/admin/analytics/v2", None),
    ("GET", "/api/v1/admin/analytics/v2/reports", None),
    ("POST", "/api/v1/admin/analytics/v2/sources/check", None),
    ("GET", "/api/v1/admin/analytics/executive-report.pdf", None),
    ("GET", "/api/v1/admin/analytics/executive-report.xlsx", None),
    ("POST", "/api/v1/admin/analytics/executive-report/send", {
        "format": "pdf",
        "request_key": "isolated-auth-test-key-123456",
    }),
)


def _participant(*, grants=()):
    return SimpleNamespace(
        id=42, telegram_id=900042, role="participant",
        is_blocked=False, is_archived=False, permission_grants=list(grants),
    )


def _client(user):
    app = FastAPI()
    app.include_router(analytics_v2_router, prefix="/api/v1")
    app.include_router(executive_router, prefix="/api/v1")
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=AssertionError("unauthorized database read")),
        scalars=AsyncMock(side_effect=AssertionError("unauthorized database read")),
    )
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:LOCALTEST",
        miniapp_auth_secret="isolated-analytics-test-secret",
    )
    app.dependency_overrides[get_bot] = lambda: None
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), session


class ProtectedAnalyticsExportAuthorizationTests(unittest.TestCase):
    def _assert_denied(self, user, expected):
        client, session = _client(user)
        with client:
            for method, path, payload in ROUTES:
                with self.subTest(method=method, path=path, expected=expected):
                    response = client.request(method, path, json=payload)
                    self.assertEqual(response.status_code, expected, response.text)
                    self.assertEqual(
                        response.headers["content-type"].split(";")[0],
                        "application/json",
                    )
                    self.assertNotIn("Content-Disposition", response.headers)
        session.scalar.assert_not_awaited()
        session.scalars.assert_not_awaited()

    def test_anonymous_cannot_read_or_send_analytics(self):
        self._assert_denied(None, 401)

    def test_participant_cannot_read_or_send_analytics(self):
        self._assert_denied(_participant(), 403)

    def test_department_scoped_analytics_grant_is_not_global_admin(self):
        grant = SimpleNamespace(
            permission="analytics.read", is_active=True,
            scope_type="department", scope_id=9,
        )
        self._assert_denied(_participant(grants=(grant,)), 403)


if __name__ == "__main__":
    unittest.main()
