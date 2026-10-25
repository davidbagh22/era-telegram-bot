from unittest import IsolatedAsyncioTestCase

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.media_extras import read_my_media_task_attachments
from app.database.base import Base
from app.database.media_models import MediaAttachment
from app.database.models import Department, Direction, Task, TaskParticipant, User, UserDirection
from app.services import task_service
from app.services.media_attachment_service import confirm_attachment


class MediaTaskAccessTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed(self, session):
        users = [User(telegram_id=100+i, first_name="Участник", application_status="approved") for i in range(3)]
        department = Department(name="Внешние связи")
        session.add_all([*users, department])
        await session.flush()
        direction = Direction(name="Медиа", department_id=department.id)
        session.add(direction)
        await session.flush()
        membership = UserDirection(user_id=users[0].id, direction_id=direction.id, status="approved")
        session.add(membership)
        task = Task(title="Медиа", description="Материал", creator_id=users[2].id,
                    task_type="challenge", status="published", reward_json={"media_task": True}, max_participants=2)
        session.add(task)
        await session.flush()
        return users, direction, membership, task

    async def test_outsider_cannot_list_view_claim_or_submit_even_with_the_task_id(self):
        async with self.factory() as session:
            users, _, _, task = await self.seed(session)
            outsider = users[1]
            self.assertNotIn(task, await task_service.list_for_user(session, outsider))
            self.assertFalse(await task_service.can_view(session, task, outsider))
            self.assertFalse(await task_service.can_submit(session, task, outsider))
            self.assertEqual(await task_service.claim(session, task, outsider), (None, "closed"))

    async def test_revocation_blocks_old_claim_and_attached_file_buttons(self):
        async with self.factory() as session:
            users, _, membership, task = await self.seed(session)
            member = users[0]
            _, reason = await task_service.claim(session, task, member)
            self.assertIsNone(reason)
            file = MediaAttachment(target_type="task", target_id=task.id, uploader_id=member.id,
                                   status="attached", media_type="photo", telegram_file_id="private-file")
            session.add(file)
            await session.flush()
            self.assertTrue(await task_service.can_submit(session, task, member))
            membership.status = "rejected"
            await session.flush()
            self.assertFalse(await task_service.can_view(session, task, member))
            self.assertFalse(await task_service.can_submit(session, task, member))
            self.assertEqual(await task_service.claim(session, task, member), (None, "closed"))
            with self.assertRaises(PermissionError):
                await confirm_attachment(session, attachment_id=file.id, user=member)

    async def test_team_members_cannot_open_another_performers_result_files(self):
        async with self.factory() as session:
            users, direction, _, task = await self.seed(session)
            performer, observer = users[:2]
            session.add(UserDirection(user_id=observer.id, direction_id=direction.id, status="approved"))
            await session.flush()
            await task_service.claim(session, task, performer)
            file = MediaAttachment(target_type="task", target_id=task.id, uploader_id=performer.id,
                                   status="attached", media_type="photo", telegram_file_id="private-file")
            session.add(file)
            await session.flush()
            self.assertTrue(await task_service.can_view(session, task, observer))
            with self.assertRaises(HTTPException) as caught:
                await read_my_media_task_attachments(task.id, observer, session)
            self.assertEqual(caught.exception.status_code, 404)
            files = await read_my_media_task_attachments(task.id, performer, session)
            self.assertEqual([item.id for item in files], [file.id])

    async def test_non_media_public_tasks_keep_the_existing_application_flow(self):
        async with self.factory() as session:
            users, _, _, task = await self.seed(session)
            task.reward_json = {}
            await session.flush()
            participant, reason = await task_service.claim(session, task, users[1])
            self.assertIsNone(reason)
            self.assertEqual(participant.status, "pending")

    async def test_legacy_pending_request_cannot_exceed_the_performer_limit(self):
        async with self.factory() as session:
            users, direction, _, task = await self.seed(session)
            task.max_participants = 1
            session.add(UserDirection(user_id=users[1].id, direction_id=direction.id, status="approved"))
            await session.flush()
            _, reason = await task_service.claim(session, task, users[0])
            self.assertIsNone(reason)
            session.add(TaskParticipant(task_id=task.id, user_id=users[1].id, status="pending"))
            await session.flush()
            self.assertEqual(await task_service.claim(session, task, users[1]), (None, "full"))
