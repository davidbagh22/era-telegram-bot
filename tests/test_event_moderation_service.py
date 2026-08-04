from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, User
from app.services import event_moderation_service
from app.utils.constants import ApplicationStatus, EventStatus, Role


class EventModerationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
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
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _event(self, *, created_by: int, **overrides) -> Event:
        defaults = dict(
            title="Летний слёт",
            description="d",
            event_date=date(2026, 9, 1),
            event_time=time(18, 0),
            location="Ереван",
            format="offline",
            status=EventStatus.PENDING_APPROVAL,
        )
        defaults.update(overrides)
        return Event(created_by=created_by, **defaults)

    async def test_approve_sets_status_and_notifies_owner(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            leader = await self._make_user(session, telegram_id=2)
            event = self._event(created_by=leader.id)
            session.add(event)
            await session.flush()

            result = await event_moderation_service.decide_event(
                session, event, action="approve", comment="", actor=admin
            )

            self.assertEqual(event.status, EventStatus.APPROVED)
            self.assertEqual(event.approved_by, admin.id)
            self.assertEqual(result.owner.id, leader.id)
            self.assertIn("одобрено", result.notice)

    async def test_revise_requires_comment(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            leader = await self._make_user(session, telegram_id=2)
            event = self._event(created_by=leader.id)
            session.add(event)
            await session.flush()

            with self.assertRaises(ValueError):
                await event_moderation_service.decide_event(
                    session, event, action="revise", comment="   ", actor=admin
                )

    async def test_revise_sets_status_draft_with_comment(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            leader = await self._make_user(session, telegram_id=2)
            event = self._event(created_by=leader.id)
            session.add(event)
            await session.flush()

            result = await event_moderation_service.decide_event(
                session, event, action="revise", comment="Уточните формат", actor=admin
            )

            self.assertEqual(event.status, EventStatus.DRAFT)
            self.assertIn("доработку", result.notice)
            self.assertIn("Уточните формат", result.notice)

    async def test_reject_sets_status_cancelled_with_comment(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            leader = await self._make_user(session, telegram_id=2)
            event = self._event(created_by=leader.id)
            session.add(event)
            await session.flush()

            result = await event_moderation_service.decide_event(
                session, event, action="reject", comment="Не подходит", actor=admin
            )

            self.assertEqual(event.status, EventStatus.CANCELLED)
            self.assertIn("отклонено", result.notice)

    async def test_unknown_action_raises(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            leader = await self._make_user(session, telegram_id=2)
            event = self._event(created_by=leader.id)
            session.add(event)
            await session.flush()

            with self.assertRaises(ValueError):
                await event_moderation_service.decide_event(
                    session, event, action="not_a_real_action", comment="x", actor=admin
                )

    async def test_list_events_for_review_only_pending_approval(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, telegram_id=2)
            pending = self._event(created_by=leader.id, status=EventStatus.PENDING_APPROVAL)
            approved = self._event(created_by=leader.id, status=EventStatus.APPROVED)
            session.add_all([pending, approved])
            await session.flush()

            rows = await event_moderation_service.list_events_for_review(session)
            self.assertEqual([e.id for e in rows], [pending.id])


if __name__ == "__main__":
    unittest.main()
