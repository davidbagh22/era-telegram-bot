from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Task,
    TaskParticipant,
    User,
)
from app.services.activity_service import calendar_items, history_entries, list_events, list_tasks
from app.utils.constants import EventStatus, RegistrationStatus, TaskStatus


class ActivityServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1, **overrides) -> User:
        defaults = dict(
            telegram_id=telegram_id,
            first_name="Dev",
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
            role="participant",
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _event(self, *, created_by: int, days_offset: int, status=EventStatus.PUBLISHED) -> Event:
        return Event(
            title="Meetup",
            description="d",
            event_date=date.today() + timedelta(days=days_offset),
            event_time=time(18, 0),
            location="HQ",
            format="offline",
            created_by=created_by,
            status=status,
        )

    async def test_all_scope_lists_published_upcoming_events_with_registration_flag(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = self._event(created_by=user.id, days_offset=2)
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.REGISTERED
                )
            )
            await session.flush()

            rows = await list_events(session, user, "all")
            self.assertEqual(len(rows), 1)
            fetched_event, registration = rows[0]
            self.assertEqual(fetched_event.id, event.id)
            self.assertEqual(registration.status, RegistrationStatus.REGISTERED)

    async def test_all_scope_excludes_draft_events(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            session.add(self._event(created_by=user.id, days_offset=2, status=EventStatus.DRAFT))
            await session.flush()

            rows = await list_events(session, user, "all")
            self.assertEqual(rows, [])

    async def test_mine_scope_only_active_registrations(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event1 = self._event(created_by=user.id, days_offset=1)
            event2 = self._event(created_by=user.id, days_offset=3)
            session.add_all([event1, event2])
            await session.flush()
            session.add_all(
                [
                    EventRegistration(
                        event_id=event1.id, user_id=user.id, status=RegistrationStatus.REGISTERED
                    ),
                    EventRegistration(
                        event_id=event2.id, user_id=user.id, status=RegistrationStatus.CANCELLED
                    ),
                ]
            )
            await session.flush()

            rows = await list_events(session, user, "mine")
            self.assertEqual([event.id for event, _ in rows], [event1.id])

    async def test_past_scope_only_past_dates(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            past_event = self._event(
                created_by=user.id, days_offset=-5, status=EventStatus.COMPLETED
            )
            future_event = self._event(created_by=user.id, days_offset=5)
            session.add_all([past_event, future_event])
            await session.flush()
            session.add_all(
                [
                    EventRegistration(
                        event_id=past_event.id, user_id=user.id, status=RegistrationStatus.ATTENDED
                    ),
                    EventRegistration(
                        event_id=future_event.id,
                        user_id=user.id,
                        status=RegistrationStatus.REGISTERED,
                    ),
                ]
            )
            await session.flush()

            rows = await list_events(session, user, "past")
            self.assertEqual([event.id for event, _ in rows], [past_event.id])

    async def _task(self, *, creator_id: int, **overrides) -> Task:
        defaults = dict(
            title="Task",
            description="d",
            creator_id=creator_id,
            deadline=datetime.now(timezone.utc) + timedelta(days=1),
            points=10,
        )
        defaults.update(overrides)
        return Task(**defaults)

    async def test_available_scope_excludes_joined_challenge(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            open_task = await self._task(
                creator_id=user.id, task_type="challenge", status=TaskStatus.PUBLISHED
            )
            joined_task = await self._task(
                creator_id=user.id, task_type="challenge", status=TaskStatus.PUBLISHED
            )
            session.add_all([open_task, joined_task])
            await session.flush()
            session.add(
                TaskParticipant(task_id=joined_task.id, user_id=user.id, status="accepted")
            )
            await session.flush()

            tasks = await list_tasks(session, user, "available")
            self.assertEqual([task.id for task in tasks], [open_task.id])

    async def test_mine_scope_includes_assigned_and_joined_non_archived(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            assigned = await self._task(
                creator_id=user.id, assignee_id=user.id, status=TaskStatus.IN_PROGRESS
            )
            archived = await self._task(
                creator_id=user.id, assignee_id=user.id, status=TaskStatus.COMPLETED
            )
            session.add_all([assigned, archived])
            await session.flush()

            tasks = await list_tasks(session, user, "mine")
            self.assertEqual([task.id for task in tasks], [assigned.id])

    async def test_review_and_completed_scopes(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            review_task = await self._task(
                creator_id=user.id, assignee_id=user.id, status=TaskStatus.REVIEW
            )
            completed_task = await self._task(
                creator_id=user.id, assignee_id=user.id, status=TaskStatus.COMPLETED
            )
            session.add_all([review_task, completed_task])
            await session.flush()

            review = await list_tasks(session, user, "review")
            completed = await list_tasks(session, user, "completed")
            self.assertEqual([task.id for task in review], [review_task.id])
            self.assertEqual([task.id for task in completed], [completed_task.id])

    async def test_calendar_combines_events_and_task_deadlines_sorted(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = self._event(created_by=user.id, days_offset=10)
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.REGISTERED
                )
            )
            task = await self._task(
                creator_id=user.id,
                assignee_id=user.id,
                status=TaskStatus.IN_PROGRESS,
                deadline=datetime.now(timezone.utc) + timedelta(days=2),
            )
            session.add(task)
            await session.flush()

            items = await calendar_items(session, user, days_ahead=30)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].kind, "task")
            self.assertEqual(items[1].kind, "event")

    async def test_calendar_respects_horizon(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = self._event(created_by=user.id, days_offset=90)
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.REGISTERED
                )
            )
            await session.flush()

            items = await calendar_items(session, user, days_ahead=30)
            self.assertEqual(items, [])

    async def test_history_includes_attended_events_completed_tasks_points_and_portfolio(
        self,
    ) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = self._event(
                created_by=user.id, days_offset=-3, status=EventStatus.COMPLETED
            )
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.ATTENDED
                )
            )
            task = await self._task(
                creator_id=user.id, assignee_id=user.id, status=TaskStatus.COMPLETED
            )
            session.add(task)
            session.add(
                PortfolioItem(
                    user_id=user.id, title="Certificate", item_type="certificate", status="verified"
                )
            )
            session.add(
                PortfolioItem(
                    user_id=user.id, title="Unverified", item_type="certificate", status="pending"
                )
            )
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=20,
                    reason="Bonus",
                    approved_by=user.id,
                    source_type="test",
                    idempotency_key="k1",
                )
            )
            await session.flush()

            entries = await history_entries(session, user)
            kinds = {entry.kind for entry in entries}
            self.assertEqual(kinds, {"event_attended", "task_completed", "portfolio", "points"})
            titles = {entry.title for entry in entries}
            self.assertNotIn("Unverified", titles)


if __name__ == "__main__":
    unittest.main()
