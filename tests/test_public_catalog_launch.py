from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, func

from tests.test_task_review_service import TaskReviewServiceTests
from app.config import Settings
from app.database.models import AppSetting, Task, TaskSubmission, PortfolioItem
from app.handlers.participant.task_block2 import task_view, tasks_list
from app.services.public_task_catalog_service import publish_catalog
from app.services.task_service import claim, can_view, can_submit, completed_task_ids
from app.services.task_review_service import decide_submission
from app.utils.constants import ApplicationStatus


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
            seeded = list((await s.scalars(select(Task))).all())
            for catalog_task in seeded:
                catalog_task.max_participants = 50
                catalog_task.reward_json = {"catalog_key": catalog_task.reward_json["catalog_key"]}
            await s.commit()
            again = await publish_catalog(s, creator=admin, bot=None, settings=settings)
            assert again['created'] == 0
            assert await s.scalar(select(func.count()).select_from(Task)) == 20
            normalized = list((await s.scalars(select(Task))).all())
            assert all(task.max_participants is None for task in normalized)
            assert all((task.reward_json or {}).get('public_task') for task in normalized)
            task = await s.scalar(select(Task).order_by(Task.id))
            member, error = await claim(s, task, first)
            assert error is None and member.status == 'joined'
            submission = TaskSubmission(task_id=task.id, user_id=first.id, text='Result', status='pending')
            s.add(submission)
            await s.flush()
            award = await decide_submission(s, submission, task, first, action='approve', comment='', actor=admin)
            assert award.points_awarded == task.points
            assert task.status == 'published'
            assert member.status == 'completed'
            assert not await can_submit(s, task, first)
            assert await completed_task_ids(s, first, [task]) == {task.id}
            from app.api.v1.tasks import _to_task_out
            from app.services.activity_service import list_tasks

            assert task not in await list_tasks(s, first, 'available')
            assert task in await list_tasks(s, first, 'completed')
            task_out = await _to_task_out(s, task, first, settings)
            assert task_out.status == 'completed'
            assert task_out.is_joined_or_assigned
            assert not task_out.can_submit
            existing, reason = await claim(s, task, first)
            assert existing.status == 'completed' and reason == 'completed'
            assert await can_view(s, task, second)
            assert (await claim(s, task, second))[0].status == 'joined'
            repeated = await decide_submission(s, submission, task, first, action='approve', comment='', actor=admin)
            assert repeated.points_awarded == 0
            assert await s.scalar(select(func.count()).select_from(PortfolioItem)) == 1

            for mode in ('active', 'open'):
                call = SimpleNamespace(
                    data=f'tasks:list:{mode}', answer=AsyncMock(),
                    message=SimpleNamespace(answer=AsyncMock()),
                )
                await tasks_list(call, first, s)
                assert task.title not in call.message.answer.await_args.args[0]

            archive_call = SimpleNamespace(
                data='tasks:list:archive', answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await tasks_list(archive_call, first, s)
            assert task.title in archive_call.message.answer.await_args.args[0]
            assert 'Выполнено' in archive_call.message.answer.await_args.args[0]

            view_call = SimpleNamespace(
                data=f'task:view:{task.id}', answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()),
            )
            await task_view(view_call, first, s)
            view_text = view_call.message.answer.await_args.args[0]
            callbacks = [
                button.callback_data
                for row in view_call.message.answer.await_args.kwargs['reply_markup'].inline_keyboard
                for button in row
            ]
            assert 'Выполнено' in view_text
            assert not any(value.startswith('task:result:') for value in callbacks)

    async def test_transport_sees_committed_tasks_and_distinct_links(self):
        settings = Settings(bot_token='1234567890:test-token', bot_username='ERA_1bot')
        async with self.session_factory() as s:
            admin = await self._make_user(s, 21, role='admin')
            await s.commit()
            async def send_topic(_bot, _settings, key, text, **kwargs):
                assert key == 'notifications'
                assert 'Две новые возможности' in text
                async with self.session_factory() as verify:
                    assert await verify.scalar(select(func.count()).select_from(Task)) == 20
                rows = kwargs['reply_markup'].inline_keyboard
                assert rows[0][0].url.endswith('start=tasks_catalog')
                assert rows[1][0].url.endswith('start=bookclub')
                assert kwargs['delivery_key'] == 'public-catalog-v2'
                return True
            bot = SimpleNamespace(send_message=AsyncMock())
            with patch('app.services.public_task_catalog_service.send_general_topic', side_effect=send_topic) as public_send:
                result = await publish_catalog(s, creator=admin, bot=bot, settings=settings)
            public_send.assert_awaited_once()
            bot.send_message.assert_not_awaited()
            assert result['group_sent'] and result['sent'] == 1


class BookAnalyticsTests(TaskReviewServiceTests):
    async def test_subscriber_count_matches_eligible_daily_audience(self):
        from app.api.v1.leaders_workspace import book_analytics

        async with self.session_factory() as session:
            admin = await self._make_user(session, 31, role='admin')
            await self._make_user(session, 32, book_club_subscribed=True)
            await self._make_user(
                session, 33, book_club_subscribed=True,
                application_status=ApplicationStatus.PENDING,
            )
            await self._make_user(session, 34, book_club_subscribed=True, is_blocked=True)
            await self._make_user(session, 35, book_club_subscribed=True, is_archived=True)
            session.add(AppSetting(key='book-reflection:2:1', value={'answer': 'private'}))
            await session.commit()

            result = await book_analytics(admin, session)

            assert result['subscribers'] == 1
            assert result['responses'] == 1
            assert result['respondents'] == 1
