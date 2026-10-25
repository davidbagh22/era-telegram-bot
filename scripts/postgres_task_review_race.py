"""Prove task review outcomes using isolated CI PostgreSQL, never production."""
import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import PointTransaction, Task, TaskSubmission, User
from app.services.task_review_service import decide_submission
from app.utils.constants import ApplicationStatus, Role


async def main():
    url = os.environ['DATABASE_URL']
    if make_url(url).database != 'era_test':
        raise RuntimeError('Only isolated era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid = 20_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    try:
        async with sessions() as session:
            staff = User(telegram_id=uid, first_name='CI staff', role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED)
            member = User(telegram_id=uid+1, first_name='CI member', application_status=ApplicationStatus.APPROVED)
            session.add_all([staff, member])
            await session.flush()
            task = Task(title='CI review race', description='Isolated fixture', creator_id=staff.id,
                assignee_id=member.id, task_type='private', status='review', points=20)
            session.add(task)
            await session.flush()
            submission = TaskSubmission(task_id=task.id, user_id=member.id, text='CI result', status='pending')
            session.add(submission)
            await session.commit()
            staff_id, member_id, task_id, submission_id = staff.id, member.id, task.id, submission.id

        async def decide(action):
            async with sessions() as session:
                result = await decide_submission(session, await session.get(TaskSubmission, submission_id),
                    await session.get(Task, task_id), await session.get(User, member_id),
                    action=action, comment='' if action == 'approve' else 'Stale review',
                    actor=await session.get(User, staff_id))
                await session.commit()
                return result.changed, result.points_awarded

        accepted = await asyncio.wait_for(asyncio.gather(*(decide('approve') for _ in range(8))), 45)
        assert sum(changed for changed, _ in accepted) == 1 and sum(points for _, points in accepted) == 20
        stale = await asyncio.wait_for(asyncio.gather(*(decide('revision' if i % 2 else 'reject') for i in range(8))), 45)
        assert not any(changed or points for changed, points in stale)
        async with sessions() as session:
            assert (await session.get(TaskSubmission, submission_id)).status == 'approved'
            assert (await session.get(Task, task_id)).status == 'completed'
            count, points = (await session.execute(select(func.count(), func.sum(PointTransaction.points)).where(
                PointTransaction.related_task_id == task_id, PointTransaction.user_id == member_id))).one()
            assert count == 1 and points == 20
        print('PostgreSQL: 8 approvals produce one decision and one reward; 8 stale returns/rejections preserve both')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
