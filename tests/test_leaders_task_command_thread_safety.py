"""A /task reply must originate from the configured Leaders Tasks destination."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.handlers.leader_chat_workcenter import begin_group_task


class LeadersTaskCommandThreadSafetyTests(IsolatedAsyncioTestCase):
    async def invoke(self, configured_thread, command_thread, source_thread):
        source = SimpleNamespace(
            text="Подготовить отчёт", caption=None, message_id=101,
            message_thread_id=source_thread,
        )
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-1001),
            from_user=SimpleNamespace(id=123),
            reply_to_message=source,
            message_thread_id=command_thread,
            reply=AsyncMock(),
        )
        state = SimpleNamespace(
            clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
        )
        user = SimpleNamespace(id=77, telegram_id=123)
        settings = SimpleNamespace(leaders_chat_id=-1001)
        with (
            patch("app.handlers.leader_chat_workcenter._can_create", return_value=True),
            patch("app.handlers.leader_chat_workcenter.delivery_topic",
                  new_callable=AsyncMock, return_value=configured_thread) as route,
        ):
            await begin_group_task(message, state, user, settings, None)
            route.assert_awaited_once_with(None, -1001, "tasks")
        return message, state

    async def test_correct_forum_thread_creates_task_draft(self):
        message, state = await self.invoke(41, 41, 41)
        state.clear.assert_awaited_once()
        state.set_state.assert_awaited_once()
        self.assertEqual(state.update_data.await_args.kwargs["task_thread_id"], 41)
        message.reply.assert_awaited_once()

    async def test_command_in_pulse_thread_cannot_create_task(self):
        message, state = await self.invoke(41, 42, 42)
        state.clear.assert_not_awaited()
        state.update_data.assert_not_awaited()
        state.set_state.assert_not_awaited()
        self.assertIn("теме «Задачи»", message.reply.await_args.args[0])

    async def test_reply_to_other_thread_cannot_create_task(self):
        message, state = await self.invoke(41, 41, 43)
        state.clear.assert_not_awaited()
        state.update_data.assert_not_awaited()
        state.set_state.assert_not_awaited()
        self.assertIn("теме «Задачи»", message.reply.await_args.args[0])

    async def test_plain_chat_accepts_only_unthreaded_messages(self):
        good_message, good_state = await self.invoke(None, None, None)
        good_state.set_state.assert_awaited_once()
        self.assertIsNone(good_state.update_data.await_args.kwargs["task_thread_id"])
        bad_message, bad_state = await self.invoke(None, 8, 8)
        bad_state.set_state.assert_not_awaited()
        self.assertIn("теме «Задачи»", bad_message.reply.await_args.args[0])
