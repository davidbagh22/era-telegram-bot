"""Welcome routing must use chat_key_for_id so media/leaders aren't general."""

from __future__ import annotations

import inspect
import unittest

from app.handlers import chat as chat_handlers


class ChatWelcomeRoutingTests(unittest.TestCase):
    def test_welcome_members_uses_shared_chat_key_lookup(self) -> None:
        source = inspect.getsource(chat_handlers.welcome_members)
        self.assertIn("chat_key_for_id(settings, message.chat.id)", source)
        self.assertNotIn("settings.internal_department_chat_id", source)
