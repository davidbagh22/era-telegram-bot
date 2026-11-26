from __future__ import annotations

import unittest
from datetime import date, time, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


class EventsListBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as session:
            creator = User(
                id=1,
                telegram_id=1001,
                first_name="Анна",
                last_name="Орлова",
                application_status=ApplicationStatus.APPROVED,
            )
            viewer = User(
                id=2,
                telegram_id=1002,
                first_name="Иван",
                last_name="Петров",
                application_status=ApplicationStatus.APPROVED,
            )
            third = User(
                id=3,
                telegram_id=1003,
                first_name="Мария",
                last_name="Соколова",
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([creator, viewer, third])
            await session.flush()

            events = [
                Event(
                    id=10 + i,
                    title=f"Событие {i}",
                    description="Описание",
                    event_date=date.today() + timedelta(days=i + 1),
                    event_time=time(18, 0),
                    location="Ереван",
                    format="offline",
                    access_type="all",
                    points_for_visit=10,
                    participant_limit=5 if i % 2 == 0 else None,
                    status=EventStatus.REGISTRATION_OPEN,
                    created_by=creator.id,
                    approved_by=creator.id,
                )
                for i in range(6)
            ]
            session.add_all(events)
            await session.flush()
            session.add_all([
                EventExperience(
                    event_id=10,
                    organizer="Клуб ЭРА",
                    waitlist_enabled=True,
                    show_in_public_listing=True,
                ),
                EventExperience(
                    event_id=12,
                    organizer=None,
                    waitlist_enabled=False,
                    show_in_public_listing=True,
                ),
            ])
            session.add_all([
                EventRegistration(event_id=10, user_id=2, status=RegistrationStatus.REGISTERED),
                EventRegistration(event_id=10, user_id=3, status=RegistrationStatus.ATTENDED),
                EventRegistration(event_id=11, user_id=3, status=RegistrationStatus.WAITLIST),
                EventRegistration(event_id=12, user_id=2, status=RegistrationStatus.CANCELLED),
            ])
            await session.commit()
            self.viewer = viewer

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_read_events_batches_experience_counts_and_creators(self) -> None:
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: self.viewer
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token", bot_username="era_bot"
        )

        queries: list[str] = []

        @sa_event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def _count(_conn, _cursor, statement, *_args):
            queries.append(statement)

        try:
            client = TestClient(app)
            with (
                patch("app.api.v1.events.registered_count", side_effect=AssertionError("per-event query")),
                patch("app.api.v1.events.available_places", side_effect=AssertionError("per-event query")),
            ):
                response = client.get("/api/v1/events", params={"scope": "all"})
        finally:
            sa_event.remove(self.engine.sync_engine, "before_cursor_execute", _count)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 6)
        by_id = {item["id"]: item for item in body}

        self.assertEqual(by_id[10]["registered_count"], 2)
        self.assertEqual(by_id[10]["remaining_count"], 3)
        self.assertEqual(by_id[10]["available_places"], "3")
        self.assertEqual(by_id[10]["organizer"], "Клуб ЭРА")
        self.assertTrue(by_id[10]["waitlist_enabled"])
        self.assertEqual(by_id[10]["registration_status"], "registered")

        self.assertEqual(by_id[11]["registered_count"], 0)
        self.assertEqual(by_id[11]["available_places"], "без ограничений")
        self.assertEqual(by_id[11]["organizer"], "Анна Орлова")

        self.assertEqual(by_id[12]["registered_count"], 0)
        self.assertEqual(by_id[12]["remaining_count"], 5)
        self.assertEqual(by_id[12]["organizer"], "Анна Орлова")
        self.assertEqual(by_id[12]["registration_status"], "cancelled")

        # Batching keeps query count constant regardless of event list size
        # (list_events queries + 3 bulk queries = 10, vs 6 + 4*N before).
        self.assertLessEqual(len(queries), 10)
