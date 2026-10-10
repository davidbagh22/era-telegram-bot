from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, func

from tests.test_task_review_service import TaskReviewServiceTests
from app.config import Settings
from app.database.models import Task, TaskSubmission, PortfolioItem
from app.services.public_task_catalog_service import publish_catalog
from app.services.task_service import claim, can_view
from app.services.task_review_service import decide_submission


class PublicCatalogTests(TaskReviewServiceTests):
    async def test_catalog_repeat_self_service_and_independent_completion(self):
        settings = Settings(bot_token='1234567890:test-token', bot_username='ERA_1bot')
        async with self.session_factory() as s:
            admin = await self._make_user(s, 11, role='admin')
            first = await self._make_user(s, 12)
            second = await self._make_user(s, 13)
            await s.commit()
            result = await publish_catalog(s, creator=admin, bot=None, settings=settings)
            assert result['created'] == 20
            again = await publish_catalog(s, creator=admin, bot=None, settings=settings)
            assert again['created'] == 0
            assert await s.scalar(select(func.count()).select_from(Task)) == 20
            task = await s.scalar(select(Task).order_by(Task.id))
            member, error = await claim(s, task, first)
            assert error is None and member.status == 'joined'
            submission = TaskSubmission(task_id=task.id, user_id=first.id, text='Result', status='pending')
            s.add(submission)
            await s.flush()
            award = await decide_submission(s, submission, task, first, action='approve', comment='', actor=admin)
            assert award.points_awarded == task.points
            assert task.status == 'published'
            assert await can_view(s, task, second)
            assert (await claim(s, task, second))[0].status == 'joined'
            repeated = await decide_submission(s, submission, task, first, action='approve', comment='', actor=admin)
            assert repeated.points_awarded == 0
            assert await s.scalar(select(func.count()).select_from(PortfolioItem)) == 1

    async def test_transport_sees_committed_tasks_and_distinct_links(self):
        settings = Settings(bot_token='1234567890:test-token', bot_username='ERA_1bot')
        async with self.session_factory() as s:
            admin = await self._make_user(s, 21, role='admin')
            await s.commit()
            async def send(*args, **kwargs):
                async with self.session_factory() as verify:
                    assert await verify.scalar(select(func.count()).select_from(Task)) == 20
                rows = kwargs['reply_markup'].inline_keyboard
                assert rows[0][0].url.endswith('start=tasks_catalog')
                assert rows[1][0].url.endswith('start=bookclub')
                return SimpleNamespace(sent=True)
            with patch('app.services.public_task_catalog_service.safe_send_once', side_effect=send), patch('app.services.public_task_catalog_service.send_general_topic', new=AsyncMock(return_value=True)):
                result = await publish_catalog(s, creator=admin, bot=SimpleNamespace(), settings=settings)
            assert result['group_sent'] and result['sent'] == 1
