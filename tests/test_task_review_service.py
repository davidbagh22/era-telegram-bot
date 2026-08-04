from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, Task, TaskParticipant, TaskSubmission, User
from app.services import task_review_service
from app.utils.constants import ApplicationStatus, Role, TaskStatus


class TaskReviewServiceTests(unittest.IsolatedAsyncioTestCase):
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

    def _task(self, *, creator_id: int, **overrides) -> Task:
        defaults = dict(
            title="Написать пост",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=20,
            task_type="private",
        )
        defaults.update(overrides)
        return Task(creator_id=creator_id, **defaults)

    def _submission(self, *, task_id: int, user_id: int, **overrides) -> TaskSubmission:
        defaults = dict(text="Готово", status="pending")
        defaults.update(overrides)
        return TaskSubmission(task_id=task_id, user_id=user_id, **defaults)

    async def _points_sum(self, session, user_id: int) -> int:
        rows = await session.scalars(
            select(PointTransaction.points).where(PointTransaction.user_id == user_id)
        )
        return sum(rows.all())

    async def test_approve_private_task_awards_points_and_completes_task(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id, task_type="private")
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            result = await task_review_service.decide_submission(
                session, submission, task, participant, action="approve", comment="", actor=admin
            )

            self.assertEqual(submission.status, "approved")
            self.assertEqual(task.status, TaskStatus.COMPLETED)
            self.assertEqual(result.points_awarded, 20)
            self.assertEqual(await self._points_sum(session, participant.id), 20)
            self.assertIn("одобрен", result.participant_notice)

    async def test_approve_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id, task_type="private")
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            await task_review_service.decide_submission(
                session, submission, task, participant, action="approve", comment="", actor=admin
            )
            result = await task_review_service.decide_submission(
                session, submission, task, participant, action="approve", comment="", actor=admin
            )

            self.assertEqual(result.points_awarded, 0)
            self.assertIsNone(result.participant_notice)
            self.assertEqual(await self._points_sum(session, participant.id), 20)

    async def test_approve_open_task_completes_only_when_all_members_approved(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            member_a = await self._make_user(session, telegram_id=2)
            member_b = await self._make_user(session, telegram_id=3)
            task = self._task(creator_id=admin.id, task_type="challenge")
            session.add(task)
            await session.flush()
            session.add(TaskParticipant(task_id=task.id, user_id=member_a.id, status="accepted"))
            session.add(TaskParticipant(task_id=task.id, user_id=member_b.id, status="accepted"))
            submission_a = self._submission(task_id=task.id, user_id=member_a.id)
            session.add(submission_a)
            await session.flush()

            await task_review_service.decide_submission(
                session, submission_a, task, member_a, action="approve", comment="", actor=admin
            )
            self.assertEqual(task.status, TaskStatus.IN_PROGRESS)

            submission_b = self._submission(task_id=task.id, user_id=member_b.id)
            session.add(submission_b)
            await session.flush()
            await task_review_service.decide_submission(
                session, submission_b, task, member_b, action="approve", comment="", actor=admin
            )
            self.assertEqual(task.status, TaskStatus.COMPLETED)

    async def test_revision_requires_comment(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id)
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            with self.assertRaises(ValueError):
                await task_review_service.decide_submission(
                    session, submission, task, participant, action="revision", comment=" ", actor=admin
                )

    async def test_revision_sets_needs_revision_and_task_in_progress(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id)
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            result = await task_review_service.decide_submission(
                session, submission, task, participant, action="revision", comment="Доделайте", actor=admin
            )

            self.assertEqual(submission.status, "needs_revision")
            self.assertEqual(submission.admin_comment, "Доделайте")
            self.assertEqual(task.status, TaskStatus.IN_PROGRESS)
            self.assertIn("Доделайте", result.participant_notice)

    async def test_reject_sets_rejected_status(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id)
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            result = await task_review_service.decide_submission(
                session, submission, task, participant, action="reject", comment="Не подходит", actor=admin
            )

            self.assertEqual(submission.status, "rejected")
            self.assertEqual(await self._points_sum(session, participant.id), 0)
            self.assertIn("не принят", result.participant_notice)

    async def test_unknown_action_raises(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id)
            session.add(task)
            await session.flush()
            submission = self._submission(task_id=task.id, user_id=participant.id)
            session.add(submission)
            await session.flush()

            with self.assertRaises(ValueError):
                await task_review_service.decide_submission(
                    session, submission, task, participant, action="nope", comment="x", actor=admin
                )

    async def test_list_pending_submissions_filters_by_status(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            participant = await self._make_user(session, telegram_id=2)
            task = self._task(creator_id=admin.id)
            session.add(task)
            await session.flush()
            pending = self._submission(task_id=task.id, user_id=participant.id, status="pending")
            approved = self._submission(task_id=task.id, user_id=participant.id, status="approved")
            session.add_all([pending, approved])
            await session.flush()

            rows = await task_review_service.list_pending_submissions(session)
            self.assertEqual([s.id for s in rows], [pending.id])


if __name__ == "__main__":
    unittest.main()
