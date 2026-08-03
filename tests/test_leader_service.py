from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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


if __name__ == "__main__":
    unittest.main()
