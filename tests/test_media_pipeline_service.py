from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.media_models import MediaContentItem, MediaContentStatus, MediaContentTask
from app.database.models import Task, User
from app.services.media_pipeline_service import (
    ALLOWED_TRANSITIONS,
    normalize_status,
    product_status,
    reconcile_content_state,
    reconcile_media_pipeline_job,
    transition_content_status,
)
from app.utils.constants import ApplicationStatus, TaskStatus


class MediaPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_master_status_vocabulary_is_complete(self) -> None:
        self.assertEqual(
            [status.name for status in MediaContentStatus],
            [
                "IDEA",
                "PLANNED",
                "ASSIGNED",
                "IN_PROGRESS",
                "REVIEW",
                "READY",
                "SCHEDULED",
                "PUBLISHED",
                "SKIPPED",
                "FAILED",
            ],
        )
        self.assertEqual(normalize_status("draft"), "planned")
        self.assertEqual(product_status("in_progress"), "IN_PROGRESS")

    def test_terminal_states_cannot_transition_back_to_work(self) -> None:
        self.assertEqual(ALLOWED_TRANSITIONS["published"], set())
        self.assertEqual(ALLOWED_TRANSITIONS["skipped"], set())

    async def _seed_user(self, session) -> User:
        user = User(
            telegram_id=777001,
            first_name="Media",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_legacy_draft_is_normalized_on_model_write(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            item = MediaContentItem(
                source_kind="manual",
                source_key="manual:test:draft",
                status="draft",
                created_by=user.id,
            )
            session.add(item)
            await session.flush()
            self.assertEqual(item.status, MediaContentStatus.PLANNED.value)

    async def test_existing_task_engine_drives_assigned_progress_review_ready(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            item = MediaContentItem(
                source_kind="manual",
                source_key="manual:test:task",
                status="planned",
                created_by=user.id,
            )
            session.add(item)
            await session.flush()
            task = Task(
                title="Media work",
                description="test",
                creator_id=user.id,
                deadline=datetime.now(timezone.utc) + timedelta(days=2),
                points=40,
                status=TaskStatus.PUBLISHED,
            )
            session.add(task)
            await session.flush()
            session.add(MediaContentTask(content_id=item.id, task_id=task.id, task_kind="text"))
            await session.flush()

            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "assigned")

            task.status = TaskStatus.IN_PROGRESS
            await session.flush()
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "in_progress")

            task.status = TaskStatus.REVIEW
            await session.flush()
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "review")

            task.status = TaskStatus.COMPLETED
            await session.flush()
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "ready")

    async def test_completed_work_with_schedule_becomes_scheduled(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            item = MediaContentItem(
                source_kind="manual",
                source_key="manual:test:scheduled",
                status="planned",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=user.id,
            )
            session.add(item)
            await session.flush()
            task = Task(
                title="Media work",
                description="test",
                creator_id=user.id,
                deadline=datetime.now(timezone.utc) + timedelta(hours=8),
                points=40,
                status=TaskStatus.COMPLETED,
            )
            session.add(task)
            await session.flush()
            session.add(MediaContentTask(content_id=item.id, task_id=task.id, task_kind="text"))
            await session.flush()
            await reconcile_content_state(session, item)
            self.assertEqual(item.status, "scheduled")

    async def test_reconcile_job_reaches_item_after_500_unchanged_rows(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            session.add_all(
                [
                    MediaContentItem(
                        source_kind="media_workspace",
                        source_key=f"workspace:backlog:{index}",
                        status="planned",
                        created_by=user.id,
                    )
                    for index in range(500)
                ]
            )
            tail = MediaContentItem(
                source_kind="manual",
                source_key="manual:backlog:tail",
                status="planned",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=user.id,
            )
            session.add(tail)
            await session.commit()
            tail_id = tail.id

        await reconcile_media_pipeline_job(self.factory)

        async with self.factory() as session:
            item = await session.get(MediaContentItem, tail_id)
            self.assertEqual(item.status, "scheduled")

    async def test_reconcile_job_reaches_third_batch_and_preserves_terminal_rows(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            session.add_all(
                [
                    MediaContentItem(
                        source_kind="media_workspace",
                        source_key=f"workspace:three-batches:{index}",
                        status="planned",
                        created_by=user.id,
                    )
                    for index in range(1000)
                ]
            )
            published = MediaContentItem(
                source_kind="manual",
                source_key="manual:terminal",
                status="published",
                created_by=user.id,
            )
            tail = MediaContentItem(
                source_kind="manual",
                source_key="manual:third-batch",
                status="planned",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=user.id,
            )
            session.add_all([published, tail])
            await session.commit()
            tail_id, published_id = tail.id, published.id

        await reconcile_media_pipeline_job(self.factory)

        async with self.factory() as session:
            tail = await session.get(MediaContentItem, tail_id)
            published = await session.get(MediaContentItem, published_id)
            self.assertEqual(tail.status, "scheduled")
            self.assertEqual(published.status, "published")

    async def test_invalid_transition_is_rejected(self) -> None:
        async with self.factory() as session:
            user = await self._seed_user(session)
            item = MediaContentItem(
                source_kind="manual",
                source_key="manual:test:published",
                status="published",
                created_by=user.id,
            )
            session.add(item)
            await session.flush()
            with self.assertRaises(ValueError):
                await transition_content_status(session, item, MediaContentStatus.PLANNED)


if __name__ == "__main__":
    unittest.main()
