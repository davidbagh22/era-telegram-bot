from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import (
    Event,
    EventActivity,
    EventActivitySubmission,
    EventRegistration,
    User,
)
from app.services import event_activity_service as svc
from app.utils.constants import EventStatus, RegistrationStatus


class EventActivityServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    def _event(self, *, created_by: int, **overrides) -> Event:
        defaults = dict(
            title="Событие",
            description="d",
            event_date=date(2026, 1, 1),
            event_time=time(18, 0),
            location="Онлайн",
            format="online",
            status=EventStatus.COMPLETED,
            created_by=created_by,
        )
        defaults.update(overrides)
        return Event(**defaults)

    def _activity(self, *, event_id: int, **overrides) -> EventActivity:
        defaults = dict(
            event_id=event_id, title="Активность", description="d", submission_type="text", points=20, is_active=True
        )
        defaults.update(overrides)
        return EventActivity(**defaults)

    # -- parsing --

    def test_parse_bulk_lines_valid_and_invalid_mixed(self) -> None:
        raw = "Пост в сторис | 30 | link | Отправьте ссылку\nПлохая строка\nОтзыв | 5 | text"
        parsed, rejected = svc.parse_bulk_lines(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(rejected, 1)
        self.assertEqual(parsed[0]["title"], "Пост в сторис")
        self.assertEqual(parsed[0]["points"], 30)
        self.assertEqual(parsed[1]["description"], "Отзыв")  # falls back to title

    def test_parse_bulk_lines_rejects_bad_type_and_points(self) -> None:
        raw = "A | 10 | nonsense_type | d\nB | -5 | text | d\nC | 2000 | text | d"
        parsed, rejected = svc.parse_bulk_lines(raw)
        self.assertEqual(parsed, [])
        self.assertEqual(rejected, 3)

    # -- admin: create / send --

    async def test_create_activities_bulk(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()

            created, rejected = await svc.create_activities_bulk(
                session, event, "A | 10 | text | d\nB | 20 | photo | d2"
            )
            self.assertEqual(created, 2)
            self.assertEqual(rejected, 0)
            activities = await svc.list_activities_admin(session, event.id)
            self.assertEqual(len(activities), 2)

    async def test_activities_sent_marker_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()

            self.assertFalse(svc.activities_already_sent(event))
            svc.mark_activities_sent(event)
            self.assertTrue(svc.activities_already_sent(event))

    async def test_send_recipients_only_active_registrations(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            registered = await self._make_user(session, 2)
            cancelled = await self._make_user(session, 3)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            session.add_all(
                [
                    EventRegistration(event_id=event.id, user_id=registered.id, status=RegistrationStatus.REGISTERED),
                    EventRegistration(event_id=event.id, user_id=cancelled.id, status=RegistrationStatus.CANCELLED),
                ]
            )
            await session.flush()

            recipients = await svc.send_recipients(session, event.id)
            self.assertEqual([u.id for u in recipients], [registered.id])

    # -- admin: review --

    async def test_admin_decide_approve_awards_points_once(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id, points=25)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(
                activity_id=activity.id, user_id=participant.id, text="done", status="pending"
            )
            session.add(submission)
            await session.flush()

            result = await svc.admin_decide(session, submission, approve=True, reviewer_id=admin.id)
            self.assertIsNotNone(result)
            self.assertEqual(submission.status, "approved")
            self.assertEqual(submission.points_awarded, 25)

            # Second decide call is a no-op (submission no longer reviewable).
            again = await svc.admin_decide(session, submission, approve=True, reviewer_id=admin.id)
            self.assertIsNone(again)

    async def test_admin_decide_reject_awards_nothing(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id, points=25)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(activity_id=activity.id, user_id=participant.id, status="pending")
            session.add(submission)
            await session.flush()

            result = await svc.admin_decide(session, submission, approve=False, reviewer_id=admin.id)
            self.assertIsNotNone(result)
            self.assertEqual(submission.status, "rejected")
            self.assertEqual(submission.points_awarded, 0)

    async def test_admin_decide_accepts_leader_approved_status(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id, points=10)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(
                activity_id=activity.id, user_id=participant.id, status="leader_approved"
            )
            session.add(submission)
            await session.flush()

            result = await svc.admin_decide(session, submission, approve=True, reviewer_id=admin.id)
            self.assertIsNotNone(result)
            self.assertEqual(submission.status, "approved")

    async def test_list_reviewable_submissions_includes_pending_and_leader_approved_only(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id)
            session.add(activity)
            await session.flush()
            session.add_all(
                [
                    EventActivitySubmission(activity_id=activity.id, user_id=participant.id, status="pending"),
                    EventActivitySubmission(
                        activity_id=activity.id, user_id=admin.id, status="leader_approved"
                    ),
                ]
            )
            await session.flush()
            # An already-approved one shouldn't show up.
            other_activity = self._activity(event_id=event.id, title="Другая")
            session.add(other_activity)
            await session.flush()
            session.add(
                EventActivitySubmission(activity_id=other_activity.id, user_id=participant.id, status="approved")
            )
            await session.flush()

            rows = await svc.list_reviewable_submissions(session)
            self.assertEqual(len(rows), 2)

    # -- leader --

    async def test_list_leader_pending_scoped_to_responsible_events(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, 1)
            other_leader = await self._make_user(session, 2)
            participant = await self._make_user(session, 3)
            my_event = self._event(created_by=leader.id, responsible_id=leader.id)
            other_event = self._event(created_by=other_leader.id, responsible_id=other_leader.id, title="Другое")
            session.add_all([my_event, other_event])
            await session.flush()
            my_activity = self._activity(event_id=my_event.id)
            other_activity = self._activity(event_id=other_event.id)
            session.add_all([my_activity, other_activity])
            await session.flush()
            session.add_all(
                [
                    EventActivitySubmission(activity_id=my_activity.id, user_id=participant.id, status="pending"),
                    EventActivitySubmission(activity_id=other_activity.id, user_id=participant.id, status="pending"),
                ]
            )
            await session.flush()

            rows = await svc.list_leader_pending(session, leader.id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1].id, my_activity.id)

    async def test_leader_decide_approve_moves_to_leader_approved(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=leader.id, responsible_id=leader.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(activity_id=activity.id, user_id=participant.id, status="pending")
            session.add(submission)
            await session.flush()

            result = await svc.leader_decide(session, submission, approve=True, reviewer_id=leader.id)
            self.assertIsNotNone(result)
            self.assertEqual(submission.status, "leader_approved")

    async def test_leader_decide_reject(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=leader.id, responsible_id=leader.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(activity_id=activity.id, user_id=participant.id, status="pending")
            session.add(submission)
            await session.flush()

            result = await svc.leader_decide(session, submission, approve=False, reviewer_id=leader.id)
            self.assertIsNotNone(result)
            self.assertEqual(submission.status, "rejected")

    async def test_leader_decide_already_decided_is_noop(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=leader.id, responsible_id=leader.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id)
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(
                activity_id=activity.id, user_id=participant.id, status="leader_approved"
            )
            session.add(submission)
            await session.flush()

            result = await svc.leader_decide(session, submission, approve=True, reviewer_id=leader.id)
            self.assertIsNone(result)

    # -- participant --

    async def test_list_activities_for_participant_none_when_not_registered(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            session.add(self._activity(event_id=event.id))
            await session.flush()

            result = await svc.list_activities_for_participant(session, event, participant)
            self.assertIsNone(result)

    async def test_list_activities_for_participant_only_active(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            session.add(EventRegistration(event_id=event.id, user_id=participant.id, status=RegistrationStatus.REGISTERED))
            session.add(self._activity(event_id=event.id, title="Активна", is_active=True))
            session.add(self._activity(event_id=event.id, title="Неактивна", is_active=False))
            await session.flush()

            result = await svc.list_activities_for_participant(session, event, participant)
            self.assertIsNotNone(result)
            self.assertEqual([a.title for a in result], ["Активна"])

    async def test_submit_manual_upserts_single_row(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id, submission_type="manual")
            session.add(activity)
            await session.flush()

            first = await svc.submit_manual(session, activity, participant)
            second = await svc.submit_manual(session, activity, participant)
            self.assertEqual(first.id, second.id)
            self.assertEqual(second.status, "pending")

    async def test_get_submission_returns_none_when_absent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            activity = self._activity(event_id=event.id)
            session.add(activity)
            await session.flush()

            self.assertIsNone(await svc.get_submission(session, activity.id, participant.id))


if __name__ == "__main__":
    unittest.main()
