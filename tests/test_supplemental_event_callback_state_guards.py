"""Bound untrusted supplemental event callbacks and recovered FSM state.

Mock-only: no production PostgreSQL, Telegram calls, registrations or points.
"""
from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.models import Feedback
from app.handlers.participant.events import (
    attendance_confirmation,
    feedback_finish,
    feedback_start,
    selfie_not_photo,
    selfie_photo,
    selfie_start,
)
from app.states.event import FeedbackStates, SelfieStates
from app.utils.constants import ApplicationStatus, RegistrationStatus


def _call(data):
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )


def _state(data=None):
    return SimpleNamespace(
        get_data=AsyncMock(return_value=data or {}),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
        clear=AsyncMock(),
    )


def _approved_user():
    return SimpleNamespace(
        id=1,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
    )


class SupplementalEventCallbackGuards(IsolatedAsyncioTestCase):
    async def test_attendance_invalid_id_does_not_query_or_change_status(self):
        for raw in ("", "0", "-1", "2147483648", "９", "9" * 5000, "bad"):
            with self.subTest(raw=raw[:24]):
                call = _call(f"attendance:{raw}:yes")
                session = SimpleNamespace(scalar=AsyncMock())
                with patch("app.handlers.participant.events._approved", return_value=True):
                    await attendance_confirmation(call, SimpleNamespace(id=1), session)
                session.scalar.assert_not_awaited()
                call.answer.assert_awaited_once()

    async def test_attendance_wrong_namespace_or_answer_never_queries(self):
        for payload in ("other:42:yes", "attendance:42:maybe",
                        "attendance:42:yes:extra"):
            call = _call(payload)
            session = SimpleNamespace(scalar=AsyncMock())
            with patch("app.handlers.participant.events._approved", return_value=True):
                await attendance_confirmation(call, SimpleNamespace(id=1), session)
            session.scalar.assert_not_awaited()

    async def test_attendance_valid_id_preserves_confirmation(self):
        call = _call("attendance:00042:yes")
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        session = SimpleNamespace(scalar=AsyncMock(return_value=registration))
        with patch("app.handlers.participant.events._approved", return_value=True):
            await attendance_confirmation(call, SimpleNamespace(id=1), session)
        session.scalar.assert_awaited_once()
        self.assertEqual(registration.status, RegistrationStatus.WILL_COME)
        call.message.answer.assert_awaited_once()

    async def test_selfie_start_rejects_invalid_id_before_database_and_fsm(self):
        for raw in ("", "0", "-1", "2147483648", "９", "9" * 5000, "bad"):
            with self.subTest(raw=raw[:24]):
                call = _call("selfie:start:" + raw)
                session = SimpleNamespace(get=AsyncMock(), scalar=AsyncMock())
                state = _state()
                with patch("app.handlers.participant.events._approved", return_value=True):
                    await selfie_start(call, SimpleNamespace(id=1), session, state)
                session.get.assert_not_awaited()
                session.scalar.assert_not_awaited()
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_selfie_start_valid_id_preserves_fsm_transition(self):
        call = _call("selfie:start:42")
        session = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(event_date=date.today())),
            scalar=AsyncMock(return_value=SimpleNamespace()),
        )
        state = _state()
        with patch("app.handlers.participant.events._approved", return_value=True):
            await selfie_start(call, SimpleNamespace(id=1), session, state)
        session.get.assert_awaited_once()
        state.set_state.assert_awaited_once_with(SelfieStates.photo)
        state.update_data.assert_awaited_once_with(selfie_event_id=42)

    async def test_selfie_non_photo_clears_stale_fsm_for_inactive_user(self):
        cases = (
            None,
            SimpleNamespace(id=1, application_status=ApplicationStatus.PENDING,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.REJECTED,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=True, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=False, is_archived=True),
        )
        for user in cases:
            with self.subTest(user=str(user)):
                message = SimpleNamespace(answer=AsyncMock())
                state = _state({"selfie_event_id": 42})
                await selfie_not_photo(message, state, user)
                state.clear.assert_awaited_once()
                state.get_data.assert_not_awaited()
                state.update_data.assert_not_awaited()
                message.answer.assert_awaited_once()

    async def test_selfie_non_photo_approved_user_keeps_photo_prompt(self):
        message = SimpleNamespace(answer=AsyncMock())
        state = _state({"selfie_event_id": 42})
        await selfie_not_photo(message, state, _approved_user())
        state.clear.assert_not_awaited()
        state.get_data.assert_not_awaited()
        message.answer.assert_awaited_once_with("Отправьте фотографию как изображение.")

    async def test_selfie_photo_rechecks_approval_before_fsm_or_database(self):
        cases = (
            None,
            SimpleNamespace(id=1, application_status=ApplicationStatus.PENDING,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.REJECTED,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=True, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=False, is_archived=True),
        )
        for user in cases:
            with self.subTest(user=str(user)):
                message = SimpleNamespace(answer=AsyncMock())
                state = _state({"selfie_event_id": 42})
                session = SimpleNamespace(scalar=AsyncMock(), add=MagicMock(), flush=AsyncMock())
                with patch("app.handlers.participant.events.notify_admins", new_callable=AsyncMock) as notify:
                    await selfie_photo(message, state, session, user,
                                      SimpleNamespace(), SimpleNamespace())
                state.get_data.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                session.flush.assert_not_awaited()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()

    async def test_selfie_photo_approved_valid_state_preserves_submission(self):
        message = SimpleNamespace(
            photo=[SimpleNamespace(file_id="isolated-test-file")],
            answer=AsyncMock(),
        )
        state = _state({"selfie_event_id": 42})
        session = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(event_date=date.today())),
            scalar=AsyncMock(side_effect=[SimpleNamespace(), None]),
            add=MagicMock(),
            flush=AsyncMock(),
        )
        with patch("app.handlers.participant.events.notify_admins", new_callable=AsyncMock) as notify:
            await selfie_photo(message, state, session, _approved_user(),
                              SimpleNamespace(), SimpleNamespace())
        session.get.assert_awaited_once()
        self.assertEqual(session.scalar.await_count, 2)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        notify.assert_awaited_once()
        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()

    async def test_selfie_photo_rechecks_event_and_registration_before_writes(self):
        # Eligibility can change after selfie_start has already set the FSM.
        cases = (
            ("event_deleted", None, SimpleNamespace()),
            ("registration_missing", SimpleNamespace(event_date=date.today()), None),
            ("event_rescheduled", SimpleNamespace(event_date=date(2000, 1, 1)),
             SimpleNamespace()),
        )
        for label, event, registration in cases:
            with self.subTest(case=label):
                message = SimpleNamespace(
                    photo=[SimpleNamespace(file_id="isolated-test-file")],
                    answer=AsyncMock(),
                )
                state = _state({"selfie_event_id": 42})
                session = SimpleNamespace(
                    get=AsyncMock(return_value=event),
                    scalar=AsyncMock(return_value=registration),
                    add=MagicMock(),
                    flush=AsyncMock(),
                )
                with patch("app.handlers.participant.events.notify_admins",
                           new_callable=AsyncMock) as notify:
                    await selfie_photo(message, state, session, _approved_user(),
                                      SimpleNamespace(), SimpleNamespace())
                session.get.assert_awaited_once()
                session.scalar.assert_awaited_once()
                session.add.assert_not_called()
                session.flush.assert_not_awaited()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()

    async def test_selfie_photo_invalid_fsm_does_not_query_or_notify(self):
        for value in (None, True, -1, "bad", "2147483648", "９", "9" * 5000):
            with self.subTest(value=str(value)[:24]):
                message = SimpleNamespace(answer=AsyncMock())
                state = _state({"selfie_event_id": value})
                session = SimpleNamespace(scalar=AsyncMock(), add=MagicMock(), flush=AsyncMock())
                with patch("app.handlers.participant.events.notify_admins", new_callable=AsyncMock) as notify:
                    await selfie_photo(message, state, session, _approved_user(),
                                      SimpleNamespace(), SimpleNamespace())
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                session.flush.assert_not_awaited()
                notify.assert_not_awaited()
                state.clear.assert_awaited_once()
                message.answer.assert_awaited_once()

    async def test_feedback_start_denies_inactive_or_unapproved_user_before_fsm(self):
        cases = (
            None,
            SimpleNamespace(id=1, application_status=ApplicationStatus.PENDING,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=True, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=False, is_archived=True),
        )
        for user in cases:
            with self.subTest(user=str(user)):
                call = _call("feedback:start:42")
                state = _state()
                await feedback_start(call, state, user)
                call.answer.assert_awaited_once()
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_feedback_finish_denies_inactive_or_unapproved_before_database(self):
        cases = (
            None,
            SimpleNamespace(id=1, application_status=ApplicationStatus.REJECTED,
                            is_blocked=False, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=True, is_archived=False),
            SimpleNamespace(id=1, application_status=ApplicationStatus.APPROVED,
                            is_blocked=False, is_archived=True),
        )
        for user in cases:
            with self.subTest(user=str(user)):
                call = _call("feedback:again:yes")
                state = _state({"feedback_event_id": 42, "rating": 5,
                                "liked": "Хорошо", "improve": "Нет"})
                session = SimpleNamespace(scalar=AsyncMock(), add=MagicMock())
                await feedback_finish(call, state, session, user)
                call.answer.assert_awaited_once()
                state.get_data.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                state.clear.assert_awaited_once()
                call.message.answer.assert_awaited_once()

    async def test_feedback_start_rejects_invalid_callback_before_fsm(self):
        for raw in ("", "0", "-1", "2147483648", "９", "9" * 5000, "bad"):
            with self.subTest(raw=raw[:24]):
                call = _call("feedback:start:" + raw)
                state = _state()
                await feedback_start(call, state, _approved_user())
                state.set_state.assert_not_awaited()
                state.update_data.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_feedback_start_valid_callback_preserves_fsm(self):
        call = _call("feedback:start:42")
        state = _state()
        await feedback_start(call, state, _approved_user())
        state.set_state.assert_awaited_once_with(FeedbackStates.rating)
        state.update_data.assert_awaited_once_with(feedback_event_id=42)

    async def test_feedback_finish_rejects_forged_answer_before_database(self):
        for raw in ("", "feedback:again:maybe", "feedback:again:yes:extra",
                    "feedback:again:yes" + "9" * 5000):
            with self.subTest(raw=raw[:30]):
                call = _call(raw)
                state = _state({"feedback_event_id": 42, "rating": 5,
                                "liked": "Хорошо", "improve": "Нет"})
                session = SimpleNamespace(scalar=AsyncMock(), add=MagicMock())
                await feedback_finish(call, state, session, _approved_user())
                state.get_data.assert_not_awaited()
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                state.clear.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_feedback_finish_rejects_missing_or_corrupt_state(self):
        good = {"feedback_event_id": 42, "rating": 5,
                "liked": "Хорошо", "improve": "Нет"}
        broken = [
            {}, {**good, "feedback_event_id": None},
            {**good, "feedback_event_id": True},
            {**good, "feedback_event_id": "2147483648"},
            {**good, "rating": True}, {**good, "rating": 0},
            {**good, "rating": "5"}, {**good, "liked": ""},
            {**good, "liked": 123}, {**good, "improve": " "},
            {**good, "improve": "a" * 1001},
        ]
        for data in broken:
            with self.subTest(data=str(data)[:70]):
                call = _call("feedback:again:yes")
                state = _state(data)
                session = SimpleNamespace(scalar=AsyncMock(), add=MagicMock())
                await feedback_finish(call, state, session, _approved_user())
                session.scalar.assert_not_awaited()
                session.add.assert_not_called()
                state.clear.assert_awaited_once()
                call.message.answer.assert_awaited_once()

    async def test_feedback_finish_valid_state_preserves_submission(self):
        call = _call("feedback:again:unsure")
        state = _state({"feedback_event_id": "42", "rating": 5,
                        "liked": "Хорошо", "improve": "Нет"})
        session = SimpleNamespace(scalar=AsyncMock(return_value=None), add=MagicMock())
        await feedback_finish(call, state, session, _approved_user())
        session.scalar.assert_awaited_once()
        session.add.assert_called_once()
        feedback = session.add.call_args.args[0]
        self.assertIsInstance(feedback, Feedback)
        self.assertEqual((feedback.event_id, feedback.rating, feedback.wants_again),
                         (42, 5, "unsure"))
        state.clear.assert_awaited_once()
        call.message.answer.assert_awaited_once()
