from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers import chat_faq
from app.services.chat_faq_service import FAQ_ANSWERS
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus


def _approved_user(telegram_id: int = 777) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_id=telegram_id, application_status=ApplicationStatus.APPROVED, is_blocked=False
    )


def _blocked_user(telegram_id: int = 777) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_id=telegram_id, application_status=ApplicationStatus.APPROVED, is_blocked=True
    )


def _group_state(bot_id: int = 1, group_chat_id: int = -100, user_id: int = 777) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot_id, chat_id=group_chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


class ChatFaqHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_faq_answer_sends_canned_html_text_to_dm(self) -> None:
        call = SimpleNamespace(data="faq:what_is_era", answer=AsyncMock())
        user = _approved_user()
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=True)) as safe_send:
            await chat_faq.faq_answer(call, user, bot=SimpleNamespace(id=1))
        safe_send.assert_awaited_once()
        args, kwargs = safe_send.call_args
        self.assertEqual(args[1], user.telegram_id)
        self.assertEqual(args[2], FAQ_ANSWERS["faq:what_is_era"])
        self.assertEqual(kwargs["parse_mode"], "HTML")
        call.answer.assert_awaited_once()
        self.assertNotIn("show_alert", call.answer.call_args.kwargs)

    async def test_faq_answer_alerts_on_send_failure(self) -> None:
        call = SimpleNamespace(data="faq:what_it_gives", answer=AsyncMock())
        user = _approved_user()
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=False)):
            await chat_faq.faq_answer(call, user, bot=SimpleNamespace(id=1))
        (text,), kwargs = call.answer.call_args
        self.assertEqual(text, texts.FAQ_ANSWER_SEND_FAILED)
        self.assertTrue(kwargs["show_alert"])

    async def test_faq_answer_blocks_unapproved_user(self) -> None:
        call = SimpleNamespace(data="faq:what_can_i_do", answer=AsyncMock())
        with patch.object(chat_faq, "safe_send", AsyncMock()) as safe_send:
            await chat_faq.faq_answer(call, None, bot=SimpleNamespace(id=1))
        safe_send.assert_not_awaited()
        (text,), kwargs = call.answer.call_args
        self.assertEqual(text, texts.APPLICATION_PENDING)
        self.assertTrue(kwargs["show_alert"])

    async def test_faq_answer_blocks_blocked_user(self) -> None:
        call = SimpleNamespace(data="faq:what_to_do", answer=AsyncMock())
        with patch.object(chat_faq, "safe_send", AsyncMock()) as safe_send:
            await chat_faq.faq_answer(call, _blocked_user(), bot=SimpleNamespace(id=1))
        safe_send.assert_not_awaited()

    async def test_faq_contact_sends_question_start_and_arms_dm_state(self) -> None:
        call = SimpleNamespace(data="faq:contact", answer=AsyncMock())
        user = _approved_user(telegram_id=999)
        state = _group_state(bot_id=1, group_chat_id=-100, user_id=999)
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=True)) as safe_send:
            await chat_faq.faq_contact(call, user, bot=SimpleNamespace(id=1), state=state)
        safe_send.assert_awaited_once()
        args, _ = safe_send.call_args
        self.assertEqual(args[1], user.telegram_id)
        self.assertEqual(args[2], texts.QUESTION_START)

        # The reply lands in the user's *private* chat, not the group this
        # callback fired in -- state must be armed on that private key.
        private_key = StorageKey(bot_id=1, chat_id=user.telegram_id, user_id=user.telegram_id)
        private_state = FSMContext(storage=state.storage, key=private_key)
        current = await private_state.get_state()
        self.assertEqual(current, QuestionStates.text.state)

        # And the group-chat-scoped state itself must stay untouched.
        self.assertIsNone(await state.get_state())

    async def test_faq_contact_does_not_arm_state_when_send_fails(self) -> None:
        call = SimpleNamespace(data="faq:contact", answer=AsyncMock())
        user = _approved_user(telegram_id=888)
        state = _group_state(bot_id=1, group_chat_id=-100, user_id=888)
        with patch.object(chat_faq, "safe_send", AsyncMock(return_value=False)):
            await chat_faq.faq_contact(call, user, bot=SimpleNamespace(id=1), state=state)
        private_key = StorageKey(bot_id=1, chat_id=user.telegram_id, user_id=user.telegram_id)
        private_state = FSMContext(storage=state.storage, key=private_key)
        self.assertIsNone(await private_state.get_state())
        (text,), kwargs = call.answer.call_args
        self.assertEqual(text, texts.FAQ_ANSWER_SEND_FAILED)
        self.assertTrue(kwargs["show_alert"])


if __name__ == "__main__":
    unittest.main()
