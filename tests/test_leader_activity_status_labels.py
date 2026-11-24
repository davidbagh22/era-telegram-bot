"""Leader activity review cards must never show raw English status enums."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.handlers.leader.event_activities_block7 import send_card


class LeaderActivityStatusLabelTests(IsolatedAsyncioTestCase):
    async def test_pending_card_uses_russian_status(self):
        call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()))
        sub = SimpleNamespace(
            id=9, activity_id=3, user_id=4, status="pending",
            text="готово", file_id=None, file_type=None,
        )
        activity = SimpleNamespace(title="Отзыв", points=15)
        target = SimpleNamespace(first_name="Анна", last_name="Иванова")

        async def _get(model, key):
            if key == 3:
                return activity
            if key == 4:
                return target
            return None

        session = SimpleNamespace(get=AsyncMock(side_effect=_get))
        await send_card(call, session, sub)
        text = call.message.answer.await_args.args[0]
        self.assertIn("на проверке", text)
        self.assertNotIn("pending", text)
        self.assertNotIn("#9", text)
