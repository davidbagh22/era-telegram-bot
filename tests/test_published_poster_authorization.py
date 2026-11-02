"""Poster editing and draft preview must reject anonymous and unscoped users.

No production calls, event writes, real Telegram identities or messages.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.admin_event_create import router as admin_event_router
from app.config import Settings


PNG = b"\x89PNG\r\n\x1a\n" + b"isolated-fixture"


def _participant(*, grants=()):
    return SimpleNamespace(
        id=20, telegram_id=900020, role="participant",
        is_blocked=False, is_archived=False, permission_grants=list(grants),
    )


def _client(user):
    app = FastAPI()
    app.include_router(admin_event_router, prefix="/api/v1")
    session = SimpleNamespace(get=AsyncMock(side_effect=AssertionError("unauthorized DB read")))

    async def session_override():
        yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:LOCALTEST", general_chat_id=-100,
    )
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), session


class PublishedPosterAuthorizationTests(unittest.TestCase):
    def _assert_denied(self, user, expected):
        client, session = _client(user)
        routes = (
            ("GET", "/api/v1/admin/events/7/poster/preview", {}),
            ("POST", "/api/v1/admin/events/7/poster", {
                "files": {"file": ("poster.png", PNG, "image/png")},
            }),
            ("POST", "/api/v1/admin/events/7/poster/remove", {}),
            ("GET", "/api/v1/admin/events/7/draft", {}),
        )
        with client:
            for method, path, kwargs in routes:
                with self.subTest(method=method, path=path, expected=expected):
                    response = client.request(method, path, **kwargs)
                    self.assertEqual(response.status_code, expected)
                    self.assertEqual(response.headers["content-type"].split(";")[0], "application/json")
        session.get.assert_not_awaited()

    def test_anonymous_user_cannot_read_or_modify_poster(self):
        self._assert_denied(None, 401)

    def test_ordinary_participant_cannot_read_or_modify_poster(self):
        self._assert_denied(_participant(), 403)

    def test_department_scoped_events_permission_is_not_global_admin(self):
        scoped_grant = SimpleNamespace(
            permission="events.manage", is_active=True,
            scope_type="department", scope_id=9,
        )
        self._assert_denied(_participant(grants=(scoped_grant,)), 403)


if __name__ == "__main__":
    unittest.main()
