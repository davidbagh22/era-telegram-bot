"""Feedback requires an approved attendance proof for the target event.

Grounded in the product path: the feedback CTA is issued only after proof
approval. Forged callback event ids must not open or write feedback.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import IntegrityError

from app.handlers.participant import events as events_mod
from app.handlers.participant.events import feedback_finish, feedback_start
from app.states.event import FeedbackStates
from app.utils.constants import ApplicationStatus


def _approved_user(*, user_id: int = 7):
    return SimpleNamespace(
        id=user_id,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
    )


def _session_with_proof(proof_id: int | None):
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=proof_id)
    session.begin_nested = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(),
        __aexit__=AsyncMock(return_value=None),
    ))
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class FeedbackAttendanceEligibilityTests(IsolatedAsyncioTestCase):
    async def test_start_rejects_missing_approved_proof(self):
        call = SimpleNamespace(
            data="feedback:start:42",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            set_state=AsyncMock(),
            update_data=AsyncMock(),
            clear=AsyncMock(),
        )
        session = _session_with_proof(None)
        await feedback_start(call, state, session, _approved_user())
        call.answer.assert_awaited_once()
        state.clear.assert_awaited_once()
        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()
        call.message.answer.assert_awaited_once()
        self.assertIn("подтверждённого участия", call.message.answer.await_args.args[0])

    async def test_start_opens_wizard_when_proof_approved(self):
        call = SimpleNamespace(
            data="feedback:start:42",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            set_state=AsyncMock(),
            update_data=AsyncMock(),
            clear=AsyncMock(),
        )
        session = _session_with_proof(99)
        await feedback_start(call, state, session, _approved_user())
        state.set_state.assert_awaited_once_with(FeedbackStates.rating)
        state.update_data.assert_awaited_once_with(feedback_event_id=42)
        call.message.answer.assert_awaited_once()
        state.clear.assert_not_awaited()

    async def test_finish_rejects_without_approved_proof(self):
        call = SimpleNamespace(
            data="feedback:again:yes",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "feedback_event_id": 42,
                    "rating": 5,
                    "liked": "Хорошо",
                    "improve": "Больше времени",
                }
            ),
            clear=AsyncMock(),
        )
        session = _session_with_proof(None)
        await feedback_finish(call, state, session, _approved_user())
        state.clear.assert_awaited_once()
        session.add.assert_not_called()
        call.message.answer.assert_awaited_once()
        self.assertIn("подтверждённого участия", call.message.answer.await_args.args[0])

    async def test_finish_writes_when_proof_approved(self):
        call = SimpleNamespace(
            data="feedback:again:yes",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "feedback_event_id": 42,
                    "rating": 4,
                    "liked": "Атмосфера",
                    "improve": "Звук",
                }
            ),
            clear=AsyncMock(),
        )
        # First scalar = proof check; second = existing Feedback lookup.
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[101, None])
        nested = AsyncMock()
        nested.__aenter__ = AsyncMock(return_value=None)
        nested.__aexit__ = AsyncMock(return_value=None)
        session.begin_nested = MagicMock(return_value=nested)
        session.add = MagicMock()
        session.flush = AsyncMock()
        await feedback_finish(call, state, session, _approved_user())
        session.add.assert_called_once()
        state.clear.assert_awaited_once()
        call.message.answer.assert_awaited_once_with(events_mod.texts.FEEDBACK_DONE)

    async def test_finish_recovers_unique_race_via_update(self):
        call = SimpleNamespace(
            data="feedback:again:no",
            answer=AsyncMock(),
            message=SimpleNamespace(answer=AsyncMock()),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "feedback_event_id": 42,
                    "rating": 3,
                    "liked": "Тема",
                    "improve": "Формат",
                }
            ),
            clear=AsyncMock(),
        )
        raced = SimpleNamespace(rating=1, liked="old", improve="old", wants_again="yes")
        session = AsyncMock()
        # proof ok, no existing, then raced row after IntegrityError
        session.scalar = AsyncMock(side_effect=[101, None, raced])
        nested = AsyncMock()
        nested.__aenter__ = AsyncMock(return_value=None)
        nested.__aexit__ = AsyncMock(return_value=None)
        session.begin_nested = MagicMock(return_value=nested)
        session.add = MagicMock()
        session.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))
        await feedback_finish(call, state, session, _approved_user())
        self.assertEqual(raced.rating, 3)
        self.assertEqual(raced.liked, "Тема")
        self.assertEqual(raced.improve, "Формат")
        self.assertEqual(raced.wants_again, "no")
        state.clear.assert_awaited_once()
        call.message.answer.assert_awaited_once_with(events_mod.texts.FEEDBACK_DONE)
