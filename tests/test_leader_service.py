from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import (
    Department,
    Direction,
    Event,
    Project,
    Task,
    TaskParticipant,
    User,
    UserDepartment,
    UserDirection,
)
from app.services import leader_service
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, Role


class LeaderServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def _scope_leader(self, session) -> tuple[User, Department, Direction]:
        department = Department(name="Внутренние связи")
        session.add(department)
        await session.flush()
        direction = Direction(department_id=department.id, name="Культура")
        session.add(direction)
        await session.flush()
        leader = await self._make_user(session, telegram_id=1, role=Role.LEADER)
        session.add(UserDepartment(user_id=leader.id, department_id=department.id))
        session.add(UserDirection(user_id=leader.id, direction_id=direction.id))
        await session.flush()
        await session.refresh(leader)
        return leader, department, direction

    async def test_list_scope_participants_restricted_to_leader_scope(self) -> None:
        async with self.session_factory() as session:
            leader, department, direction = await self._scope_leader(session)
            in_scope = await self._make_user(session, telegram_id=2)
            session.add(UserDepartment(user_id=in_scope.id, department_id=department.id))
            out_of_scope = await self._make_user(session, telegram_id=3)
            await session.flush()

            participants = await leader_service.list_scope_participants(session, leader)
            ids = {p.id for p in participants}
            self.assertIn(in_scope.id, ids)
            self.assertNotIn(out_of_scope.id, ids)

    async def test_admin_sees_all_participants(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1, role=Role.ADMIN)
            other = await self._make_user(session, telegram_id=2)
            await session.flush()

            participants = await leader_service.list_scope_participants(session, admin)
            ids = {p.id for p in participants}
            self.assertIn(admin.id, ids)
            self.assertIn(other.id, ids)

    async def test_list_scope_events_includes_own_created_events(self) -> None:
        async with self.session_factory() as session:
            leader, department, direction = await self._scope_leader(session)
            other_leader = await self._make_user(session, telegram_id=9, role=Role.LEADER)
            own_event = Event(
                title="Own event",
                description="d",
                event_date=datetime(2026, 1, 1).date(),
                event_time=datetime(2026, 1, 1, 18, 0).time(),
                location="Loc",
                format="offline",
                created_by=leader.id,
                status=EventStatus.PENDING_APPROVAL,
            )
            unrelated_event = Event(
                title="Unrelated",
                description="d",
                event_date=datetime(2026, 1, 1).date(),
                event_time=datetime(2026, 1, 1, 18, 0).time(),
                location="Loc",
                format="offline",
                created_by=other_leader.id,
                status=EventStatus.PENDING_APPROVAL,
            )
            session.add_all([own_event, unrelated_event])
            await session.flush()

            events = await leader_service.list_scope_events(session, leader)
            ids = {e.id for e in events}
            self.assertIn(own_event.id, ids)
            self.assertNotIn(unrelated_event.id, ids)

    async def test_list_scope_projects_restricted_to_leader_scope(self) -> None:
        async with self.session_factory() as session:
            leader, department, direction = await self._scope_leader(session)
            author = await self._make_user(session, telegram_id=5)
            in_scope = Project(
                author_id=author.id,
                department_id=department.id,
                title="In scope",
                short_description="d",
                status=ProjectStatus.DRAFT,
            )
            out_of_scope = Project(
                author_id=author.id,
                title="Out of scope",
                short_description="d",
                status=ProjectStatus.DRAFT,
            )
            session.add_all([in_scope, out_of_scope])
            await session.flush()

            projects = await leader_service.list_scope_projects(session, leader)
            ids = {p.id for p in projects}
            self.assertIn(in_scope.id, ids)
            self.assertNotIn(out_of_scope.id, ids)

    async def test_create_assigned_task_rejects_invalid_points(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            assignee = await self._make_user(session, telegram_id=2)
            with self.assertRaises(ValueError):
                await leader_service.create_assigned_task(
                    session,
                    creator=leader,
                    assignee=assignee,
                    title="t",
                    description="d",
                    deadline=datetime.now(timezone.utc),
                    points=1001,
                    bot=None,
                )

    async def test_create_assigned_task_creates_task(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            assignee = await self._make_user(session, telegram_id=2)
            task = await leader_service.create_assigned_task(
                session,
                creator=leader,
                assignee=assignee,
                title="Помочь на мероприятии",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=20,
                bot=None,
            )
            self.assertEqual(task.creator_id, leader.id)
            self.assertEqual(task.assignee_id, assignee.id)
            self.assertEqual(task.points, 20)

    async def test_create_open_task_rejects_invalid_max_participants(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            with self.assertRaises(ValueError):
                await leader_service.create_open_task(
                    session,
                    creator=leader,
                    title="t",
                    description="d",
                    deadline=datetime.now(timezone.utc),
                    points=10,
                    max_participants=0,
                )

    async def test_create_open_task_sets_challenge_type(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Открытая задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=15,
                max_participants=3,
            )
            self.assertEqual(task.task_type, "challenge")
            self.assertEqual(task.status, "published")
            self.assertIsNone(task.assignee_id)

    async def test_list_open_tasks_with_applications_groups_by_task(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            applicant = await self._make_user(session, telegram_id=7)
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Открытая задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=15,
                max_participants=3,
            )
            session.add(TaskParticipant(task_id=task.id, user_id=applicant.id, status="pending"))
            await session.flush()

            results = await leader_service.list_open_tasks_with_applications(session, leader)
            self.assertEqual(len(results), 1)
            self.assertEqual(len(results[0].applications), 1)
            self.assertEqual(results[0].applications[0].applicant.id, applicant.id)

    async def test_decide_task_application_accept_respects_capacity(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            applicant_a = await self._make_user(session, telegram_id=7)
            applicant_b = await self._make_user(session, telegram_id=8)
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Открытая задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=15,
                max_participants=1,
            )
            session.add(TaskParticipant(task_id=task.id, user_id=applicant_a.id, status="pending"))
            session.add(TaskParticipant(task_id=task.id, user_id=applicant_b.id, status="pending"))
            await session.flush()

            await leader_service.decide_task_application(
                session, task=task, target=applicant_a, action="accept", actor=leader, bot=None
            )
            with self.assertRaises(ValueError):
                await leader_service.decide_task_application(
                    session, task=task, target=applicant_b, action="accept", actor=leader, bot=None
                )

    async def test_decide_task_application_rejects_non_owner(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            other_leader = await self._make_user(session, telegram_id=9, role=Role.LEADER)
            applicant = await self._make_user(session, telegram_id=7)
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Открытая задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=15,
                max_participants=3,
            )
            session.add(TaskParticipant(task_id=task.id, user_id=applicant.id, status="pending"))
            await session.flush()

            with self.assertRaises(PermissionError):
                await leader_service.decide_task_application(
                    session, task=task, target=applicant, action="accept", actor=other_leader, bot=None
                )

    async def test_decide_task_application_reject_sets_status(self) -> None:
        async with self.session_factory() as session:
            leader, _, _ = await self._scope_leader(session)
            applicant = await self._make_user(session, telegram_id=7)
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Открытая задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=15,
                max_participants=3,
            )
            session.add(TaskParticipant(task_id=task.id, user_id=applicant.id, status="pending"))
            await session.flush()

            participant = await leader_service.decide_task_application(
                session, task=task, target=applicant, action="reject", actor=leader, bot=None
            )
            self.assertEqual(participant.status, "rejected")


class FakeBot:
    id = 999

    def __init__(self, fail_chat_ids: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_chat_ids = fail_chat_ids or set()
        self._next_message_id = 1

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        from aiogram.exceptions import TelegramNetworkError

        if chat_id in self.fail_chat_ids:
            raise TelegramNetworkError(method=None, message="simulated outage")
        self.sent.append((chat_id, text))
        message = SimpleNamespace(message_id=self._next_message_id)
        self._next_message_id += 1
        return message


class TaskChatDeliveryTests(unittest.IsolatedAsyncioTestCase):
    """2026-08 master spec section 31-33: task creation supports choosing
    delivery destinations, never rolls back on a Telegram failure, and the
    result is readable back as entity<->chat<->message_id<->status<->error."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _leader(self, session) -> User:
        user = User(
            telegram_id=1,
            first_name="Dev",
            role=Role.LEADER,
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_create_open_task_dispatches_to_requested_chats(self) -> None:
        async with self.session_factory() as session:
            leader = await self._leader(session)
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100111, leaders_chat_id=-100222)
            bot = FakeBot()
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=10,
                max_participants=3,
                destinations=["general", "leaders"],
                bot=bot,
                settings=settings,
            )
            await session.commit()
            self.assertEqual({chat_id for chat_id, _ in bot.sent}, {-100111, -100222})
            deliveries = await leader_service.list_task_deliveries(session, task.id)
            self.assertEqual(len(deliveries), 2)
            self.assertTrue(all(d.status == "sent" for d in deliveries))
            self.assertTrue(all(d.sent_at is not None for d in deliveries))
            self.assertTrue(all(d.telegram_message_id is not None for d in deliveries))

    async def test_task_creation_survives_a_telegram_failure(self) -> None:
        # The core guarantee: a Telegram outage on one (or every) requested
        # chat must never roll back the task itself.
        async with self.session_factory() as session:
            leader = await self._leader(session)
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100111)
            bot = FakeBot(fail_chat_ids={-100111})
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=10,
                max_participants=3,
                destinations=["general"],
                bot=bot,
                settings=settings,
            )
            await session.commit()
            # The task itself exists and is fully published, not rolled back.
            persisted = await session.get(Task, task.id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.status, "published")
            deliveries = await leader_service.list_task_deliveries(session, task.id)
            self.assertEqual(len(deliveries), 1)
            self.assertEqual(deliveries[0].status, "failed")
            self.assertIsNotNone(deliveries[0].error)

    async def test_unbound_destination_recorded_as_failed_not_skipped(self) -> None:
        async with self.session_factory() as session:
            leader = await self._leader(session)
            settings = Settings(bot_token="1234567890:test-token")  # no chats bound
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=10,
                max_participants=3,
                destinations=["internal"],
                bot=FakeBot(),
                settings=settings,
            )
            await session.commit()
            deliveries = await leader_service.list_task_deliveries(session, task.id)
            self.assertEqual(len(deliveries), 1)
            self.assertEqual(deliveries[0].status, "failed")
            self.assertEqual(deliveries[0].error, "chat_not_bound")

    async def test_create_open_task_rejects_unknown_destination(self) -> None:
        async with self.session_factory() as session:
            leader = await self._leader(session)
            with self.assertRaises(ValueError):
                await leader_service.create_open_task(
                    session,
                    creator=leader,
                    title="Задача",
                    description="d",
                    deadline=datetime.now(timezone.utc),
                    points=10,
                    max_participants=3,
                    destinations=["not_a_real_chat"],
                    settings=Settings(bot_token="1234567890:test-token"),
                )

    async def test_retry_delivery_only_resends_that_one_destination(self) -> None:
        async with self.session_factory() as session:
            leader = await self._leader(session)
            settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100111, leaders_chat_id=-100222)
            bot = FakeBot(fail_chat_ids={-100111})
            task = await leader_service.create_open_task(
                session,
                creator=leader,
                title="Задача",
                description="d",
                deadline=datetime.now(timezone.utc),
                points=10,
                max_participants=3,
                destinations=["general", "leaders"],
                bot=bot,
                settings=settings,
            )
            await session.commit()
            deliveries = await leader_service.list_task_deliveries(session, task.id)
            failed = next(d for d in deliveries if d.chat_key == "general")
            self.assertEqual(failed.status, "failed")

            # Retry with a bot that no longer fails -- only the failed
            # destination should be resent.
            recovered_bot = FakeBot()
            await leader_service.retry_task_delivery(session, recovered_bot, failed, task)
            await session.commit()
            self.assertEqual(len(recovered_bot.sent), 1)
            self.assertEqual(recovered_bot.sent[0][0], -100111)

            updated = await leader_service.list_task_deliveries(session, task.id)
            updated_general = next(d for d in updated if d.chat_key == "general")
            self.assertEqual(updated_general.status, "sent")
            # The leaders delivery, never retried, keeps its original status.
            updated_leaders = next(d for d in updated if d.chat_key == "leaders")
            self.assertEqual(updated_leaders.status, "sent")


if __name__ == "__main__":
    unittest.main()
