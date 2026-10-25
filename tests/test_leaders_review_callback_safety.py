"""Reject stale Leaders review callbacks before touching submissions or FSM state."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.handlers.leader_chat_workcenter import handle_leaders_task_card_action
from app.utils.constants import TaskStatus


class LeadersReviewCallbackSafetyTests(IsolatedAsyncioTestCase):
    async def test_closed_or_unsubmitted_task_cannot_be_approved_or_returned(self):
        for status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS):
            for action in ("accept", "return"):
                with self.subTest(status=status, action=action):
                    task = SimpleNamespace(id=9, status=status, assignee_id=2)
                    call = SimpleNamespace(
                        data=f"leaders_task:{action}:9",
                        message=SimpleNamespace(chat=SimpleNamespace(id=-1001), reply=AsyncMock()),
                        answer=AsyncMock(),
                    )
                    state = SimpleNamespace(
                        clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
                    )
                    session = SimpleNamespace(scalar=AsyncMock(), get=AsyncMock())
                    bot = SimpleNamespace(send_message=AsyncMock())
                    with patch(
                        "app.handlers.leader_chat_workcenter._card_task",
                        new=AsyncMock(return_value=task),
                    ):
                        await handle_leaders_task_card_action(
                            call, state, session,
                            SimpleNamespace(leaders_chat_id=-1001),
                            SimpleNamespace(id=3),
                            SimpleNamespace(id=3), bot,
                        )
                    self.assertIn("не ожидает проверки", call.answer.await_args.args[0])
                    self.assertTrue(call.answer.await_args.kwargs["show_alert"])
                    state.clear.assert_not_awaited()
                    state.update_data.assert_not_awaited()
                    session.scalar.assert_not_awaited()
                    session.get.assert_not_awaited()
                    bot.send_message.assert_not_awaited()

    async def test_review_task_still_opens_return_comment_form(self):
        task = SimpleNamespace(id=9, status=TaskStatus.REVIEW, assignee_id=2)
        call = SimpleNamespace(
            data="leaders_task:return:9",
            message=SimpleNamespace(chat=SimpleNamespace(id=-1001), reply=AsyncMock()),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock(),
        )
        with (
            patch(
                "app.handlers.leader_chat_workcenter._card_task",
                new=AsyncMock(return_value=task),
            ),
            patch("app.handlers.leader_chat_workcenter._can_create", return_value=True),
        ):
            await handle_leaders_task_card_action(
                call, state, SimpleNamespace(),
                SimpleNamespace(leaders_chat_id=-1001),
                SimpleNamespace(id=3), SimpleNamespace(id=3),
                SimpleNamespace(send_message=AsyncMock()),
            )
        state.set_state.assert_awaited_once()
        state.update_data.assert_awaited_once_with(
            leaders_task_id=9, leaders_task_chat_id=-1001,
        )
        self.assertIn("комментарий", call.message.reply.await_args.args[0])
