from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.admin_people_detail import RichUserDetailOut
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


def _target_user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        telegram_id=999,
        first_name="Target",
        last_name=None,
        username=None,
        role="participant",
        application_status="approved",
        participation_status="new_member",
        is_blocked=False,
        is_archived=False,
        city=None,
        phone=None,
        email=None,
        occupation=None,
        motivation=None,
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


def _patch_detail_helpers():
    return (
        patch("app.api.v1.admin.total_points", new=AsyncMock(return_value=42)),
        patch("app.api.v1.admin.user_management_service.user_badges", new=AsyncMock(return_value=[])),
        patch(
            "app.api.v1.admin.user_management_service.available_badges", new=AsyncMock(return_value=[])
        ),
        patch("app.api.v1.admin.user_management_service.social_links", new=AsyncMock(return_value=[])),
        patch("app.api.v1.admin.user_management_service.portfolio_count", new=AsyncMock(return_value=0)),
        patch("app.api.v1.admin.user_management_service.active_permission_set", return_value=set()),
    )


class UsersListApiTests(unittest.TestCase):
    def test_participant_without_permissions_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/users")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_users(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.user_management_service.search_users",
            new=AsyncMock(return_value=([_target_user()], 1)),
        ):
            response = client.get("/api/v1/admin/users?query=targ")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["first_name"], "Target")

    def test_person_view_permission_allows_read_only_access(self) -> None:
        session = SimpleNamespace()
        viewer = _participant(permission_grants=[SimpleNamespace(is_active=True, permission="people.view")])
        app = _build_app(viewer, session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.user_management_service.search_users",
            new=AsyncMock(return_value=([], 0)),
        ):
            response = client.get("/api/v1/admin/users")
        self.assertEqual(response.status_code, 200)


class UserDetailApiTests(unittest.TestCase):
    def test_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/users/999")
        self.assertEqual(response.status_code, 404)

    def test_detail_contract_is_rich_participant_profile(self) -> None:
        fields = set(RichUserDetailOut.model_fields)
        required = {
            "photo_attached",
            "photo_data_url",
            "birth_date",
            "education_work",
            "skills",
            "experience",
            "available_time",
            "desired_path",
            "departments",
            "directions",
            "metrics",
            "leadership",
            "points_suggestion",
            "badge_suggestions",
            "activity",
            "surveys",
            "permissions",
            "badges",
            "available_badges",
        }
        self.assertTrue(required.issubset(fields))


