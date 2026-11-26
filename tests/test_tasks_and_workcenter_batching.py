from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.community_models import TaskSquad
from app.database.models import AuditLog, Task, TaskDelivery, TaskParticipant, TaskSubmission, User
from app.utils.constants import ApplicationStatus, Role


class TasksAndWorkcenterBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as session:
            admin = User(
                id=1,
                telegram_id=9001,
                first_name="Админ",
                last_name="ЭРА",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            member = User(
                id=2,
                telegram_id=9002,
                first_name="Участник",
                last_name="Тест",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([admin, member])
            await session.flush()

            tasks = []
            for i in range(6):
                reward = (
                    {"community_mission": {"code": f"M{i}", "claim_mode": "squad", "min_people": 1, "max_people": 4, "workspace_chat_key": "general", "deliverable": "отчёт"}}
                    if i % 2 == 0
                    else {"public_task": True}
                )
                task = Task(
                    id=100 + i,
                    title=f"Задача {i}",
                    description="Описание",
                    creator_id=admin.id,
                    assignee_id=member.id if i == 1 else None,
                    task_type="challenge",
                    status="published",
                    points=10 + i,
                    deadline=datetime.now(timezone.utc) + timedelta(days=3),
                    reward_json=reward,
                )
                tasks.append(task)
            session.add_all(tasks)
            await session.flush()

            session.add(TaskSquad(task_id=100, responsible_user_id=admin.id, workspace_chat_key="general", status="active"))
            session.add_all([
                TaskParticipant(task_id=100, user_id=member.id, status="joined"),
                TaskParticipant(task_id=100, user_id=admin.id, status="accepted"),
                TaskParticipant(task_id=103, user_id=member.id, status="joined"),
            ])
            session.add_all([
                TaskDelivery(
                    task_id=100 + i,
                    chat_key="leaders",
                    chat_id=-100900,
                    status="sent",
                    telegram_message_id=500 + i,
                )
                for i in range(6)
            ])
            session.add(TaskSubmission(task_id=100, user_id=member.id, text="Отчёт", status="pending"))
            session.add(AuditLog(actor_id=admin.id, action="task.created", entity_type="task", entity_id=100))
            await session.commit()
            self.admin = admin
            self.member = member

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def _client(self, viewer: User) -> TestClient:
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            bot_username="era_bot",
            leaders_chat_id=-100900,
            admin_ids=[9001],
        )
        return TestClient(app)

    def test_read_tasks_batches_membership_and_squad_queries(self) -> None:
        client = self._client(self.member)
        queries: list[str] = []

        @sa_event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def _count(_conn, _cursor, statement, *_args):
            queries.append(statement)

        try:
            with patch("app.api.v1.tasks.task_service.can_submit", side_effect=AssertionError("per-task query")):
                avail = client.get("/api/v1/tasks", params={"scope": "available"})
                mine = client.get("/api/v1/tasks", params={"scope": "mine"})
        finally:
            sa_event.remove(self.engine.sync_engine, "before_cursor_execute", _count)

        self.assertEqual(avail.status_code, 200)
        self.assertEqual(mine.status_code, 200)
        avail_by_id = {item["id"]: item for item in avail.json()}
        mine_by_id = {item["id"]: item for item in mine.json()}
        self.assertEqual(set(avail_by_id), {102, 104, 105})
        self.assertEqual(set(mine_by_id), {100, 101, 103})
        self.assertEqual(mine_by_id[100]["squad_size"], 2)
        self.assertEqual(mine_by_id[100]["squad_status"], "active")
        self.assertTrue(mine_by_id[100]["can_submit"])
        self.assertTrue(mine_by_id[101]["can_submit"])
        self.assertTrue(mine_by_id[103]["can_submit"])
        self.assertLessEqual(len(queries), 24)

    def test_workcenter_tasks_batches_deliveries_submissions_and_audit(self) -> None:
        client = self._client(self.admin)
        queries: list[str] = []

        @sa_event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def _count(_conn, _cursor, statement, *_args):
            queries.append(statement)

        try:
            response = client.get("/api/v1/workcenter/tasks")
        finally:
            sa_event.remove(self.engine.sync_engine, "before_cursor_execute", _count)

        self.assertEqual(response.status_code, 200)
        by_id = {item["id"]: item for item in response.json()}
        self.assertEqual(len(by_id), 6)
        self.assertEqual(by_id[100]["delivery_status"], "sent")
        self.assertEqual(by_id[100]["submissions"][0]["text"], "Отчёт")
        self.assertEqual(by_id[100]["history"][0]["action"], "task.created")
        self.assertEqual(by_id[101]["assignee_name"], "Участник Тест")
        self.assertLessEqual(len(queries), 15)
