"""A bounded recovery worker must revisit old failures without starving new events."""
from datetime import date, time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services.event_publication_service import deliver_pending_event_announcements
from app.utils.constants import EventStatus


class EventRecoveryFairnessTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def events(self, count):
        async with self.sessions() as session:
            user = User(telegram_id=1, first_name="CI admin")
            session.add(user)
            await session.flush()
            events = [Event(title=f"CI event {i}", description="CI", event_date=date(2026, 11, 7),
                            event_time=time(18), location="CI", format="offline", created_by=user.id,
                            status=EventStatus.PUBLISHED) for i in range(count)]
            session.add_all(events)
            await session.flush()
            session.add_all([EventExperience(event_id=event.id, announcement_status="pending") for event in events])
            await session.commit()
            return [event.id for event in events]

    async def test_twenty_old_failures_cannot_starve_the_next_event_across_runs(self):
        ids = await self.events(21)
        # Delivery deliberately makes no progress, as with a missing Telegram topic.
        with patch("app.services.event_publication_service.deliver_event_announcement", new=AsyncMock()) as deliver:
            await deliver_pending_event_announcements(None, None, self.sessions)
            self.assertEqual([call.args[3] for call in deliver.await_args_list], ids[:20])
            deliver.reset_mock()
            restarted_factory = async_sessionmaker(self.engine, expire_on_commit=False)
            await deliver_pending_event_announcements(None, None, restarted_factory)
            attempted = [call.args[3] for call in deliver.await_args_list]
            self.assertEqual(attempted, [ids[20], *ids[:19]])
            self.assertEqual(len(attempted), len(set(attempted)))
        async with self.sessions() as session:
            statuses = (await session.scalars(select(EventExperience.announcement_status))).all()
            self.assertEqual(statuses, ["pending"] * 21)

    async def test_interrupted_batch_is_revisited_after_the_next_page(self):
        ids = await self.events(21)
        with patch("app.services.event_publication_service.deliver_event_announcement", new=AsyncMock(side_effect=RuntimeError("worker stopped"))):
            with self.assertRaisesRegex(RuntimeError, "worker stopped"):
                await deliver_pending_event_announcements(None, None, self.sessions)
        with patch("app.services.event_publication_service.deliver_event_announcement", new=AsyncMock()) as deliver:
            await deliver_pending_event_announcements(None, None, self.sessions)
            await deliver_pending_event_announcements(None, None, self.sessions)
            attempted = [call.args[3] for call in deliver.await_args_list]
            self.assertEqual(attempted[0], ids[20])
            self.assertEqual(set(attempted), set(ids))

    async def test_transient_database_failure_before_cursor_commit_retries_pending_page(self):
        """A failed database lookup must not advance the durable recovery cursor.

        Isolated SQLite + mocked Telegram: this tests retry eligibility, not
        real PostgreSQL DNS recovery or delivery acceptance.
        """
        ids = await self.events(3)
        original_scalar = AsyncSession.scalar
        failed_once = False

        async def fail_first_scalar(session, statement, *args, **kwargs):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError("simulated transient database DNS failure")
            return await original_scalar(session, statement, *args, **kwargs)

        with patch.object(AsyncSession, "scalar", new=fail_first_scalar):
            with self.assertRaisesRegex(OSError, "transient database DNS failure"):
                await deliver_pending_event_announcements(None, None, self.sessions)
            async with self.sessions() as session:
                cursor = await session.scalar(
                    select(AppSetting).where(
                        AppSetting.key == "event-announcement-recovery:cursor"
                    )
                )
                self.assertIsNone(cursor)

            with patch(
                "app.services.event_publication_service.deliver_event_announcement",
                new=AsyncMock(),
            ) as deliver:
                await deliver_pending_event_announcements(None, None, self.sessions)
                self.assertEqual(
                    [call.args[3] for call in deliver.await_args_list], ids
                )

        async with self.sessions() as session:
            cursor = await session.scalar(
                select(AppSetting).where(
                    AppSetting.key == "event-announcement-recovery:cursor"
                )
            )
            self.assertEqual(int(cursor.value), ids[-1])
            statuses = (await session.scalars(
                select(EventExperience.announcement_status)
            )).all()
            self.assertEqual(statuses, ["pending"] * 3)

    async def test_transient_cursor_commit_failure_keeps_pending_events_retryable(self):
        """A connection loss before cursor commit must not skip due work.

        Simulates the commit boundary in disposable SQLite only. No real
        PostgreSQL, Telegram delivery, participants or points are touched.
        """
        ids = await self.events(3)
        original_commit = AsyncSession.commit
        failed_once = False

        async def fail_first_commit(session, *args, **kwargs):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError("simulated transient cursor commit failure")
            return await original_commit(session, *args, **kwargs)

        with patch.object(AsyncSession, "commit", new=fail_first_commit):
            with self.assertRaisesRegex(OSError, "cursor commit failure"):
                await deliver_pending_event_announcements(None, None, self.sessions)

            async with self.sessions() as session:
                cursor = await session.scalar(select(AppSetting).where(
                    AppSetting.key == "event-announcement-recovery:cursor"
                ))
                self.assertIsNone(cursor)

            with patch(
                "app.services.event_publication_service.deliver_event_announcement",
                new=AsyncMock(),
            ) as deliver:
                await deliver_pending_event_announcements(None, None, self.sessions)
                self.assertEqual([call.args[3] for call in deliver.await_args_list], ids)

        async with self.sessions() as session:
            cursor = await session.scalar(select(AppSetting).where(
                AppSetting.key == "event-announcement-recovery:cursor"
            ))
            self.assertEqual(int(cursor.value), ids[-1])
            statuses = (await session.scalars(
                select(EventExperience.announcement_status)
            )).all()
            self.assertEqual(statuses, ["pending"] * 3)

    async def test_corrupt_cursor_recovers_and_nonpublic_or_terminal_items_are_excluded(self):
        ids = await self.events(4)
        async with self.sessions() as session:
            session.add(AppSetting(key="event-announcement-recovery:cursor", value="damaged"))
            (await session.get(Event, ids[1])).status = EventStatus.CANCELLED
            (await session.get(Event, ids[2])).status = EventStatus.DRAFT
            (await session.get(EventExperience, ids[3])).announcement_status = "sent"
            await session.commit()
        with patch("app.services.event_publication_service.deliver_event_announcement", new=AsyncMock()) as deliver:
            await deliver_pending_event_announcements(None, None, self.sessions)
            self.assertEqual([call.args[3] for call in deliver.await_args_list], ids[:1])
