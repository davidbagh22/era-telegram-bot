from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api.v1.project_builder import read_project_builder_questions
from app.config import Settings
from app.handlers.participant.navigation import _send_navigation_guide
from app.services.chat_faq_service import FAQ_ANSWERS, FAQ_PINNED_MESSAGE
from app.services.system_scheduler import add_system_jobs
from app.utils.constants import ApplicationStatus, Role
from app.utils.deep_links import (
    miniapp_admin_url,
    miniapp_event_url,
    miniapp_projects_url,
)


class TelegramSafeDeepLinkTests(unittest.TestCase):
    def test_sections_use_query_route_not_fragment(self) -> None:
        url = miniapp_projects_url("https://era.example/app/")
        parsed = urlsplit(url)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(parse_qs(parsed.query)["eraPath"], ["projects"])

    def test_entity_route_preserves_existing_query(self) -> None:
        url = miniapp_event_url("https://era.example/app/?devTelegramId=42", 17)
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(query["devTelegramId"], ["42"])
        self.assertEqual(query["eraPath"], ["events/17"])

    def test_admin_route_is_explicit(self) -> None:
        url = miniapp_admin_url("https://era.example/app/")
        self.assertEqual(parse_qs(urlsplit(url).query)["eraPath"], ["admin"])


class TelegramNavigationRenderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_uses_html_parse_mode_instead_of_printing_tags(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        user = SimpleNamespace(
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
            role=Role.PARTICIPANT,
            permission_grants=[],
        )
        settings = Settings(
            bot_token="0000000000:TESTTOKEN",
            miniapp_auth_secret="test-secret",
            miniapp_url="https://era.example/app/",
        )

        await _send_navigation_guide(message, user, settings)

        message.answer.assert_awaited_once()
        args, kwargs = message.answer.await_args
        self.assertIn("<b>Куда идём?</b>", args[0])
        self.assertEqual(kwargs["parse_mode"], "HTML")
        keyboard = kwargs["reply_markup"]
        projects_url = keyboard.inline_keyboard[0][0].web_app.url
        self.assertEqual(parse_qs(urlsplit(projects_url).query)["eraPath"], ["projects"])


class ProjectBuilderContractTests(unittest.TestCase):
    def test_builder_exposes_explanations_and_ai_prompts(self) -> None:
        questions = asyncio.run(read_project_builder_questions())
        self.assertGreater(len(questions), 10)
        self.assertTrue(all(question.prompt.strip() for question in questions))
        self.assertTrue(any(question.ai_hint and question.ai_hint.strip() for question in questions))
        self.assertTrue(any(question.key == "scenario" and question.ai_hint for question in questions))


class GeneralFaqContractTests(unittest.TestCase):
    def test_pinned_card_and_private_answers_are_editorially_complete(self) -> None:
        self.assertIn("лично вам", FAQ_PINNED_MESSAGE)
        self.assertEqual(
            set(FAQ_ANSWERS),
            {"faq:what_is_era", "faq:what_it_gives", "faq:what_to_do", "faq:what_can_i_do"},
        )
        self.assertTrue(all(len(text) > 120 for text in FAQ_ANSWERS.values()))

    def test_scheduler_keeps_faq_pin_alive(self) -> None:
        settings = Settings(bot_token="0000000000:TESTTOKEN", timezone="Asia/Yerevan")
        scheduler = AsyncIOScheduler(timezone=settings.timezone)
        add_system_jobs(scheduler, SimpleNamespace(), settings, lambda: None)
        jobs = {job.id for job in scheduler.get_jobs()}
        self.assertIn("general-chat-faq-pin", jobs)


if __name__ == "__main__":
    unittest.main()
