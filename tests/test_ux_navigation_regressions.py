from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api.v1.project_builder import read_project_builder_questions
from app.config import Settings
from app.services.chat_faq_service import FAQ_ANSWERS, FAQ_PINNED_MESSAGE
from app.services.system_scheduler import add_system_jobs
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


class ProjectBuilderContractTests(unittest.TestCase):
    def test_builder_exposes_explanations_and_ai_prompts(self) -> None:
        questions = asyncio.run(read_project_builder_questions())
        self.assertEqual(len(questions), 16)
        self.assertTrue(all(question.prompt.strip() for question in questions))
        self.assertTrue(all(question.ai_hint and question.ai_hint.strip() for question in questions))
        self.assertTrue(any(question.key == "scenario" and question.ai_hint for question in questions))


class GeneralFaqContractTests(unittest.TestCase):
    def test_pinned_card_and_private_answers_cover_master_navigation(self) -> None:
        self.assertIn("лично для вас", FAQ_PINNED_MESSAGE)
        required = {
            "faq:events",
            "faq:projects",
            "faq:tasks",
            "faq:points",
            "faq:registration",
            "faq:active",
            "faq:contact",
        }
        self.assertTrue(required.issubset(set(FAQ_ANSWERS)))
        self.assertTrue(all(len(FAQ_ANSWERS[key]) > 80 for key in required))

    def test_scheduler_keeps_faq_pin_alive(self) -> None:
        settings = Settings(bot_token="0000000000:TESTTOKEN", timezone="Asia/Yerevan")
        scheduler = AsyncIOScheduler(timezone=settings.timezone)
        add_system_jobs(scheduler, SimpleNamespace(), settings, lambda: None)
        jobs = {job.id for job in scheduler.get_jobs()}
        self.assertIn("general-chat-faq-pin", jobs)
        self.assertIn("configured-event-reminders", jobs)
        self.assertIn("event-wizard-task-sync", jobs)


if __name__ == "__main__":
    unittest.main()
