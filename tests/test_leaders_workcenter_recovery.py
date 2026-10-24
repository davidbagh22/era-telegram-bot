from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from aiogram.types import Message, Chat, User as TelegramUser, CallbackQuery
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database.base import Base
from app.config import Settings
from app.handlers.leader_chat_workcenter import router
from app.services.leaders_topics_service import setup_leaders_topics
from app.services.weekly_pulse_cycle_service import create_or_get_cycle


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_assignment_callback_not_swallowed(self):
        handler = next(h for h in router.callback_query.handlers if h.callback.__name__ == 'handle_leaders_task_card_action')
        sender = TelegramUser(id=1, is_bot=False, first_name='A')
        event = CallbackQuery(id='1', from_user=sender, chat_instance='1', data='leaders_task:assign:42')
        self.assertFalse((await handler.check(event))[0])
        self.assertTrue((await handler.check(event.model_copy(update={'data': 'leaders_task:start:42'})))[0])

    async def test_pulse_start_does_not_capture_other_start_payloads(self):
        from datetime import datetime, timezone
        handler = next(h for h in router.message.handlers if h.callback.__name__ == 'connect_pulse_from_deep_link')
        event = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=1, type='private'), text='/start pulse_connect')
        bot = AsyncMock()
        self.assertTrue((await handler.check(event, bot=bot))[0])
        for text in ['/start', '/start ref_hello', '/start event_3']:
            self.assertFalse((await handler.check(event.model_copy(update={'text': text}), bot=bot))[0])

    async def test_rebind_resets_message_but_preserves_cycle(self):
        async with self.factory() as session:
            cycle = await create_or_get_cycle(session, date_from=date(2026,10,5), date_to=date(2026,10,11), leader_chat_id=-1001)
            cycle.announcement_message_id = 42
            again = await create_or_get_cycle(session, date_from=date(2026,10,5), date_to=date(2026,10,11), leader_chat_id=-1002)
            self.assertEqual(cycle.id, again.id)
            self.assertEqual(again.leader_chat_id, -1002)
            self.assertIsNone(again.announcement_message_id)

    async def test_topics_created_only_once_and_never_in_general(self):
        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001, general_chat_id=-1002)
        bot = AsyncMock()
        bot.get_chat.return_value = SimpleNamespace(is_forum=True)
        bot.get_me.return_value = SimpleNamespace(id=100, username='era_test')
        bot.get_chat_member.return_value = SimpleNamespace(can_manage_topics=True, can_pin_messages=True)
        bot.create_forum_topic.side_effect = [SimpleNamespace(message_thread_id=x) for x in (2,3,4)]
        bot.send_message.return_value = SimpleNamespace(message_id=5)
        self.assertEqual((await setup_leaders_topics(bot, settings, self.factory))['status'], 'ready')
        await setup_leaders_topics(bot, settings, self.factory)
        self.assertEqual(bot.create_forum_topic.await_count, 3)
        self.assertEqual(bot.send_message.await_count, 3)
        settings.leaders_chat_id = settings.general_chat_id
        self.assertEqual((await setup_leaders_topics(bot, settings, self.factory))['status'], 'not_configured')

    async def test_group_task_never_falls_back_to_an_unrelated_forum_thread(self):
        from app.database.models import User
        from app.handlers.leader_chat_workcenter import begin_group_task
        from app.utils.constants import ApplicationStatus, Role

        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001, general_chat_id=-1002, admin_ids=[1001])
        async with self.factory() as session:
            admin = User(telegram_id=1001, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            session.add(admin)
            await session.flush()
            state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
            message = SimpleNamespace(
                chat=SimpleNamespace(id=-1001),
                from_user=SimpleNamespace(id=1001),
                reply_to_message=SimpleNamespace(text='Prepare the report', caption=None, message_id=17),
                message_thread_id=999,
                reply=AsyncMock(),
            )
            await begin_group_task(message, state, admin, settings, session)
            state.update_data.assert_not_awaited()
            self.assertIn('не настроена', message.reply.await_args.args[0])

            from app.database.models import AppSetting
            session.add(AppSetting(key='leaders_forum:-1001:tasks', value='{"thread_id":7}'))
            await session.flush()
            await begin_group_task(message, state, admin, settings, session)
            self.assertEqual(state.update_data.await_args.kwargs['task_thread_id'], 7)

    async def test_revoked_assignee_cannot_be_selected_or_confirmed(self):
        from app.database.models import User, AppSetting, Task
        from app.handlers.leader_chat_workcenter import choose_group_task_assignee, finish_group_task
        from app.states.task import LeadersChatTaskStates
        from app.utils.constants import ApplicationStatus, Role
        from sqlalchemy import func, select

        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001, general_chat_id=-1002, admin_ids=[1001])
        async with self.factory() as session:
            admin = User(telegram_id=1001, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            revoked = User(telegram_id=1002, first_name='Revoked', application_status=ApplicationStatus.APPROVED, is_blocked=True)
            session.add_all([admin, revoked])
            session.add(AppSetting(key='leaders_forum:-1001:tasks', value='{"thread_id":7}'))
            await session.flush()

            state = SimpleNamespace(
                get_state=AsyncMock(return_value=LeadersChatTaskStates.assignee.state),
                get_data=AsyncMock(return_value={'task_creator_id': admin.id}),
                clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
            )
            call = SimpleNamespace(
                data=f'leaders_task:assign:{revoked.id}', answer=AsyncMock(),
                message=SimpleNamespace(chat=SimpleNamespace(id=-1001), answer=AsyncMock()),
            )
            await choose_group_task_assignee(call, state, session, settings, admin, SimpleNamespace(id=1001))
            state.update_data.assert_not_awaited()
            self.assertIn('недоступен', call.message.answer.await_args.args[0])

            # A previously selected user may lose approval before the deadline step.
            state.get_data.return_value = {
                'task_creator_id': admin.id, 'task_assignee_id': revoked.id,
                'task_title': 'Report', 'task_description': 'Prepare report',
                'task_chat_id': -1001, 'task_thread_id': 7,
            }
            message = SimpleNamespace(
                chat=SimpleNamespace(id=-1001), from_user=SimpleNamespace(id=1001),
                text='30.12.2027 18:00', reply=AsyncMock(),
            )
            bot = AsyncMock()
            await finish_group_task(message, state, session, settings, admin, bot)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Task)), 0)
            bot.send_message.assert_not_awaited()
            self.assertIn('недоступен', message.reply.await_args.args[0])

    async def test_revoked_assignee_cannot_use_old_task_card_actions(self):
        from app.handlers.leader_chat_workcenter import handle_leaders_task_card_action
        from app.utils.constants import ApplicationStatus, TaskStatus

        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001)
        revoked = SimpleNamespace(
            id=7, telegram_id=1002, application_status=ApplicationStatus.APPROVED,
            is_archived=False, is_blocked=True,
        )
        task = SimpleNamespace(id=42, assignee_id=7, status=TaskStatus.NEW)
        state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
        message = SimpleNamespace(chat=SimpleNamespace(id=-1001), reply=AsyncMock())
        with patch(
            'app.handlers.leader_chat_workcenter._card_task',
            new=AsyncMock(return_value=task),
        ):
            for action in ('start', 'submit', 'block'):
                call = SimpleNamespace(
                    data=f'leaders_task:{action}:42', message=message, answer=AsyncMock(),
                )
                await handle_leaders_task_card_action(
                    call, state, AsyncMock(), settings, revoked,
                    SimpleNamespace(id=1002), AsyncMock(),
                )
                self.assertTrue(call.answer.await_args.kwargs.get('show_alert'))
        self.assertEqual(task.status, TaskStatus.NEW)
        state.clear.assert_not_awaited()
        message.reply.assert_not_awaited()

    async def test_revoked_assignee_cannot_submit_result_or_blocker(self):
        from app.handlers.leader_chat_workcenter import (
            save_leaders_task_result, save_leaders_task_blocker,
        )
        from app.utils.constants import ApplicationStatus, TaskStatus

        settings = Settings(bot_token='1234567890:test-token', leaders_chat_id=-1001)
        revoked = SimpleNamespace(
            id=7, telegram_id=1002, application_status=ApplicationStatus.APPROVED,
            is_archived=False, is_blocked=True,
        )
        task = SimpleNamespace(id=42, assignee_id=7, status=TaskStatus.NEW, comment='')
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={
                'leaders_task_id': 42, 'leaders_task_chat_id': -1001,
            }),
            clear=AsyncMock(),
        )
        session = AsyncMock()
        session.get.return_value = task
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-1001), text='Result or blocker',
            caption=None, reply=AsyncMock(),
        )
        await save_leaders_task_result(message, state, session, settings, revoked)
        await save_leaders_task_blocker(message, state, session, settings, revoked)
        self.assertEqual(task.status, TaskStatus.NEW)
        self.assertEqual(task.comment, '')
        session.scalar.assert_not_awaited()
        session.add.assert_not_called()
        self.assertEqual(state.clear.await_count, 2)
