"""Concurrent project ownership and stale decisions on isolated CI PostgreSQL."""
import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AppSetting, AuditLog, PermissionGrant, Project, User
from app.services.project_review_assignment_service import assigned_project_reviewer, claim_project_review
from app.services.project_workflow_service import ProjectDecisionConflict, decide_project, project_review_version
from app.utils.constants import ApplicationStatus, ProjectStatus


async def main():
    url = os.environ['DATABASE_URL']
    parsed = make_url(url)
    if parsed.database != 'era_test' or parsed.host not in {'localhost', '127.0.0.1', '::1'}:
        raise RuntimeError('Only isolated local era_test is allowed')
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(bot_token='0000000000:CITESTTOKEN', admin_ids=[])
    uid = 40_000_000_000 + int(uuid.uuid4().hex[:7], 16)
    try:
        async with sessions() as session:
            author = User(telegram_id=uid, first_name='CI project author', application_status=ApplicationStatus.APPROVED)
            reviewers = [User(telegram_id=uid+i+1, first_name=f'CI reviewer {i}',
                              application_status=ApplicationStatus.APPROVED) for i in range(8)]
            session.add_all([author, *reviewers])
            await session.flush()
            project = Project(author_id=author.id, title='Isolated project review race',
                              short_description='CI fixture', status=ProjectStatus.INITIAL_REVIEW)
            session.add(project)
            await session.flush()
            for reviewer in reviewers:
                session.add(PermissionGrant(user_id=reviewer.id, permission='projects.review',
                    scope_type='project', scope_id=project.id, granted_by=author.id, is_active=True))
            await session.commit()
            project_id, reviewer_ids = project.id, [u.id for u in reviewers]
            version = project_review_version(project)

        async def claim(reviewer_id):
            async with sessions() as session:
                try:
                    await claim_project_review(session, project_id, await session.get(User, reviewer_id), settings)
                    await session.commit()
                    return reviewer_id
                except PermissionError:
                    await session.rollback()
                    return None

        winners = await asyncio.wait_for(asyncio.gather(*(claim(i) for i in reviewer_ids)), 45)
        assert len([i for i in winners if i is not None]) == 1, winners
        winner = next(i for i in winners if i is not None)

        async def decide(action):
            async with sessions() as session:
                try:
                    await decide_project(session, await session.get(Project, project_id), action=action,
                        comment='CI verified decision', actor=await session.get(User, winner),
                        settings=settings, expected_version=version)
                    await session.commit()
                    return True
                except ProjectDecisionConflict:
                    await session.rollback()
                    return False

        decisions = await asyncio.wait_for(asyncio.gather(*(decide('initial_accept') for _ in range(8))), 45)
        assert sum(decisions) == 1, decisions
        assert not any(await asyncio.wait_for(asyncio.gather(*(decide('reject') for _ in range(8))), 45))
        async with sessions() as session:
            assert (await session.get(Project, project_id)).status == ProjectStatus.VENUE_REVIEW
            assert await assigned_project_reviewer(session, project_id) == winner
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.entity_type == 'project', AuditLog.entity_id == project_id,
                AuditLog.action == 'project_review_decision')) == 1
            assert await session.scalar(select(func.count()).select_from(AppSetting).where(
                AppSetting.key.like(f'project-review-notice:{project_id}:%'))) == 1
        print('PostgreSQL: one owner from 8 claims; one decision and notice from 8 approvals; 8 stale rejections blocked')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
