from __future__ import annotations

import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant() -> SimpleNamespace:
    return SimpleNamespace(
        id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )


def _event(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=5,
        title="Летний слёт",
        description="d",
        event_date=date(2026, 9, 5),
        event_time=time(18, 0),
        location="Ереван",
        status="pending_approval",
        created_by=2,
        approved_by=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class AdminEventsApiTests(unittest.TestCase):
    def test_list_events_requires_manage_permission(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/events")
        self.assertEqual(response.status_code, 403)

    def test_list_events_for_review(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_moderation_service.list_events_for_review",
            new=AsyncMock(return_value=[_event()]),
        ):
            response = client.get("/api/v1/admin/events")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["title"], "Летний слёт")
        self.assertEqual(body[0]["event_date"], "2026-09-05")

    def test_decide_event_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/events/5/decide", json={"action": "approve", "comment": ""}
        )
        self.assertEqual(response.status_code, 404)

    def test_decide_event_invalid_action(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_event()))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/events/5/decide", json={"action": "not_real", "comment": ""}
        )
        self.assertEqual(response.status_code, 422)

    def test_decide_event_requires_comment_for_reject(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_moderation_service.decide_event",
            new=AsyncMock(side_effect=ValueError("comment_required")),
        ):
            response = client.post(
                "/api/v1/admin/events/5/decide", json={"action": "reject", "comment": ""}
            )
        self.assertEqual(response.status_code, 422)

    def test_decide_event_approve_notifies_owner(self) -> None:
        event = _event()
        owner = SimpleNamespace(telegram_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        result = SimpleNamespace(event=event, owner=owner, notice="Мероприятие одобрено")
        with (
            patch(
                "app.api.v1.admin.event_moderation_service.decide_event",
                new=AsyncMock(return_value=result),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post(
                "/api/v1/admin/events/5/decide", json={"action": "approve", "comment": ""}
            )
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