class RoleChangeApiTests(unittest.TestCase):
    def test_denied_decision_returns_409(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=False, reason="Нельзя менять собственную роль")
        with patch(
            "app.api.v1.admin.user_management_service.change_role", new=AsyncMock(return_value=decision)
        ):
            response = client.post("/api/v1/admin/users/10/role", json={"role": "leader"})
        self.assertEqual(response.status_code, 409)

    def test_invalid_role_value(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/role", json={"role": "not_a_role"})
        self.assertEqual(response.status_code, 422)

    def test_success_notifies_and_syncs_chat_access(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=True, reason="")
        patches = _patch_detail_helpers()
        with (
            patch(
                "app.api.v1.admin.user_management_service.change_role", new=AsyncMock(return_value=decision)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
            patch("app.api.v1.admin.sync_user_chat_access", new=AsyncMock()) as sync_mock,
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
        ):
            response = client.post("/api/v1/admin/users/10/role", json={"role": "leader"})
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()
        sync_mock.assert_awaited_once()

    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/role", json={"role": "leader"})
        self.assertEqual(response.status_code, 403)


class BlockArchiveApiTests(unittest.TestCase):
    def test_block_success(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=True, reason="")
        patches = _patch_detail_helpers()
        with (
            patch(
                "app.api.v1.admin.user_management_service.set_blocked", new=AsyncMock(return_value=decision)
            ),
            patch("app.api.v1.admin.sync_user_chat_access", new=AsyncMock()),
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
        ):
            response = client.post("/api/v1/admin/users/10/block", json={"blocked": True})
        self.assertEqual(response.status_code, 200)

    def test_block_denied_returns_409(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=False, reason="Нельзя изменить собственный доступ")
        with patch(
            "app.api.v1.admin.user_management_service.set_blocked", new=AsyncMock(return_value=decision)
        ):
            response = client.post("/api/v1/admin/users/10/block", json={"blocked": True})
        self.assertEqual(response.status_code, 409)

    def test_archive_success(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=True, reason="")
        patches = _patch_detail_helpers()
        with (
            patch(
                "app.api.v1.admin.user_management_service.set_archived",
                new=AsyncMock(return_value=decision),
            ),
            patch("app.api.v1.admin.sync_user_chat_access", new=AsyncMock()),
            patches[0], patches[1], patches[2], patches[3], patches[4], patches[5],
        ):
            response = client.post("/api/v1/admin/users/10/archive", json={"archived": True})
        self.assertEqual(response.status_code, 200)


class PermissionToggleApiTests(unittest.TestCase):
    def test_people_manage_permission_alone_is_not_enough(self) -> None:
        # Toggling technical permissions is a full-admin-only action
        # (require_permissions_manager / can_manage_permissions) — narrower
        # than people.manage on purpose, mirroring the bot's own
        # `permissions=True` guard branch in rights_block6.py::_guard.
        session = SimpleNamespace()
        manager = _participant(
            permission_grants=[SimpleNamespace(is_active=True, permission="people.manage")]
        )
        app = _build_app(manager, session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/permissions/people.view")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_toggle(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=True, reason="")
        with patch(
            "app.api.v1.admin.user_management_service.toggle_permission",
            new=AsyncMock(return_value=(decision, True)),
        ):
            response = client.post("/api/v1/admin/users/10/permissions/people.view")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])

    def test_denied_decision_returns_409(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(allowed=False, reason="Нельзя менять собственные права")
        with patch(
            "app.api.v1.admin.user_management_service.toggle_permission",
            new=AsyncMock(return_value=(decision, False)),
        ):
            response = client.post("/api/v1/admin/users/10/permissions/people.view")
        self.assertEqual(response.status_code, 409)


class PointsAwardApiTests(unittest.TestCase):
    def test_zero_amount_rejected(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/points", json={"amount": 0, "reason": "x"})
        self.assertEqual(response.status_code, 422)

    def test_missing_reason_rejected(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/points", json={"amount": 10, "reason": "  "})
        self.assertEqual(response.status_code, 422)

    def test_participant_without_points_award_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/points", json={"amount": 10, "reason": "ok"})
        self.assertEqual(response.status_code, 403)

    def test_success_notifies_target(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.user_management_service.award_points", new=AsyncMock(return_value=52)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/users/10/points", json={"amount": 10, "reason": "ok"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["balance"], 52)
        safe_send_mock.assert_awaited_once()


class BadgeAwardApiTests(unittest.TestCase):
    def test_missing_reason_rejected(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/badges/1", json={"reason": ""})
        self.assertEqual(response.status_code, 422)

    def test_badge_not_found(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(side_effect=[target, None]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/users/10/badges/1", json={"reason": "ok"})
        self.assertEqual(response.status_code, 404)

    def test_already_awarded_returns_409(self) -> None:
        target = _target_user()
        badge = SimpleNamespace(id=1, name="Первый шаг")
        session = SimpleNamespace(get=AsyncMock(side_effect=[target, badge]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.user_management_service.award_badge", new=AsyncMock(return_value=False)
        ):
            response = client.post("/api/v1/admin/users/10/badges/1", json={"reason": "ok"})
        self.assertEqual(response.status_code, 409)

    def test_success_notifies_target(self) -> None:
        target = _target_user()
        badge = SimpleNamespace(id=1, name="Первый шаг")
        session = SimpleNamespace(get=AsyncMock(side_effect=[target, badge]))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.user_management_service.award_badge", new=AsyncMock(return_value=True)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/users/10/badges/1", json={"reason": "ok"})
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
