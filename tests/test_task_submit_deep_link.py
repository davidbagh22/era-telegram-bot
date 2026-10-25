from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from app.handlers.emergency import _try_start_task_submission_from_deep_link
from app.states.growth import TaskSubmissionStates
from app.utils.deep_links import (
    miniapp_admin_project_url,
    miniapp_community_url,
    miniapp_path_url,
    miniapp_project_application_url,
    miniapp_project_url,
    miniapp_projects_url,
    parse_task_submit_payload,
    task_submit_deep_link,
)


class DeepLinkHelperTests(unittest.TestCase):
    def test_builds_expected_url(self) -> None:
        url = task_submit_deep_link("era_bot", 42)
        self.assertEqual(url, "https://t.me/era_bot?start=task_submit_42")

    def test_round_trip_parse(self) -> None:
        self.assertEqual(parse_task_submit_payload("task_submit_42"), 42)

    def test_unrelated_payload_returns_none(self) -> None:
        self.assertIsNone(parse_task_submit_payload("some_other_payload"))

    def test_malformed_id_returns_none(self) -> None:
        self.assertIsNone(parse_task_submit_payload("task_submit_abc"))

    def assertEraPath(self, url: str, expected: str) -> None:
        parsed = urlsplit(url)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), [expected])

    def test_miniapp_project_deep_links_use_telegram_safe_query_routes(self) -> None:
        base_url = "https://era.example/app/"
        self.assertEraPath(miniapp_project_url(base_url, 7), "projects/7")
        self.assertEraPath(
            miniapp_project_application_url(base_url, 7, 15),
            "projects/7/team/applications/15",
        )
        self.assertEraPath(miniapp_admin_project_url(base_url, 7), "admin/projects/7")

    def test_miniapp_path_url_preserves_additional_query_params(self) -> None:
        url = miniapp_path_url(
            "https://era.example/app?devTelegramId=42",
            "projects/7/tasks/3",
            {"tab": "tasks"},
        )
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(query["eraPath"], ["projects/7/tasks/3"])
        self.assertEqual(query["tab"], ["tasks"])
        self.assertEqual(query["devTelegramId"], ["42"])

    def test_miniapp_top_level_deep_links_use_telegram_safe_query_routes(self) -> None:
        self.assertEraPath(miniapp_projects_url("https://era.example/app"), "projects")
        self.assertEraPath(miniapp_community_url("https://era.example/app"), "community")


class TrySubmissionHandoffTests(unittest.IsolatedAsyncioTestCase):
    def _message(self) -> SimpleNamespace:
        return SimpleNamespace(answer=AsyncMock())

    def _state(self) -> SimpleNamespace:
        return SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    async def test_no_command_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        session = SimpleNamespace(get=AsyncMock())
        result = await _try_start_task_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, None
        )
        self.assertFalse(result)
        message.answer.assert_not_awaited()

    async def test_unrelated_payload_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        session = SimpleNamespace(get=AsyncMock())
        command = SimpleNamespace(args="something_else")
        result = await _try_start_task_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, command
        )
        self.assertFalse(result)

    async def test_task_not_found_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        command = SimpleNamespace(args="task_submit_99")
        result = await _try_start_task_submission_from_deep_link(
            message, SimpleNamespace(id=1), state, session, command
        )
        self.assertFalse(result)

    async def test_valid_task_starts_submission_fsm(self) -> None:
        message = self._message()
        state = self._state()
        task = SimpleNamespace(id=7, title="Собрать отчёт", status="in_progress", assignee_id=1)
        session = SimpleNamespace(get=AsyncMock(return_value=task))
        command = SimpleNamespace(args="task_submit_7")
        user = SimpleNamespace(id=1)

        result = await _try_start_task_submission_from_deep_link(
            message, user, state, session, command
        )

        self.assertTrue(result)
        state.set_state.assert_awaited_once_with(TaskSubmissionStates.result)
        state.update_data.assert_awaited_once_with(task_id=7)
        message.answer.assert_awaited_once()

    async def test_task_user_cannot_submit_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        # assignee_id differs and no TaskParticipant membership -> can_submit is False
        task = SimpleNamespace(id=7, title="Собрать отчёт", status="in_progress", assignee_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=task), scalar=AsyncMock(return_value=None))
        command = SimpleNamespace(args="task_submit_7")
        user = SimpleNamespace(id=1)

        result = await _try_start_task_submission_from_deep_link(
            message, user, state, session, command
        )

        self.assertFalse(result)
        state.set_state.assert_not_awaited()

    async def test_archived_task_returns_false(self) -> None:
        message = self._message()
        state = self._state()
        task = SimpleNamespace(id=7, title="Собрать отчёт", status="completed", assignee_id=1)
        session = SimpleNamespace(get=AsyncMock(return_value=task))
        command = SimpleNamespace(args="task_submit_7")
        user = SimpleNamespace(id=1)

        result = await _try_start_task_submission_from_deep_link(
            message, user, state, session, command
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
