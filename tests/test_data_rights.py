from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, ConsentLog, DataDeletionRequest, User
from app.services import data_rights_service


class DataRightsServiceTests(unittest.IsolatedAsyncioTestCase):
    """Real sqlite session — see tests/test_consent_and_minors.py for the
    pattern this mirrors."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_export_includes_profile_and_consent_log(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=1, first_name="Тест", city="Ереван", email="a@example.com")
            session.add(user)
            await session.flush()
            session.add(
                ConsentLog(
                    user_id=user.id,
                    consent_type="registration",
                    policy_version="v1",
                    granted=True,
                    source="bot",
                )
            )
            await session.commit()

            await session.refresh(user, attribute_names=["departments", "directions"])
            data = await data_rights_service.export_user_data(session, user)

            self.assertEqual(data["profile"]["city"], "Ереван")
            self.assertEqual(data["profile"]["email"], "a@example.com")
            self.assertEqual(len(data["consent_log"]), 1)
            self.assertEqual(data["consent_log"][0]["consent_type"], "registration")
            self.assertIn("exported_at", data)

    async def test_request_deletion_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=2, first_name="Тест")
            session.add(user)
            await session.flush()

            first = await data_rights_service.request_deletion(session, user, "please")
            second = await data_rights_service.request_deletion(session, user, "again")
            await session.commit()

            self.assertEqual(first.id, second.id)
            rows = (
                await session.scalars(
                    select(DataDeletionRequest).where(DataDeletionRequest.user_id == user.id)
                )
            ).all()
            self.assertEqual(len(rows), 1)

    async def test_request_deletion_writes_audit_log(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=3, first_name="Тест")
            session.add(user)
            await session.flush()

            await data_rights_service.request_deletion(session, user, None)
            await session.commit()

            entries = (await session.scalars(select(AuditLog))).all()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].action, "user.deletion_requested")

    async def test_fulfill_approve_anonymizes_and_archives(self) -> None:
        async with self.session_factory() as session:
            target = User(telegram_id=4, first_name="Реал Имя", city="Ереван", email="real@example.com")
            admin = User(telegram_id=5, first_name="Админ", role="admin")
            session.add_all([target, admin])
            await session.flush()

            request = await data_rights_service.request_deletion(session, target, None)
            await session.commit()

            result = await data_rights_service.fulfill_deletion_request(
                session, request, admin=admin, approve=True
            )
            await session.commit()

            self.assertEqual(result.status, data_rights_service.FULFILLED)
            self.assertIsNone(target.city)
            self.assertIsNone(target.email)
            self.assertEqual(target.first_name, "Удалённый пользователь")
            self.assertTrue(target.is_archived)
            self.assertEqual(target.archived_by, admin.id)

    async def test_fulfill_reject_leaves_data_untouched(self) -> None:
        async with self.session_factory() as session:
            target = User(telegram_id=6, first_name="Реал Имя", city="Ереван")
            admin = User(telegram_id=7, first_name="Админ", role="admin")
            session.add_all([target, admin])
            await session.flush()

            request = await data_rights_service.request_deletion(session, target, None)
            await session.commit()

            result = await data_rights_service.fulfill_deletion_request(
                session, request, admin=admin, approve=False
            )
            await session.commit()

            self.assertEqual(result.status, data_rights_service.REJECTED)
            self.assertEqual(target.city, "Ереван")
            self.assertFalse(target.is_archived)

    async def test_fulfill_is_a_noop_for_an_already_decided_request(self) -> None:
        async with self.session_factory() as session:
            target = User(telegram_id=8, first_name="Реал Имя")
            admin = User(telegram_id=9, first_name="Админ", role="admin")
            session.add_all([target, admin])
            await session.flush()

            request = await data_rights_service.request_deletion(session, target, None)
            await session.commit()
            await data_rights_service.fulfill_deletion_request(
                session, request, admin=admin, approve=True
            )
            await session.commit()

            second_call = await data_rights_service.fulfill_deletion_request(
                session, request, admin=admin, approve=False
            )
            self.assertEqual(second_call.status, data_rights_service.FULFILLED)

    async def test_list_deletion_requests_filters_by_status(self) -> None:
        async with self.session_factory() as session:
            pending_user = User(telegram_id=10, first_name="A")
            fulfilled_user = User(telegram_id=11, first_name="B")
            admin = User(telegram_id=12, first_name="Админ", role="admin")
            session.add_all([pending_user, fulfilled_user, admin])
            await session.flush()

            await data_rights_service.request_deletion(session, pending_user, None)
            fulfilled_request = await data_rights_service.request_deletion(session, fulfilled_user, None)
            await session.commit()
            await data_rights_service.fulfill_deletion_request(
                session, fulfilled_request, admin=admin, approve=True
            )
            await session.commit()

            pending = await data_rights_service.list_deletion_requests(session)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].user_id, pending_user.id)


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=555, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=999, role="admin", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    return app


class ProfileDataRightsApiTests(unittest.TestCase):
    def test_export_returns_downloadable_json(self) -> None:
        app = _build_app(_user(), SimpleNamespace())
        client = TestClient(app)
        with patch(
            "app.api.v1.profile.data_rights_service.export_user_data",
            new=AsyncMock(return_value={"exported_at": "now", "profile": {"city": "Ереван"}}),
        ):
            response = client.get("/api/v1/profile/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.json()["profile"]["city"], "Ереван")

    def test_delete_request_returns_pending_status(self) -> None:
        app = _build_app(_user(), SimpleNamespace())
        client = TestClient(app)
        fake_request = SimpleNamespace(id=7, status="pending", created_at=__import__("datetime").datetime(2026, 1, 1))
        with patch(
            "app.api.v1.profile.data_rights_service.request_deletion",
            new=AsyncMock(return_value=fake_request),
        ):
            response = client.post("/api/v1/profile/delete-request", json={"note": "please remove me"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], 7)
        self.assertEqual(body["status"], "pending")


class AdminDataRightsApiTests(unittest.TestCase):
    def test_participant_cannot_list_requests(self) -> None:
        app = _build_app(_user(), SimpleNamespace())
        client = TestClient(app)
        response = client.get("/api/v1/admin/data-deletion-requests")
        self.assertEqual(response.status_code, 403)

    def test_full_admin_can_list_requests(self) -> None:
        session = SimpleNamespace()
        target = SimpleNamespace(first_name="Кто-то", last_name=None, telegram_id=321)
        session.get = AsyncMock(return_value=target)
        fake_request = SimpleNamespace(
            id=1, user_id=42, note=None, status="pending",
            created_at=__import__("datetime").datetime(2026, 1, 1),
        )
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.data_rights_service.list_deletion_requests",
            new=AsyncMock(return_value=[fake_request]),
        ):
            response = client.get("/api/v1/admin/data-deletion-requests")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["user_id"], 42)
        self.assertEqual(body[0]["first_name"], "Кто-то")

    def test_full_admin_can_fulfill_request(self) -> None:
        session = SimpleNamespace()
        target = SimpleNamespace(first_name="Кто-то", last_name=None, telegram_id=321)
        fake_request = SimpleNamespace(
            id=1, user_id=42, note=None, status="fulfilled",
            created_at=__import__("datetime").datetime(2026, 1, 1),
        )
        session.get = AsyncMock(side_effect=[fake_request, target])
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.data_rights_service.fulfill_deletion_request", new=AsyncMock()
        ):
            response = client.post(
                "/api/v1/admin/data-deletion-requests/1/fulfill", json={"approve": True}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "fulfilled")

    def test_fulfill_unknown_request_is_404(self) -> None:
        session = SimpleNamespace()
        session.get = AsyncMock(return_value=None)
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/data-deletion-requests/999/fulfill", json={"approve": True}
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
