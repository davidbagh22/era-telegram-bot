"""Exercise workcenter races against disposable CI PostgreSQL only."""
import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AppSetting, Broadcast, Task, TaskDelivery, User
from app.services import leaders_access_service as access, leaders_campaign_service as campaigns, leaders_workspace as work
from app.utils.constants import ApplicationStatus, Role


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only isolated era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 30_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    settings = Settings(bot_token='0000000000:CITESTTOKEN', leaders_chat_id=-uid, general_chat_id=-uid-1)
    try:
        async with sessions() as session:
            users = [User(telegram_id=uid+i, first_name='CI workcenter', role=Role.ADMIN if i == 0 else Role.LEADER,
                          application_status=ApplicationStatus.APPROVED) for i in range(9)]
            candidate = User(telegram_id=uid+9, first_name='CI candidate', role=Role.PARTICIPANT,
                             application_status=ApplicationStatus.APPROVED)
            session.add_all([*users, candidate, AppSetting(key=f'leaders_forum:{-uid}:important', value='{"mode":"plain"}')])
            await session.commit()
            admin_id, member_ids, candidate_id = users[0].id, [u.id for u in users[1:]], candidate.id

        async def create():
            async with sessions() as session:
                task = await work.create_task(session, settings, await session.get(User, admin_id),
                    title='CI confirmed once', request_key=f'ci-{uid}')
                await session.commit()
                return task.id
        ids = await asyncio.wait_for(asyncio.gather(*(create() for _ in range(8))), 45)
        assert len(set(ids)) == 1
        task_id = ids[0]

        async def claim(user_id):
            async with sessions() as session:
                try:
                    await work.claim_task(session, await session.get(Task, task_id), await session.get(User, user_id))
                    await session.commit()
                    return True
                except ValueError:
                    await session.rollback()
                    return False
        assert sum(await asyncio.wait_for(asyncio.gather(*(claim(i) for i in member_ids)), 45)) == 1

        async def promote():
            async with sessions() as session:
                try:
                    await access.set_leader(session, settings, await session.get(User, admin_id), candidate_id,
                                            enabled=True, expected_role='participant')
                    await session.commit()
                    return True
                except ValueError:
                    await session.rollback()
                    return False
        assert sum(await asyncio.wait_for(asyncio.gather(*(promote() for _ in range(8))), 45)) == 1

        async def campaign():
            async with sessions() as session:
                item = await campaigns.create(session, settings, await session.get(User, admin_id),
                    body='CI never sent', request_key=f'ci-{uid}', mode='group')
                await session.commit()
                return item.id
        broadcasts = await asyncio.wait_for(asyncio.gather(*(campaign() for _ in range(8))), 45)
        assert len(set(broadcasts)) == 1
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TaskDelivery).where(TaskDelivery.task_id == task_id)) == 1
            assert (await session.get(Task, task_id)).assignee_id in member_ids
            assert (await session.get(User, candidate_id)).role == Role.LEADER
            assert (await session.get(Broadcast, broadcasts[0])).status == 'sending'
        print('PostgreSQL: one task/card, one claimant, one role transition and one campaign under 8 concurrent confirmations; no Telegram calls')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
