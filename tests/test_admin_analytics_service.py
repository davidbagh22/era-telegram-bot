from __future__ import annotations

import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import Department, Direction, Event, PointTransaction, Project, User, UserDepartment
from app.services.admin_analytics_service import build_analytics_payload
from app.utils.constants import ApplicationStatus, EventStatus


class AdminAnalyticsServiceTests(unittest.IsolatedAsyncioTestCase):
    """Real sqlite session — mirrors tests/test_consent_and_minors.py's
    pattern. Confirms the payload extracted from
    app/handlers/admin/management_ready.py behaves identically to the
    bot's own inline version it replaced."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_summary_counts_match_seeded_data(self) -> None:
        async with self.session_factory() as session:
            department = Department(name="Медиа")
            session.add(department)
            await session.flush()
            direction = Direction(name="Соцсети", department_id=department.id)
            approved = User(
                telegram_id=1, first_name="Одобрен", application_status=ApplicationStatus.APPROVED
            )
            pending = User(telegram_id=2, first_name="Ожидает", application_status=ApplicationStatus.PENDING)
            session.add_all([direction, approved, pending])
            await session.flush()
            session.add(UserDepartment(user_id=approved.id, department_id=department.id))
            session.add(
                Event(
                    title="E1", description="d", event_date=date(2026, 9, 1), event_time=time(18, 0),
                    location="Онлайн", format="online", status=EventStatus.REGISTRATION_OPEN,
                    points_for_visit=5, created_by=approved.id,
                )
            )
            session.add(Project(title="P1", short_description="d", author_id=approved.id, status="approved"))
            session.add(
                PointTransaction(
                    user_id=approved.id, points=10, reason="test", source_type="test",
                    idempotency_key="k1",
                )
            )
            session.add(
                MonthlyGoal(
                    month="2026-08", title="Цель", target_value=5, current_value=1,
                    scope_type="department", scope_id=department.id,
                )
            )
            session.add(OrganizationContact(organization_name="Партнёр"))
            await session.commit()

            payload = await build_analytics_payload(session)

            self.assertEqual(payload.summary["total_users"], 2)
            self.assertEqual(payload.summary["approved_users"], 1)
            self.assertEqual(payload.summary["pending_users"], 1)
            self.assertEqual(payload.summary["events"], 1)
            self.assertEqual(payload.summary["projects"], 1)
            self.assertEqual(payload.summary["contacts"], 1)
            self.assertEqual(payload.summary["goals"], 1)
            self.assertEqual(payload.totals[approved.id], 10)
            self.assertEqual(len(payload.department_stats), 1)
            self.assertEqual(payload.department_stats[0].members, 1)
            self.assertEqual(payload.department_stats[0].active_goals, 1)
            self.assertEqual(payload.goals[0].scope_name, "Медиа")

    async def test_deleted_goals_are_excluded(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=1, first_name="Тест")
            session.add(user)
            await session.flush()
            session.add(
                MonthlyGoal(month="2026-08", title="Активная", target_value=1, scope_type="global")
            )
            session.add(
                MonthlyGoal(
                    month="2026-08", title="Удалённая", target_value=1, scope_type="global",
                    status="deleted",
                )
            )
            await session.commit()

            payload = await build_analytics_payload(session)
            self.assertEqual(len(payload.goals), 1)
            self.assertEqual(payload.goals[0].title, "Активная")


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=999, role="admin", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=555, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    return app


class AdminAnalyticsApiTests(unittest.TestCase):
    def test_participant_cannot_read_summary(self) -> None:
        app = _build_app(_participant())
        client = TestClient(app)
        response = client.get("/api/v1/admin/analytics")
        self.assertEqual(response.status_code, 403)

    def test_admin_reads_summary(self) -> None:
        app = _build_app(_admin())
        client = TestClient(app)
        fake_payload = SimpleNamespace(
            summary={
                "total_users": 3, "approved_users": 2, "pending_users": 1,
                "events": 4, "projects": 5, "contacts": 6, "goals": 7,
            }
        )
        with patch(
            "app.api.v1.admin.build_analytics_payload", new=AsyncMock(return_value=fake_payload)
        ):
            response = client.get("/api/v1/admin/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_users"], 3)

    def test_export_returns_a_downloadable_xlsx(self) -> None:
        app = _build_app(_admin())
        client = TestClient(app)
        fake_payload = SimpleNamespace(
            users=[], events=[], projects=[], totals={}, department_stats=[],
            direction_stats=[], goals=[], contacts=[],
        )
        with (
            patch("app.api.v1.admin.build_analytics_payload", new=AsyncMock(return_value=fake_payload)),
            patch("app.api.v1.admin.build_analytics_workbook", return_value=b"fake-xlsx-bytes"),
        ):
            response = client.get("/api/v1/admin/analytics/export.xlsx?section=users")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response.headers["content-type"])
        self.assertIn("ERA_analytics_users.xlsx", response.headers["content-disposition"])
        self.assertEqual(response.content, b"fake-xlsx-bytes")


if __name__ == "__main__":
    unittest.main()
