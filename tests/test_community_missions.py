from __future__ import annotations

import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.content.community_missions_pack import load_community_missions
from app.database import Base  # imports community model metadata
from app.database.community_models import CommunityMissionTemplate, TaskSquad, TaskSubtask
from app.database.models import TaskParticipant, User
from app.services import task_service
from app.services.community_mission_service import launch_mission, seed_community_missions
from app.utils.constants import ApplicationStatus


class CommunityMissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_authored_pack_contains_exactly_26_missions(self) -> None:
        items = load_community_missions()
        self.assertEqual(len(items), 26)
        self.assertEqual(items[0]["code"], "M1.1")
        self.assertEqual(items[-1]["code"], "M6.5")
        self.assertTrue(all(item["deliverable"] for item in items))

    async def test_seed_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            await seed_community_missions(session)
            await seed_community_missions(session)
            count = int(
                await session.scalar(select(func.count(CommunityMissionTemplate.id))) or 0
            )
            self.assertEqual(count, 26)

    async def test_multiple_people_join_one_task_squad(self) -> None:
        async with self.session_factory() as session:
            creator = User(
                telegram_id=1,
                first_name="Creator",
                application_status=ApplicationStatus.APPROVED,
            )
            first = User(
                telegram_id=2,
                first_name="First",
                application_status=ApplicationStatus.APPROVED,
            )
            second = User(
                telegram_id=3,
                first_name="Second",
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([creator, first, second])
            await session.flush()
            await seed_community_missions(session)
            template = await session.scalar(
                select(CommunityMissionTemplate).where(
                    CommunityMissionTemplate.code == "M1.1"
                )
            )
            self.assertIsNotNone(template)
            task = await launch_mission(session, template, creator_id=creator.id)

            membership1, error1 = await task_service.claim(session, task, first)
            membership2, error2 = await task_service.claim(session, task, second)
            self.assertIsNone(error1)
            self.assertIsNone(error2)
            self.assertEqual(membership1.status, "joined")
            self.assertEqual(membership2.status, "joined")

            squads = list(
                (await session.scalars(select(TaskSquad).where(TaskSquad.task_id == task.id))).all()
            )
            self.assertEqual(len(squads), 1)
            self.assertEqual(squads[0].status, "active")
            participants = list(
                (
                    await session.scalars(
                        select(TaskParticipant).where(TaskParticipant.task_id == task.id)
                    )
                ).all()
            )
            self.assertEqual(len(participants), 2)
            subtasks = list(
                (
                    await session.scalars(
                        select(TaskSubtask).where(TaskSubtask.squad_id == squads[0].id)
                    )
                ).all()
            )
            self.assertGreaterEqual(len(subtasks), 2)

    async def test_repeated_claim_does_not_create_second_squad(self) -> None:
        async with self.session_factory() as session:
            creator = User(telegram_id=1, first_name="Creator")
            user = User(
                telegram_id=2,
                first_name="User",
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([creator, user])
            await session.flush()
            await seed_community_missions(session)
            template = await session.scalar(
                select(CommunityMissionTemplate).where(
                    CommunityMissionTemplate.code == "M6.1"
                )
            )
            task = await launch_mission(session, template, creator_id=creator.id)
            await task_service.claim(session, task, user)
            _, reason = await task_service.claim(session, task, user)
            self.assertEqual(reason, "already_joined")
            count = int(
                await session.scalar(
                    select(func.count(TaskSquad.id)).where(TaskSquad.task_id == task.id)
                )
                or 0
            )
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
