from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from app.handlers.leader_chat_workcenter import team_tasks_shortcut


class TeamTasksShortcutTests(IsolatedAsyncioTestCase):
    async def test_authorized_entry_opens_team_tasks_directly(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())
        settings = SimpleNamespace(effective_miniapp_url="https://example.org/app/")
        with patch("app.handlers.leader_chat_workcenter._can_create", return_value=True):
            await team_tasks_shortcut(message, object(), settings)
        button = message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        query = parse_qs(urlsplit(button.web_app.url).query)
        self.assertEqual(query["adminSection"], ["team-tasks"])
        self.assertIn("admin", next(value[0] for key, value in query.items() if key != "adminSection"))

    async def test_denied_entry_exposes_no_management_button(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())
        with patch("app.handlers.leader_chat_workcenter._can_create", return_value=False):
            await team_tasks_shortcut(message, None, SimpleNamespace())
        self.assertNotIn("reply_markup", message.answer.await_args.kwargs)

    async def test_missing_miniapp_keeps_native_task_instructions(self):
        message = SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())
        with patch("app.handlers.leader_chat_workcenter._can_create", return_value=True):
            await team_tasks_shortcut(message, object(), SimpleNamespace(effective_miniapp_url=""))
        self.assertIn("/task", message.answer.await_args.args[0])
