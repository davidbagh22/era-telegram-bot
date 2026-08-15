from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.handlers.emergency import _try_faq_deep_link
from app.services.chat_faq_service import FAQ_ANSWERS
from app.states.question import QuestionStates
from app.utils.constants import ApplicationStatus


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append((text, kwargs))


class FakeState:
    def __init__(self) -> None:
        self.state = None

    async def set_state(self, state) -> None:
        self.state = state


class FaqPrivateDeepLinkTests(unittest.IsolatedAsyncioTestCase):
    def _user(self):
        return SimpleNamespace(
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
        )

    async def test_answer_payload_sends_requested_answer_in_private_chat(self) -> None:
        message = FakeMessage()
        state = FakeState()
        handled = await _try_faq_deep_link(
            message,
            self._user(),
            state,
            SimpleNamespace(args="faq_what_is_era"),
        )
        self.assertTrue(handled)
        self.assertEqual(message.answers[0][0], FAQ_ANSWERS["faq:what_is_era"])
        self.assertEqual(message.answers[0][1].get("parse_mode"), "HTML")

    async def test_contact_payload_arms_question_state(self) -> None:
        message = FakeMessage()
        state = FakeState()
        handled = await _try_faq_deep_link(
            message,
            self._user(),
            state,
            SimpleNamespace(args="faq_contact"),
        )
        self.assertTrue(handled)
        self.assertEqual(state.state, QuestionStates.text)
        self.assertTrue(message.answers)

    async def test_unrelated_start_payload_falls_through(self) -> None:
        message = FakeMessage()
        state = FakeState()
        handled = await _try_faq_deep_link(
            message,
            self._user(),
            state,
            SimpleNamespace(args="registration"),
        )
        self.assertFalse(handled)
        self.assertEqual(message.answers, [])


if __name__ == "__main__":
    unittest.main()
