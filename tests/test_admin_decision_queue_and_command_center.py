from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, LeadershipAttentionItem, Task, TaskSubmission, User
from app.handlers.admin.commands_ready import admin_hub_text
from app.services.admin_dashboard_service import dashboard_metrics
from app.utils.constants import ApplicationStatus, AttentionItemStatus, Role, TaskStatus

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _make_user(telegram_id: int, **overrides) -> User:
    defaults = dict(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        phone="+10000000000",
        city="Yerevan",
        education_work="Work",
        occupation="Engineer",
        motivation="Help",
        available_time="Evenings",
        desired_path="participant",
        personal_data_consent=True,
        is_channel_subscribed=True,
        application_status=ApplicationStatus.APPROVED,
    )
    defaults.update(overrides)
    return User(**defaults)


class AdminDecisionQueueApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def _client(self, actor: User) -> TestClient:
        app = FastAPI()
        app.include_router(api_router)

        async def _session():
            async with self.factory() as session:
                yield session
                await session.commit()

        app.dependency_overrides[get_current_user] = lambda: actor
        app.dependency_overrides[get_session] = _session
        app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
        return TestClient(app)

    async def _seed(self):
        now = datetime.now(timezone.utc)
        async with self.factory() as session:
            admin = _make_user(100, first_name="Admin", role=Role.ADMIN)
            leader = _make_user(101, first_name="Leader", role=Role.LEADER)
            participant = _make_user(102, first_name="Participant", role=Role.PARTICIPANT)
            blocked_admin = _make_user(103, first_name="Blocked", role=Role.ADMIN, is_blocked=True)
            session.add_all([admin, leader, participant, blocked_admin])
            await session.flush()

            overdue_task = Task(
                title="Просроченная задача",
                description="Нужно решение",
                creator_id=admin.id,
                assignee_id=leader.id,
                deadline=now - timedelta(days=2),
                points=50,
                status=TaskStatus.IN_PROGRESS,
            )
            submission_task = Task(
                title="Задача с ответом",
                description="Есть работа на проверке",
                creator_id=admin.id,
                assignee_id=participant.id,
                deadline=now + timedelta(days=2),
                points=80,
                status=TaskStatus.REVIEW,
            )
            completed_task = Task(
                title="Выполненная задача",
                description="Готово",
                creator_id=admin.id,
                status=TaskStatus.COMPLETED,
            )
            session.add_all([overdue_task, submission_task, completed_task])
            await session.flush()

            session.add(
                TaskSubmission(
                    task_id=submission_task.id,
                    user_id=participant.id,
                    status="pending",
                )
            )
            task_blocker = LeadershipAttentionItem(
                type="blocker",
                severity="high",
                scope_type="task",
                scope_id=overdue_task.id,
                owner_id=leader.id,
                status=AttentionItemStatus.OPEN,
                resolution="Нужна помощь по срокам",
            )
            pulse_item = LeadershipAttentionItem(
                type="pulse_help",
                severity="medium",
                scope_type="pulse",
                scope_id=42,
                owner_id=leader.id,
                status=AttentionItemStatus.OPEN,
                resolution="Эскалация из Пульса",
            )
            session.add_all([task_blocker, pulse_item])
            await session.commit()

            def _actor(u: User):
                return SimpleNamespace(
                    id=u.id,
                    telegram_id=u.telegram_id,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    username=u.username,
                    role=u.role,
                    application_status=u.application_status,
                    is_blocked=u.is_blocked,
                    is_archived=u.is_archived,
                    permission_grants=[],
                )

            return {
                "admin": _actor(admin),
                "leader": _actor(leader),
                "participant": _actor(participant),
                "blocked_admin": _actor(blocked_admin),
                "overdue_task": overdue_task,
                "submission_task": submission_task,
                "completed_task": completed_task,
                "task_blocker": task_blocker,
                "pulse_item": pulse_item,
            }

    async def test_server_side_role_checks_block_non_admins(self) -> None:
        data = await self._seed()
        for non_admin in (data["participant"], data["leader"], data["blocked_admin"]):
            client = self._client(non_admin)
            for method, path in (
                ("get", "/api/v1/admin/decision-queue"),
                ("delete", f"/api/v1/admin/decision-queue/decisions/{data['pulse_item'].id}"),
                ("post", f"/api/v1/admin/decision-queue/decisions/{data['pulse_item'].id}/restore"),
                ("delete", f"/api/v1/admin/decision-queue/tasks/{data['overdue_task'].id}"),
                ("post", f"/api/v1/admin/decision-queue/tasks/{data['overdue_task'].id}/restore"),
                ("delete", f"/api/v1/workcenter/decisions/{data['pulse_item'].id}"),
            ):
                resp = await asyncio.to_thread(getattr(client, method), path)
                self.assertEqual(resp.status_code, 403, f"{non_admin.role} {method} {path}")

    async def test_delete_and_restore_decision_item_writes_audit_and_updates_queues(self) -> None:
        data = await self._seed()
        client = self._client(data["admin"])
        item_id = data["pulse_item"].id

        before = await asyncio.to_thread(client.get, "/api/v1/admin/decision-queue")
        self.assertEqual(before.status_code, 200)
        self.assertIn(item_id, [d["id"] for d in before.json()["decisions"]])

        deleted = await asyncio.to_thread(
            client.request,
            "DELETE",
            f"/api/v1/admin/decision-queue/decisions/{item_id}",
            json={"reason": "Неактуально"},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["status"], AttentionItemStatus.DISMISSED)
        self.assertTrue(deleted.json()["deleted"])
        self.assertTrue(deleted.json()["reversible"])

        duplicate = await asyncio.to_thread(
            client.delete, f"/api/v1/admin/decision-queue/decisions/{item_id}"
        )
        self.assertEqual(duplicate.status_code, 409)

        after_queue = await asyncio.to_thread(client.get, "/api/v1/admin/decision-queue")
        self.assertNotIn(item_id, [d["id"] for d in after_queue.json()["decisions"]])
        after_wc = await asyncio.to_thread(client.get, "/api/v1/workcenter/decisions")
        self.assertNotIn(item_id, [d["id"] for d in after_wc.json()])

        async with self.factory() as session:
            logs = (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.entity_type == "leadership_attention_item",
                        AuditLog.entity_id == item_id,
                    )
                )
            ).all()
            self.assertEqual([log.action for log in logs], ["leadership_attention_item.deleted"])
            self.assertEqual(logs[0].actor_id, data["admin"].id)
            self.assertEqual(logs[0].old_value["status"], "open")
            self.assertEqual(logs[0].new_value["reason"], "Неактуально")

        restored = await asyncio.to_thread(
            client.post, f"/api/v1/admin/decision-queue/decisions/{item_id}/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["status"], AttentionItemStatus.OPEN)

        relisted = await asyncio.to_thread(client.get, "/api/v1/admin/decision-queue")
        self.assertIn(item_id, [d["id"] for d in relisted.json()["decisions"]])

    async def test_restore_returns_decision_to_pre_deletion_status_and_text(self) -> None:
        data = await self._seed()
        client = self._client(data["admin"])
        deferred_resolved_at = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
        original_text = "Согласовать бюджет мероприятия"
        async with self.factory() as session:
            deferred = LeadershipAttentionItem(
                type="pulse_help",
                severity="medium",
                scope_type="pulse",
                scope_id=77,
                owner_id=data["leader"].id,
                status="deferred",
                resolution=original_text,
                resolved_at=deferred_resolved_at,
            )
            session.add(deferred)
            await session.commit()
            item_id = deferred.id

        long_reason = "х" * 500
        deleted = await asyncio.to_thread(
            client.request,
            "DELETE",
            f"/api/v1/admin/decision-queue/decisions/{item_id}",
            json={"reason": long_reason},
        )
        self.assertEqual(deleted.status_code, 200)

        async with self.factory() as session:
            item = await session.get(LeadershipAttentionItem, item_id)
            self.assertEqual(item.resolution, original_text)

        restored = await asyncio.to_thread(
            client.post, f"/api/v1/admin/decision-queue/decisions/{item_id}/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["status"], "deferred")

        async with self.factory() as session:
            item = await session.get(LeadershipAttentionItem, item_id)
            self.assertEqual(str(item.status), "deferred")
            self.assertEqual(item.resolution, original_text)
            self.assertEqual(item.resolved_at.replace(tzinfo=timezone.utc), deferred_resolved_at)

    async def test_delete_task_soft_cancels_closes_linked_blocker_and_guards_pending_submission(self) -> None:
        data = await self._seed()
        client = self._client(data["admin"])

        # Task with pending submission must NOT be silently deleted.
        blocked = await asyncio.to_thread(
            client.delete, f"/api/v1/admin/decision-queue/tasks/{data['submission_task'].id}"
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "pending_submission_exists")

        # Completed task cannot be deleted from decision queue.
        done = await asyncio.to_thread(
            client.delete, f"/api/v1/admin/decision-queue/tasks/{data['completed_task'].id}"
        )
        self.assertEqual(done.status_code, 409)
        self.assertEqual(done.json()["detail"], "task_already_completed")

        # Overdue + blocked task without pending submission can be deleted cleanly.
        task_id = data["overdue_task"].id
        deleted = await asyncio.to_thread(
            client.request,
            "DELETE",
            f"/api/v1/admin/decision-queue/tasks/{task_id}",
            json={"reason": "Дубль"},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["status"], TaskStatus.CANCELLED)

        async with self.factory() as session:
            task = await session.get(Task, task_id)
            blocker = await session.get(LeadershipAttentionItem, data["task_blocker"].id)
            self.assertEqual(str(task.status), TaskStatus.CANCELLED)
            self.assertEqual(str(blocker.status), AttentionItemStatus.DISMISSED)
            metrics = await dashboard_metrics(session)
            # Only submission_task remains in tasks_attention.
            self.assertEqual(metrics.values["tasks_attention"], 1)
            task_audit = await session.scalar(
                select(AuditLog).where(
                    AuditLog.entity_type == "task",
                    AuditLog.entity_id == task_id,
                    AuditLog.action == "admin.decision_task_deleted",
                )
            )
            self.assertIsNotNone(task_audit)
            self.assertEqual(task_audit.old_value["status"], TaskStatus.IN_PROGRESS)
            self.assertIn(data["task_blocker"].id, task_audit.old_value["closed_attention_ids"])

        # Restore brings back both the task status and its linked blocker.
        restored = await asyncio.to_thread(
            client.post, f"/api/v1/admin/decision-queue/tasks/{task_id}/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["status"], TaskStatus.IN_PROGRESS)

        async with self.factory() as session:
            blocker = await session.get(LeadershipAttentionItem, data["task_blocker"].id)
            self.assertEqual(str(blocker.status), AttentionItemStatus.OPEN)
            metrics = await dashboard_metrics(session)
            self.assertEqual(metrics.values["tasks_attention"], 2)

    async def test_workcenter_delete_decision_endpoint_soft_deletes_and_audits(self) -> None:
        data = await self._seed()
        client = self._client(data["admin"])
        item_id = data["pulse_item"].id

        resp = await asyncio.to_thread(
            client.request,
            "DELETE",
            f"/api/v1/workcenter/decisions/{item_id}",
            json={"reason": "Решено оффлайн"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

        listed = await asyncio.to_thread(client.get, "/api/v1/workcenter/decisions")
        self.assertNotIn(item_id, [row["id"] for row in listed.json()])

    async def test_bot_admin_hub_text_surfaces_key_stats(self) -> None:
        await self._seed()
        settings = Settings(bot_token="1234567890:test-token")
        async with self.factory() as session:
            text, pending = await admin_hub_text(session, settings)
        self.assertEqual(pending, 0)
        self.assertIn("Участников:", text)
        self.assertIn("активных (14д):", text)
        self.assertIn("Требуют решения:", text)


class AdminCommandCenterContractTests(unittest.TestCase):
    def test_command_center_top_quick_actions_analytics_and_decision_delete_ui(self) -> None:
        overview = (FRONTEND / "screens" / "admin" / "AdminOverviewScreen.tsx").read_text(encoding="utf-8")
        admin = (FRONTEND / "screens" / "AdminScreen.tsx").read_text(encoding="utf-8")
        queue = (FRONTEND / "screens" / "admin" / "AdminDecisionQueueScreen.tsx").read_text(encoding="utf-8")
        workcenter = (FRONTEND / "screens" / "admin" / "AdminWorkcenterScreen.tsx").read_text(encoding="utf-8")

        more_idx = overview.index("function OverviewMoreTools")
        top = overview[:more_idx]
        self.assertIn('data-testid="admin-quick-actions"', top)
        self.assertIn("onOpenBroadcast", top)
        self.assertIn("onOpenTaskCreate", top)
        self.assertIn("onOpenEventCreate", top)
        self.assertIn('data-testid="admin-analytics-summary"', top)
        self.assertIn('onOpenMetric("current_roster"', top)
        self.assertIn("setShowAnalytics(true)", top)
        self.assertIn("AdminDecisionQueueScreen", overview)

        self.assertIn('tools: { section: "broadcast" }', admin)
        self.assertIn('tasks: { section: "create", openCreate: true }', admin)
        self.assertIn('events: { section: "create" }', admin)

        self.assertIn("Удалить из очереди решений?", queue)
        self.assertIn("Подтвердить удаление", queue)
        self.assertIn("Вернуть", queue)
        self.assertIn("deleteWorkDecision", workcenter)
        self.assertIn("Подтвердить удаление", workcenter)


if __name__ == "__main__":
    unittest.main()
