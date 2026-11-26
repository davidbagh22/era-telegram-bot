from __future__ import annotations

import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import Event, EventActivity, EventActivitySubmission, Task, User
from app.handlers.leader.event_activities_block7 import leader_approve, leader_reject
from app.services import event_activity_service, task_service
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, Role


class LeaderActivityIdorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as session:
            owner = User(
                id=1,
                telegram_id=101,
                first_name="Владелец",
                role=Role.LEADER,
                application_status=ApplicationStatus.APPROVED,
            )
            other_leader = User(
                id=2,
                telegram_id=102,
                first_name="Чужой",
                role=Role.LEADER,
                application_status=ApplicationStatus.APPROVED,
            )
            pending_leader = User(
                id=3,
                telegram_id=103,
                first_name="Кандидат",
                role=Role.LEADER,
                application_status=ApplicationStatus.PENDING,
            )
            participant = User(
                id=4,
                telegram_id=104,
                first_name="Участник",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([owner, other_leader, pending_leader, participant])
            await session.flush()

            event = Event(
                id=10,
                title="Мероприятие",
                description="Описание",
                event_date=date(2026, 11, 10),
                event_time=time(18, 0),
                location="Ереван",
                format="offline",
                points_for_visit=10,
                created_by=owner.id,
                responsible_id=owner.id,
                status=EventStatus.COMPLETED,
            )
            session.add(event)
            await session.flush()

            activity = EventActivity(
                id=20,
                event_id=event.id,
                title="Пост",
                description="Сделать пост",
                submission_type="text",
                points=15,
                is_active=True,
            )
            session.add(activity)
            await session.flush()

            sub = EventActivitySubmission(
                id=30,
                activity_id=activity.id,
                user_id=participant.id,
                status="pending",
                text="Готово",
            )
            session.add(sub)
            await session.flush()

            task = Task(
                id=40,
                title="Открытая задача",
                description="Описание",
                creator_id=owner.id,
                task_type="challenge",
                status="published",
                points=10,
            )
            session.add(task)
            await session.commit()
            self.owner = owner
            self.other_leader = other_leader
            self.pending_leader = pending_leader

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_service_leader_decide_forbids_unrelated_leader(self) -> None:
        async with self.sessions() as session:
            sub = await session.get(EventActivitySubmission, 30)
            with self.assertRaises(PermissionError):
                await event_activity_service.leader_decide(
                    session, sub, approve=True, reviewer_id=self.other_leader.id
                )
            self.assertEqual(sub.status, "pending")

    def test_api_decide_forbids_foreign_and_unapproved_leader(self) -> None:
        def _make_client(viewer: User) -> TestClient:
            app = FastAPI()
            app.include_router(api_router)

            async def _session_override():
                async with self.sessions() as session:
                    yield session

            app.dependency_overrides[get_current_user] = lambda: viewer
            app.dependency_overrides[get_session] = _session_override
            app.dependency_overrides[get_bot] = lambda: None
            app.dependency_overrides[get_settings] = lambda: Settings(
                bot_token="1234567890:test-token"
            )
            return TestClient(app)

        foreign_client = _make_client(self.other_leader)
        res = foreign_client.post("/api/v1/leader/activities/30/decide", json={"action": "approve"})
        self.assertEqual(res.status_code, 403)

        pending_client = _make_client(self.pending_leader)
        res_pending = pending_client.get("/api/v1/leader/activities")
        self.assertEqual(res_pending.status_code, 403)

        owner_client = _make_client(self.owner)
        res_ok = owner_client.post("/api/v1/leader/activities/30/decide", json={"action": "approve"})
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["status"], "leader_approved")

    async def test_bot_leader_approve_and_reject_forbid_foreign_leader_and_bad_callback(self) -> None:
        settings = Settings(bot_token="1234567890:test-token")
        bot = SimpleNamespace(send_message=AsyncMock())
        async with self.sessions() as session:
            for data, handler in (
                ("leader:activity:approve:30", leader_approve),
                ("leader:activity:reject:30", leader_reject),
            ):
                call = SimpleNamespace(
                    data=data,
                    answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                if handler is leader_approve:
                    await handler(call, self.other_leader, settings, session, bot)
                else:
                    await handler(call, self.other_leader, session, bot)
                self.assertEqual(call.message.answer.await_args.args[0], texts.NO_ACCESS)

            sub = await session.get(EventActivitySubmission, 30)
            self.assertEqual(sub.status, "pending")

            bad_call = SimpleNamespace(
                data="leader:activity:approve:99999999999999",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await leader_approve(bad_call, self.owner, settings, session, bot)
            self.assertIn("не найден", bad_call.message.answer.await_args.args[0])

    async def test_task_claim_rejects_unapproved_or_archived_user(self) -> None:
        async with self.sessions() as session:
            task = await session.get(Task, 40)
            for bad_user in (
                self.pending_leader,
                User(
                    id=50,
                    telegram_id=5050,
                    first_name="Архив",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.APPROVED,
                    is_archived=True,
                ),
            ):
                participant, reason = await task_service.claim(session, task, bad_user)
                self.assertIsNone(participant)
                self.assertEqual(reason, "closed")
