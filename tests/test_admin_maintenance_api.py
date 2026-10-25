from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.maintenance_service import CONFIRMATION_PHRASE


def _full_db_admin(**overrides) -> SimpleNamespace:
    """A DB role=admin account NOT listed in ADMIN_IDS — is_full_admin()
    would accept this, but require_maintenance_access must not, per the
    explicit product decision that maintenance stays ADMIN_IDS-only."""
    defaults = dict(id=1, telegram_id=999, role="admin", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _admin_ids_admin(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=42, role="participant", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, admin_ids: list[int] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:test-token", admin_ids=admin_ids if admin_ids is not None else [42]
    )
    return app


class MaintenanceApiAccessTests(unittest.TestCase):
    def test_db_role_admin_not_in_admin_ids_is_rejected(self) -> None:
        app = _build_app(_full_db_admin())
        client = TestClient(app)
        response = client.get("/api/v1/admin/maintenance/preview")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "maintenance_access_required")

    def test_admin_ids_member_can_preview(self) -> None:
        app = _build_app(_admin_ids_admin())
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.reset_preview", new=AsyncMock(return_value={"users": 3, "events": 1})
        ):
            response = client.get("/api/v1/admin/maintenance/preview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["confirmation_phrase"], CONFIRMATION_PHRASE)

    def test_reset_rejects_wrong_phrase_without_touching_data(self) -> None:
        app = _build_app(_admin_ids_admin())
        client = TestClient(app)
        with patch("app.api.v1.admin.reset_operational_data", new=AsyncMock()) as mock_reset:
            response = client.post(
                "/api/v1/admin/maintenance/reset", json={"confirmation_phrase": "почти правильно"}
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "confirmation_phrase_mismatch")
        mock_reset.assert_not_called()

    def test_reset_runs_with_exact_phrase(self) -> None:
        app = _build_app(_admin_ids_admin())
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.reset_operational_data", new=AsyncMock(return_value={"users": 2})
        ) as mock_reset:
            response = client.post(
                "/api/v1/admin/maintenance/reset", json={"confirmation_phrase": CONFIRMATION_PHRASE}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)
        mock_reset.assert_awaited_once()

    def test_db_role_admin_cannot_run_reset_either(self) -> None:
        app = _build_app(_full_db_admin())
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/maintenance/reset", json={"confirmation_phrase": CONFIRMATION_PHRASE}
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
