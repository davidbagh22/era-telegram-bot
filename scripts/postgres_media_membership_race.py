"""Media membership and appointment races, disposable CI PostgreSQL only."""
import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AuditLog, Task, TaskParticipant, User, UserDirection
from app.services import task_service
from app.services.media_leadership_service import change_leader, leadership_state, set_invitation
from app.services.media_membership_service import request_join
from app.services.media_service import can_manage_media


async def main():
    url = os.environ["DATABASE_URL"]
    if make_url(url).database != "era_test":
        raise RuntimeError("Only isolated era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identity = 40_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    try:
        async with sessions() as session:
            users = [User(telegram_id=identity+i, first_name="CI media", application_status="approved") for i in range(3)]
            session.add_all(users)
            await session.commit()
            chair_id, member_id, leader_id = [u.id for u in users]
            settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=chair_id,
                                media_manager_ids=[identity+2])

        async def join():
            async with sessions() as session:
                result = await request_join(session, identity+1, await session.get(User, member_id))
                await session.commit()
                return result
        outcomes = await asyncio.wait_for(asyncio.gather(*(join() for _ in range(8))), 45)
        assert outcomes.count("joined") == 1, outcomes
        async with sessions() as session:
            direction, revision = await leadership_state(session)
            assert await session.scalar(select(func.count()).select_from(UserDirection).where(
                UserDirection.user_id == member_id, UserDirection.direction_id == direction.id)) == 1
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "media.member_joined", AuditLog.new_value["user_id"].as_integer() == member_id)) == 1

        async def appoint():
            async with sessions() as session:
                try:
                    await change_leader(session, await session.get(User, chair_id), settings,
                                        target_telegram_id=identity+2, expected_revision=revision)
                    await session.commit()
                    return True
                except ValueError as exc:
                    assert str(exc) == "media_leader_stale_confirmation", str(exc)
                    await session.rollback()
                    return False
        assert sum(await asyncio.wait_for(asyncio.gather(*(appoint() for _ in range(8))), 45)) == 1
        async with sessions() as session:
            task = Task(title="CI media capacity", description="Isolated fixture", creator_id=chair_id,
                        task_type="challenge", status="published", max_participants=1, reward_json={"media_task": True})
            session.add(task)
            await session.commit()
            task_id = task.id
        async def claim(user_id):
            async with sessions() as session:
                _, reason = await task_service.claim(session, await session.get(Task, task_id), await session.get(User, user_id))
                await session.commit()
                return reason
        claims = await asyncio.wait_for(asyncio.gather(*(claim([member_id, leader_id][i % 2]) for i in range(8))), 45)
        assert claims.count(None) == 1, claims
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TaskParticipant).where(
                TaskParticipant.task_id == task_id, TaskParticipant.status == "joined")) == 1
        async with sessions() as session:
            leader = await session.get(User, leader_id)
            assert await can_manage_media(session, leader, settings)
            _, revision = await leadership_state(session)
            chair = await session.get(User, chair_id)
            await change_leader(session, chair, settings, target_telegram_id=None, expected_revision=revision)
            assert not await can_manage_media(session, leader, settings)
            assert not await task_service.can_view(session, await session.get(Task, task_id), leader)
            await set_invitation(session, chair, settings, enabled=False)
            await session.commit()
        async with sessions() as session:
            try:
                await request_join(session, identity+1, await session.get(User, member_id))
                raise AssertionError("Disabled invitation accepted")
            except ValueError as exc:
                assert str(exc) == "media_invitation_disabled"
        print("Media PostgreSQL races passed: join once, appointment once, performer capacity, immediate revocation, disabled invite")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
