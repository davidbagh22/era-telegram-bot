from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.media import read_media_hub
from app.api.v1.tasks import read_tasks
from app.config import Settings
from app.database.base import Base
from app.database.media_models import MediaContentItem, MediaContentTask
from app.database.models import Department, Direction, Event, Project, Task, TaskParticipant, User, UserDirection
from app.handlers.participant.cabinet import my_tasks
from app.handlers.participant.task_block2 import task_view, tasks_list, tasks_list_page
from app.services import home_service, media_service, task_presentation_service, task_service
from app.utils.constants import ApplicationStatus, TaskStatus


def _button_callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class BotTaskListTidyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, role: str = "participant") -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=f"User{telegram_id}",
            role=role,
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        return user
    async def test_expired_published_tasks_hidden_from_open_lists_and_cannot_be_claimed(self):
        settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot")
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            admin = await self._make_user(session, 101, role="admin")
            expired = Task(
                title="Старая просроченная задача",
                description="Срок прошёл давно",
                deadline=now - timedelta(days=30),
                points=50,
                status=TaskStatus.PUBLISHED,
                task_type="challenge",
                creator_id=admin.id,
                reward_json={},
            )
            open_dated = Task(
                title="Актуальная задача со сроком",
                description="Ещё можно взять",
                deadline=now + timedelta(days=7),
                points=80,
                status=TaskStatus.PUBLISHED,
                task_type="challenge",
                creator_id=admin.id,
                reward_json={},
            )
            open_no_deadline = Task(
                title="Бессрочная задача",
                description="Без жёсткого срока",
                deadline=None,
                points=40,
                status=TaskStatus.PUBLISHED,
                task_type="challenge",
                creator_id=admin.id,
                reward_json={},
            )
            session.add_all([expired, open_dated, open_no_deadline])
            await session.commit()

            assert task_service.is_task_expired(expired, now=now) is True
            assert task_service.is_task_expired(open_dated, now=now) is False
            assert task_service.is_task_expired(open_no_deadline, now=now) is False
            assert task_service.effective_task_status(expired, now=now) == TaskStatus.OVERDUE
            assert task_service.effective_task_status(open_dated, now=now) == TaskStatus.PUBLISHED
            assert task_service.effective_task_status(open_no_deadline, now=now) == TaskStatus.PUBLISHED

            membership, reason = await task_service.claim(session, expired, admin)
            assert membership is None
            assert reason == "closed"
            assert (await session.get(Task, expired.id)).status == TaskStatus.PUBLISHED

            call = SimpleNamespace(
                data="cabinet:tasks",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await my_tasks(call, admin, session)
            text = call.message.answer.await_args.args[0]
            assert "2 открытые задачи" in text
            assert "Актуальная задача со сроком" in text
            assert "Бессрочная задача" in text
            assert "Старая просроченная задача" not in text
            assert "Открыт набор" not in text

            api_available = await read_tasks(
                scope="available", user=admin, session=session, settings=settings
            )
            api_for_you = await read_tasks(
                scope="for_you", user=admin, session=session, settings=settings
            )
            assert {item.id for item in api_available} == {open_dated.id, open_no_deadline.id}
            assert {item.id for item in api_for_you} == {open_dated.id, open_no_deadline.id}
            no_deadline_out = next(item for item in api_available if item.id == open_no_deadline.id)
            assert no_deadline_out.deadline == ""

    async def test_legacy_template_media_tasks_show_real_event_title_date_and_grouping(self):
        settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot")
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            admin = await self._make_user(session, 201, role="admin")
            dept = Department(name="Коммуникации")
            session.add(dept)
            await session.flush()
            media_dir = Direction(name="Медиа", department_id=dept.id, leader_id=admin.id)
            session.add(media_dir)
            await session.flush()
            session.add(
                UserDirection(user_id=admin.id, direction_id=media_dir.id, status="approved")
            )
            event_a = Event(
                title="Вечер настольных игр",
                description="Игры сообщества",
                event_date=date(2026, 12, 12),
                event_time=time(18, 0),
                location="Центр ЭРА",
                format="offline",
                points_for_visit=20,
                created_by=admin.id,
            )
            event_b = Event(
                title="Новогодний квиз ЭРА",
                description="Квиз",
                event_date=date(2026, 12, 20),
                event_time=time(19, 0),
                location="Центр ЭРА",
                format="offline",
                points_for_visit=20,
                created_by=admin.id,
            )
            event_old = Event(
                title="Летний пикник",
                description="Прошедшее событие",
                event_date=date(2026, 8, 25),
                event_time=time(12, 0),
                location="Парк",
                format="offline",
                points_for_visit=20,
                created_by=admin.id,
            )
            session.add_all([event_a, event_b, event_old])
            await session.flush()

            item_a = MediaContentItem(
                source_kind="event_request",
                source_key=f"event:{event_a.id}:full",
                source_type="event",
                source_id=event_a.id,
                rubric="События ЭРА",
                kind="text",
                body="Медиа-пакет для event: Вечер настольных игр",
                status="draft",
            )
            item_b = MediaContentItem(
                source_kind="event_request",
                source_key=f"event:{event_b.id}:full",
                source_type="event",
                source_id=event_b.id,
                rubric="События ЭРА",
                kind="text",
                body="Медиа-пакет для event: Новогодний квиз ЭРА",
                status="draft",
            )
            item_old = MediaContentItem(
                source_kind="event_request",
                source_key=f"event:{event_old.id}:full",
                source_type="event",
                source_id=event_old.id,
                rubric="События ЭРА",
                kind="text",
                body="Медиа-пакет для event: Летний пикник",
                status="draft",
            )
            session.add_all([item_a, item_b, item_old])
            await session.flush()

            legacy_specs = [
                (item_a, "text", "Написать текст для «События ЭРА»", now + timedelta(days=5)),
                (item_a, "design", "Подготовить дизайн для «События ЭРА»", now + timedelta(days=6)),
                (item_b, "photo", "Сделать фото для «События ЭРА»", now + timedelta(days=10)),
                (item_old, "text", "Написать текст для «События ЭРА»", now - timedelta(days=90)),
            ]
            created_tasks: list[Task] = []
            for content_item, kind, raw_title, dl in legacy_specs:
                task = Task(
                    title=raw_title,
                    description="Legacy media task",
                    deadline=dl,
                    points=50,
                    status=TaskStatus.PUBLISHED,
                    task_type="challenge",
                    creator_id=admin.id,
                    reward_json={
                        "media_task": True,
                        "media_content_id": content_item.id,
                        "media_task_kind": kind,
                    },
                )
                session.add(task)
                await session.flush()
                session.add(
                    MediaContentTask(content_id=content_item.id, task_id=task.id, task_kind=kind)
                )
                created_tasks.append(task)
            await session.commit()

            task_a_text, task_a_design, task_b_photo, task_old_text = created_tasks

            call = SimpleNamespace(
                data="cabinet:tasks",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await my_tasks(call, admin, session)
            body = call.message.answer.await_args.args[0]

            assert "3 открытые задачи" in body
            assert "События ЭРА" not in body
            assert "Летний пикник" not in body
            assert "📅 Вечер настольных игр · 12.12.2026" in body
            assert "📅 Новогодний квиз ЭРА · 20.12.2026" in body
            assert "1. Написать текст —" in body
            assert "2. Подготовить дизайн —" in body
            assert "3. Сделать фото —" in body
            # Existing DB rows are never mutated by read/presentation logic.
            assert (await session.get(Task, task_a_text.id)).title == "Написать текст для «События ЭРА»"

            view_open = SimpleNamespace(
                data=f"task:view:{task_a_text.id}",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await task_view(view_open, admin, session)
            open_view_text = view_open.message.answer.await_args.args[0]
            open_view_callbacks = _button_callbacks(
                view_open.message.answer.await_args.kwargs["reply_markup"]
            )
            assert "Написать текст для «Вечер настольных игр»" in open_view_text
            assert "📅 Вечер настольных игр · 12.12.2026" in open_view_text
            assert f"task:join:{task_a_text.id}" in open_view_callbacks

            view_expired = SimpleNamespace(
                data=f"task:view:{task_old_text.id}",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await task_view(view_expired, admin, session)
            expired_view_text = view_expired.message.answer.await_args.args[0]
            expired_view_callbacks = _button_callbacks(
                view_expired.message.answer.await_args.kwargs["reply_markup"]
            )
            assert "Написать текст для «Летний пикник»" in expired_view_text
            assert "Просрочена" in expired_view_text
            assert f"task:join:{task_old_text.id}" not in expired_view_callbacks

            api_tasks = await read_tasks(
                scope="available", user=admin, session=session, settings=settings
            )
            assert [t.id for t in api_tasks] == [task_a_text.id, task_a_design.id, task_b_photo.id]
            assert api_tasks[0].title == "Написать текст для «Вечер настольных игр»"
            assert api_tasks[0].short_title == "Написать текст"
            assert api_tasks[0].group_kind == "event"
            assert api_tasks[0].group_title == "Вечер настольных игр"
            assert api_tasks[0].group_date == "12.12.2026"
            assert all("События ЭРА" not in t.title for t in api_tasks)

            hub = await read_media_hub(user=admin, session=session, settings=settings)
            assert [t.id for t in hub.open_tasks] == [
                task_a_text.id,
                task_a_design.id,
                task_b_photo.id,
            ]
            assert hub.open_tasks[0].title == "Написать текст для «Вечер настольных игр»"
            assert hub.open_tasks[0].group_title == "Вечер настольных игр"

    async def test_new_request_media_package_stores_real_event_and_project_title(self):
        settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot")
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            admin = await self._make_user(session, 301, role="admin")
            event = Event(
                title="Зимний форум ЭРА",
                description="Форум",
                event_date=date(2026, 12, 18),
                event_time=time(11, 0),
                location="Ереван",
                format="offline",
                points_for_visit=30,
                created_by=admin.id,
            )
            project = Project(
                title="Школа волонтёров",
                short_description="Образовательный проект",
                author_id=admin.id,
            )
            session.add_all([event, project])
            await session.flush()

            ev_req = await media_service.request_media_package(
                session,
                source_type="event",
                source_id=event.id,
                package_type="full",
                requester=admin,
                settings=settings,
                due_at=now + timedelta(days=10),
            )
            pr_req = await media_service.request_media_package(
                session,
                source_type="project",
                source_id=project.id,
                package_type="full",
                requester=admin,
                settings=settings,
                due_at=now + timedelta(days=12),
            )
            await session.commit()

            ev_content = await session.get(MediaContentItem, ev_req.content_id)
            pr_content = await session.get(MediaContentItem, pr_req.content_id)
            assert ev_content.title == "Зимний форум ЭРА"
            assert pr_content.title == "Школа волонтёров"

            ev_tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                        .where(MediaContentTask.content_id == ev_content.id)
                    )
                ).all()
            )
            pr_tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                        .where(MediaContentTask.content_id == pr_content.id)
                    )
                ).all()
            )
            assert len(ev_tasks) == 6
            assert len(pr_tasks) == 6
            assert all("«Зимний форум ЭРА»" in task.title for task in ev_tasks)
            assert all("События ЭРА" not in task.title for task in ev_tasks)
            assert all("«Школа волонтёров»" in task.title for task in pr_tasks)
            assert all("Проекты ЭРА" not in task.title for task in pr_tasks)

    async def test_long_source_title_keeps_stored_media_task_titles_within_column_limit(self):
        settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot")
        long_title = ("Большой городской фестиваль ЭРА «Весна» " * 10).strip()[:255]
        self.assertEqual(len(long_title), 255)
        for kind in media_service.MEDIA_TASK_KINDS:
            stored = media_service.media_task_storage_title(kind, long_title)
            self.assertLessEqual(len(stored), media_service.MEDIA_TASK_TITLE_MAX_LENGTH)
            self.assertTrue(stored.endswith("…»"))
        short = media_service.media_task_storage_title("text", "Вечер")
        self.assertEqual(short, "Написать текст для «Вечер»")

        async with self.session_factory() as session:
            admin = await self._make_user(session, 601, role="admin")
            event = Event(
                title=long_title,
                description="Фестиваль",
                event_date=date(2026, 12, 25),
                event_time=time(10, 0),
                location="Ереван",
                format="offline",
                points_for_visit=30,
                created_by=admin.id,
            )
            session.add(event)
            await session.flush()

            request = await media_service.request_media_package(
                session,
                source_type="event",
                source_id=event.id,
                package_type="full",
                requester=admin,
                settings=settings,
                due_at=datetime.now(timezone.utc) + timedelta(days=10),
            )
            await session.commit()

            content = await session.get(MediaContentItem, request.content_id)
            tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .join(MediaContentTask, MediaContentTask.task_id == Task.id)
                        .where(MediaContentTask.content_id == content.id)
                    )
                ).all()
            )
            self.assertEqual(len(tasks), 6)
            for task in tasks:
                self.assertLessEqual(len(task.title), media_service.MEDIA_TASK_TITLE_MAX_LENGTH)
                self.assertEqual(task.reward_json["source_title"], long_title)

            contexts = await task_presentation_service.resolve_task_contexts(session, tasks)
            for task in tasks:
                self.assertEqual(contexts[task.id].group_title, long_title)
                self.assertIn(long_title, contexts[task.id].display_title)

    async def test_bot_task_list_pagination_buttons_and_empty_state(self):
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            admin = await self._make_user(session, 401, role="admin")
            # Empty state when only expired tasks exist
            session.add(
                Task(
                    title="Прошлогодняя задача",
                    description="Истекла",
                    deadline=now - timedelta(days=5),
                    points=25,
                    status=TaskStatus.PUBLISHED,
                    task_type="challenge",
                    creator_id=admin.id,
                )
            )
            await session.commit()

            empty_call = SimpleNamespace(
                data="cabinet:tasks",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await my_tasks(empty_call, admin, session)
            empty_text = empty_call.message.answer.await_args.args[0]
            assert "0 открытых задач" in empty_text
            assert "Сейчас нет открытых задач" in empty_text

            # Add 10 open tasks to verify 6-per-page pagination and controls
            open_tasks = []
            for idx in range(1, 11):
                task = Task(
                    title=f"Открытая задача #{idx}",
                    description=f"Описание {idx}",
                    deadline=now + timedelta(days=idx),
                    points=50,
                    status=TaskStatus.PUBLISHED,
                    task_type="challenge",
                    creator_id=admin.id,
                )
                session.add(task)
                open_tasks.append(task)
            await session.commit()

            page1_call = SimpleNamespace(
                data="cabinet:tasks",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await my_tasks(page1_call, admin, session)
            page1_text = page1_call.message.answer.await_args.args[0]
            page1_callbacks = _button_callbacks(
                page1_call.message.answer.await_args.kwargs["reply_markup"]
            )
            assert "10 открытых задач · стр. 1/2" in page1_text
            assert "Открытая задача #1" in page1_text
            assert "Открытая задача #6" in page1_text
            assert "Открытая задача #7" not in page1_text
            assert f"task:view:{open_tasks[0].id}" in page1_callbacks
            assert f"task:join:{open_tasks[0].id}" in page1_callbacks
            assert "tasks:list:open:page:1" in page1_callbacks
            assert "tasks:noop" in page1_callbacks
            assert "tasks:list:open:page:0" not in page1_callbacks

            page2_call = SimpleNamespace(
                data="tasks:list:open:page:1",
                answer=AsyncMock(),
                message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
            )
            await tasks_list_page(page2_call, admin, session)
            page2_call.message.edit_text.assert_awaited_once()
            page2_text = page2_call.message.edit_text.await_args.args[0]
            page2_callbacks = _button_callbacks(
                page2_call.message.edit_text.await_args.kwargs["reply_markup"]
            )
            assert "10 открытых задач · стр. 2/2" in page2_text
            assert "Открытая задача #7" in page2_text
            assert "Открытая задача #10" in page2_text
            assert "tasks:list:open:page:0" in page2_callbacks
            assert "tasks:list:open:page:2" not in page2_callbacks

            # Out-of-range page clamps safely to last page
            overflow_call = SimpleNamespace(
                data="tasks:list:open:page:99",
                answer=AsyncMock(),
                message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
            )
            await tasks_list_page(overflow_call, admin, session)
            assert "стр. 2/2" in overflow_call.message.edit_text.await_args.args[0]

    async def test_expired_active_task_shows_overdue_status_in_bot_mini_app_and_home(self):
        settings = Settings(bot_token="1234567890:test-token", bot_username="ERA_1bot")
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            user = await self._make_user(session, 501, role="participant")
            overdue_active = Task(
                title="Задача с прошедшим дедлайном",
                description="Нужно сдать отчёт",
                deadline=now - timedelta(days=2),
                points=60,
                status=TaskStatus.IN_PROGRESS,
                task_type="challenge",
                assignee_id=user.id,
                creator_id=user.id,
            )
            expired_unclaimed = Task(
                title="Просроченная открытая",
                description="Не должна попадать в доступные",
                deadline=now - timedelta(days=3),
                points=30,
                status=TaskStatus.PUBLISHED,
                task_type="challenge",
                creator_id=user.id,
            )
            session.add_all([overdue_active, expired_unclaimed])
            await session.flush()
            session.add(
                TaskParticipant(task_id=overdue_active.id, user_id=user.id, status="joined")
            )
            await session.commit()

            active_call = SimpleNamespace(
                data="tasks:list:active",
                answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await tasks_list(active_call, user, session)
            active_text = active_call.message.answer.await_args.args[0]
            assert "Задача с прошедшим дедлайном" in active_text
            assert "Просрочена" in active_text

            mine = await read_tasks(scope="mine", user=user, session=session, settings=settings)
            assert len(mine) == 1
            assert mine[0].id == overdue_active.id
            assert mine[0].status == TaskStatus.OVERDUE

            snapshot = await home_service.build_home_snapshot(session, user)
            assert snapshot.tasks_available_count == 0
            assert snapshot.active_task is not None
            assert snapshot.active_task.status == TaskStatus.OVERDUE
