"""Reversible public-listing switch must deny unauthenticated and unscoped callers.

The tests use a disposable FastAPI app and no production database, Telegram API,
real event or points ledger.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.admin_event_create import router as event_router
from app.config import Settings


def _participant(*, grants=()):
    return SimpleNamespace(
        id=24, telegram_id=900024, role="participant",
        is_blocked=False, is_archived=False, permission_grants=list(grants),
    )


def _client(user):
    app = FastAPI()
    app.include_router(event_router, prefix="/api/v1")
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


class PublicListingAuthorizationTests(unittest.TestCase):
    def _assert_denied(self, user, status):
        client, session = _client(user)
        with client:
            for visible in (False, True):
                with self.subTest(visible=visible, status=status):
                    response = client.patch(
                        "/api/v1/admin/events/7/listing",
                        json={"visible": visible},
                    )
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(
                        response.headers["content-type"].split(";")[0],
                        "application/json",
                    )
        session.get.assert_not_awaited()

    def test_anonymous_cannot_hide_or_restore(self):
        self._assert_denied(None, 401)

    def test_participant_cannot_hide_or_restore(self):
        self._assert_denied(_participant(), 403)

    def test_department_scoped_grant_is_not_global_event_manager(self):
        scoped = SimpleNamespace(
            permission="events.manage", is_active=True,
            scope_type="department", scope_id=9,
        )
        self._assert_denied(_participant(grants=(scoped,)), 403)


if __name__ == "__main__":
    unittest.main()
