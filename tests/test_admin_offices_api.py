from __future__ import annotations

import unittest
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


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _office(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, title="Куратор", description="d", is_active=True)
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


class OfficesApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/offices")
        self.assertEqual(response.status_code, 403)

    def test_list_offices(self) -> None:
        office = _office()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.office_management_service.list_offices",
                new=AsyncMock(return_value=[office]),
            ),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get("/api/v1/admin/offices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Куратор")

    def test_create_office_requires_title(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/offices", json={"title": "  "})
        self.assertEqual(response.status_code, 422)

    def test_create_office_success(self) -> None:
        office = _office()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.office_management_service.create_office",
                new=AsyncMock(return_value=office),
            ),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post("/api/v1/admin/offices", json={"title": "Куратор", "description": "d"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Куратор")

    def test_delete_office_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/offices/999/delete")
        self.assertEqual(response.status_code, 404)

    def test_delete_office_success(self) -> None:
        office = _office()
        session = SimpleNamespace(get=AsyncMock(return_value=office))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.office_management_service.delete_office", new=AsyncMock(return_value=2)),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post("/api/v1/admin/offices/1/delete")
        self.assertEqual(response.status_code, 200)

    def test_search_assignable_users_empty_query_short_circuits(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/offices/assignable-users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_assign_office_user_not_found(self) -> None:
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[office, None]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/offices/1/assign", json={"user_id": 999})
        self.assertEqual(response.status_code, 404)

    def test_assign_office_success(self) -> None:
        office = _office()
        target = SimpleNamespace(id=2, telegram_id=888, first_name="Target", last_name=None)
        session = SimpleNamespace(get=AsyncMock(side_effect=[office, target]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.office_management_service.assign_office", new=AsyncMock(return_value=None)
            ),
            patch(
                "app.api.v1.admin.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post("/api/v1/admin/offices/1/assign", json={"user_id": 2})
        self.assertEqual(response.status_code, 200)

    def test_remove_assignment_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/offices/assignments/999/remove")
        self.assertEqual(response.status_code, 404)

    def test_remove_assignment_success(self) -> None:
        assignment = SimpleNamespace(id=5, office_id=1, is_active=True, ends_at=None)
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[assignment, office]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.office_management_service.list_assignments", new=AsyncMock(return_value=[])
        ):
            response = client.post("/api/v1/admin/offices/assignments/5/remove")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(assignment.is_active)


if __name__ == "__main__":
    unittest.main()
