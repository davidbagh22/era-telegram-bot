from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.emergency import _try_start_activity_submission_from_deep_link
from app.handlers.participant.event_activities_block15 import ActivityProofStates
from app.utils.deep_links import activity_submit_deep_link, parse_activity_submit_payload


class ActivitySubmitDeepLinkHelperTests(unittest.TestCase):
    def test_builds_expected_url(self) -> None:
        url = activity_submit_deep_link("era_bot", 42)
        self.assertEqual(url, "https://t.me/era_bot?start=activity_submit_42")

    def test_round_trip_parse(self) -> None:
        self.assertEqual(parse_activity_submit_payload("activity_submit_42"), 42)

    def test_unrelated_payload_returns_none(self) -> None:
        self.assertIsNone(parse_activity_submit_payload("some_other_payload"))

    def test_malformed_id_returns_none(self) -> None:
        self.assertIsNone(parse_activity_submit_payload("activity_submit_abc"))


class TryActivitySubmissionHandoffTests(unittest.IsolatedAsyncioTestCase):
    def _message(self) -> SimpleNamespace:
        return SimpleNamespace(answer=AsyncMock())

    def _state(self) -> SimpleNamespace:
        return SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    async def test_no_command_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        session = SimpleNamespace(get=AsyncMock())
        result = await _try_start_activity_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), None
        )
        self.assertFalse(result)
        message.answer.assert_not_awaited()

    async def test_unrelated_payload_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        session = SimpleNamespace(get=AsyncMock())
        command = SimpleNamespace(args="something_else")
        result = await _try_start_activity_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
        )
        self.assertFalse(result)

    async def test_inactive_activity_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(id=7, is_active=False)
        session = SimpleNamespace(get=AsyncMock(return_value=activity))
        command = SimpleNamespace(args="activity_submit_7")
        result = await _try_start_activity_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
        )
        self.assertFalse(result)

    async def test_not_registered_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(id=7, is_active=True, event_id=3)
        session = SimpleNamespace(get=AsyncMock(return_value=activity), scalar=AsyncMock(return_value=None))
        command = SimpleNamespace(args="activity_submit_7")
        result = await _try_start_activity_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
        )
        self.assertFalse(result)
        state.set_state.assert_not_awaited()

    async def test_text_proof_type_starts_fsm(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(
            id=7, is_active=True, event_id=3, submission_type="text", title="Отзыв", description="d", points=10
        )
        registration = SimpleNamespace()
        session = SimpleNamespace(get=AsyncMock(return_value=activity), scalar=AsyncMock(return_value=registration))
        command = SimpleNamespace(args="activity_submit_7")
        with patch(
            "app.handlers.emergency.event_activity_service.get_submission", new=AsyncMock(return_value=None)
        ):
            result = await _try_start_activity_submission_from_deep_link(
                message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
            )
        self.assertTrue(result)
        state.set_state.assert_awaited_once_with(ActivityProofStates.proof)
        state.update_data.assert_awaited_once_with(activity_id=7, proof_type="text")
        message.answer.assert_awaited_once()

    async def test_manual_proof_type_submits_immediately(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(
            id=7, is_active=True, event_id=3, submission_type="manual", title="Помощь", description="d", points=10
        )
        registration = SimpleNamespace()
        event = SimpleNamespace(title="Событие")
        submission = SimpleNamespace(id=1)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[activity, event]), scalar=AsyncMock(return_value=registration)
        )
        command = SimpleNamespace(args="activity_submit_7")
        with (
            patch(
                "app.handlers.emergency.event_activity_service.get_submission", new=AsyncMock(return_value=None)
            ),
            patch(
                "app.handlers.emergency.event_activity_service.submit_manual",
                new=AsyncMock(return_value=submission),
            ),
            patch("app.handlers.emergency.notify_activity_proof", new=AsyncMock()) as notify_mock,
        ):
            result = await _try_start_activity_submission_from_deep_link(
                message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
            )
        self.assertTrue(result)
        state.set_state.assert_not_awaited()
        notify_mock.assert_awaited_once()
        message.answer.assert_awaited_once()

    async def test_already_pending_returns_true_without_starting_fsm(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(id=7, is_active=True, event_id=3, submission_type="text")
        registration = SimpleNamespace()
        existing = SimpleNamespace(status="pending")
        session = SimpleNamespace(get=AsyncMock(return_value=activity), scalar=AsyncMock(return_value=registration))
        command = SimpleNamespace(args="activity_submit_7")
        with patch(
            "app.handlers.emergency.event_activity_service.get_submission", new=AsyncMock(return_value=existing)
        ):
            result = await _try_start_activity_submission_from_deep_link(
                message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
            )
        self.assertTrue(result)
        state.set_state.assert_not_awaited()
        message.answer.assert_awaited_once()

    async def test_already_approved_returns_true_without_starting_fsm(self) -> None:
        message = self._message()
        state = self._state()
        activity = SimpleNamespace(id=7, is_active=True, event_id=3, submission_type="text")
        registration = SimpleNamespace()
        existing = SimpleNamespace(status="approved")
        session = SimpleNamespace(get=AsyncMock(return_value=activity), scalar=AsyncMock(return_value=registration))
        command = SimpleNamespace(args="activity_submit_7")
        with patch(
            "app.handlers.emergency.event_activity_service.get_submission", new=AsyncMock(return_value=existing)
        ):
            result = await _try_start_activity_submission_from_deep_link(
                message, SimpleNamespace(id=1), state, session, SimpleNamespace(), SimpleNamespace(), command
            )
        self.assertTrue(result)
        state.set_state.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
