from __future__ import annotations

import unittest
from pathlib import Path
from datetime import date, datetime, time, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.services.admin_dashboard_service import dashboard_metrics
from app.utils.constants import ApplicationStatus, RegistrationStatus, Role


def _user(telegram_id: int, **overrides) -> User:
    defaults = dict(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        phone="+10000000000",
        city="City",
        education_work="Work",
        occupation="Occupation",
        motivation="Motivation",
        available_time="Evenings",
        desired_path="participant",
        personal_data_consent=True,
        is_channel_subscribed=True,
        application_status=ApplicationStatus.APPROVED,
    )
    defaults.update(overrides)
    return User(**defaults)


class AdminHomeShortMenuBackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_pending_count_counts_pending_and_needs_info_but_not_archived(self) -> None:
        async with self.factory() as session:
            session.add_all([
                _user(1, application_status=ApplicationStatus.PENDING),
                _user(2, application_status=ApplicationStatus.NEEDS_INFO),
                _user(3, application_status=ApplicationStatus.PENDING, is_archived=True),
                _user(4, application_status=ApplicationStatus.APPROVED),
            ])
            await session.flush()
            metrics = await dashboard_metrics(session)
            self.assertEqual(metrics.values["users_pending"], 2)

    async def _seed_registrations(self):
        now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        async with self.factory() as session:
            organizer = _user(10, role=Role.ADMIN)
            session.add(organizer)
            await session.flush()
            events = [
                Event(title=title, description="d", event_date=date(2026, 12, 1), event_time=time(18, 0),
                      location="Ереван", format="offline", status="published", created_by=organizer.id)
                for title in ("Встреча А", "Встреча Б")
            ]
            people = [_user(20 + i, first_name=name) for i, name in enumerate(["Анна", "Борис", "Вера", "Глеб"])]
            session.add_all(events + people)
            await session.flush()
            rows = [
                (events[0], people[0], RegistrationStatus.REGISTERED, 0, None),
                (events[1], people[1], RegistrationStatus.REGISTERED, 1, None),
                (events[0], people[2], RegistrationStatus.CANCELLED, 3, None),
                (events[1], people[3], RegistrationStatus.WAITLIST, 2, {"full_name": "Глеб Петров"}),
            ]
            for event, person, status, minutes, signup in rows:
                registration = EventRegistration(
                    event_id=event.id, user_id=person.id, status=str(status), signup=signup,
                    created_at=now + timedelta(minutes=minutes),
                )
                session.add(registration)
            await session.commit()

    def _client(self, user) -> TestClient:
        app = FastAPI()
        app.include_router(api_router)

        async def _session():
            async with self.factory() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
        return TestClient(app)

    async def test_latest_registrations_newest_first_skip_cancelled(self) -> None:
        await self._seed_registrations()
        admin = _user(555, role=Role.ADMIN)
        admin.permission_grants = []
        client = await self._in_thread(lambda: self._client(admin).get("/api/v1/admin/events/recent-registrations"))
        self.assertEqual(client.status_code, 200)
        body = client.json()
        self.assertEqual([row["participant_name"] for row in body], ["Глеб Петров", "Борис", "Анна"])
        self.assertEqual([row["event_title"] for row in body], ["Встреча Б", "Встреча Б", "Встреча А"])
        self.assertEqual(body[0]["status"], "waitlist")
        self.assertTrue(body[0]["registered_at"].startswith("2026-11-20T12:02"))

    async def test_latest_registrations_limit_and_admin_only(self) -> None:
        await self._seed_registrations()
        admin = _user(555, role=Role.ADMIN)
        admin.permission_grants = []
        limited = await self._in_thread(lambda: self._client(admin).get("/api/v1/admin/events/recent-registrations?limit=1"))
        self.assertEqual(len(limited.json()), 1)
        participant = _user(777, role=Role.PARTICIPANT)
        participant.permission_grants = []
        denied = await self._in_thread(lambda: self._client(participant).get("/api/v1/admin/events/recent-registrations"))
        self.assertEqual(denied.status_code, 403)

    @staticmethod
    async def _in_thread(fn):
        import asyncio

        return await asyncio.to_thread(fn)


if __name__ == "__main__":
    unittest.main()


FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


class AdminHomeContractTests(unittest.TestCase):
    """Source-level contract for the Mini App admin first screen."""

    def setUp(self) -> None:
        self.overview = (FRONTEND / "screens" / "admin" / "AdminOverviewScreen.tsx").read_text(encoding="utf-8")
        self.admin = (FRONTEND / "screens" / "AdminScreen.tsx").read_text(encoding="utf-8")
        self.events = (FRONTEND / "screens" / "admin" / "AdminEventsScreen.tsx").read_text(encoding="utf-8")

    def test_exactly_three_primary_actions_with_pending_badge(self) -> None:
        start = self.overview.index('data-testid="admin-primary-actions"')
        block = self.overview[start:self.overview.index("</section>", start)]
        self.assertEqual(block.count("<ActionCell"), 3)
        for title in ("Мероприятия", "Заявки", "Задачи"):
            self.assertIn(f'title="{title}"', block)
        self.assertIn("badge={pendingApplications}", block)
        self.assertIn("metrics.users_pending", self.overview)

    def test_more_section_keeps_every_previous_tool(self) -> None:
        more_start = self.overview.index("function OverviewMoreTools")
        more = self.overview[more_start:]
        before_more = self.overview[:more_start]
        self.assertIn('aria-controls="admin-more-tools"', before_more)
        for marker in (
            "Быстро сделать", "Решить сегодня", "Регистрация и состав", "Аналитика", "Сейчас",
            'title="Мероприятие"', 'title="Редактировать мероприятие"', 'title="Рассылка"',
            'title="Проект"', 'title="Участники"', "onOpenVerification", "onOpenAnalytics",
        ):
            self.assertIn(marker, more, marker)

    def test_home_links_to_events_create_participants_and_latest_registrations(self) -> None:
        self.assertIn("Последние записи", self.overview)
        self.assertIn("fetchRecentRegistrations", self.overview)
        self.assertIn("onOpenEventCreate", self.overview)
        self.assertIn('{ events: { section: "create" } }', self.admin)
        self.assertIn('{ events: { section: "operations" } }', self.admin)
        self.assertLess(self.events.index('value: "operations"'), self.events.index('value: "moderation"'))

    def test_bot_admin_deep_link_opens_events(self) -> None:
        self.assertIn('section === "events"', self.admin)
        self.assertIn('section === "tasks"', self.admin)
