from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from aiogram.types import Chat, Message, User

from app.handlers.participant.questions import my_questions, router
from app.states.question import QuestionStates


class SupportCommandPriorityTests(IsolatedAsyncioTestCase):
    async def test_history_command_and_button_work_during_every_question_form(self):
        for state in (QuestionStates.category, QuestionStates.text, QuestionStates.attachment_choice,
                      QuestionStates.attachment, QuestionStates.followup):
            for text in ('/my_questions', '💬 Мои обращения'):
                with self.subTest(state=state.state, text=text):
                    message = Message(message_id=1, date=datetime.now(timezone.utc),
                        chat=Chat(id=22, type='private'), from_user=User(id=22, first_name='Member', is_bot=False),
                        text=text)
                    matched = None
                    for handler in router.message.handlers:
                        allowed, _ = await handler.check(message, raw_state=state.state, bot=SimpleNamespace())
                        if allowed:
                            matched = handler.callback
                            break
                    self.assertIs(matched, my_questions)
