from __future__ import annotations

import unittest
from datetime import date, time, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, User
from app.keyboards.faq import faq_keyboard
from app.services.ai_service import AIService, PROJECT_ANSWER_INSTRUCTIONS
from app.services.event_service import promote_waitlist, register_for_event
from app.services.project_builder import PROJECT_QUESTIONS
from app.utils.constants import EventStatus, RegistrationStatus


class EventExperienceRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=f"User{telegram_id}",
            phone=f"+100000{telegram_id}",
            personal_data_consent=True,
            is_channel_subscribed=True,
            role="participant",
        )
        session.add(user)
        await session.flush()
        return user

    async def _event(self, session, created_by: int, *, limit: int = 1) -> Event:
        event = Event(
            title="ERA Event",
            description="Full description",
            event_date=date.today() + timedelta(days=3),
            event_time=time(18, 0),
            location="House of Moscow",
            format="Офлайн",
            participant_limit=limit,
            created_by=created_by,
            status=EventStatus.REGISTRATION_OPEN,
        )
        session.add(event)
        await session.flush()
        return event

    async def test_capacity_waitlist_duplicate_and_promotion(self) -> None:
        async with self.sessions() as session:
            first = await self._user(session, 101)
            second = await self._user(session, 102)
            event = await self._event(session, first.id, limit=1)

            first_registration, first_error = await register_for_event(
                session, event, first.id, waitlist_enabled=True
            )
            self.assertIsNone(first_error)
            self.assertEqual(first_registration.status, RegistrationStatus.REGISTERED)

            second_registration, second_error = await register_for_event(
                session, event, second.id, waitlist_enabled=True
            )
            self.assertIsNone(second_error)
            self.assertEqual(second_registration.status, RegistrationStatus.WAITLIST)

            duplicate, duplicate_error = await register_for_event(
                session, event, second.id, waitlist_enabled=True
            )
            self.assertIsNone(duplicate)
            self.assertEqual(duplicate_error, "already")

            first_registration.status = RegistrationStatus.CANCELLED
            await session.flush()
            promoted = await promote_waitlist(session, event)
            self.assertIsNotNone(promoted)
            self.assertEqual(promoted.user_id, second.id)
            self.assertEqual(promoted.status, RegistrationStatus.REGISTERED)

    async def test_rich_event_draft_fields_survive_reload(self) -> None:
        async with self.sessions() as session:
            admin = await self._user(session, 201)
            event = await self._event(session, admin.id, limit=40)
            experience = EventExperience(
                event_id=event.id,
                short_description="Short",
                full_description="Long",
                category="Мастер-класс",
                chat_url="https://t.me/example",
                waitlist_enabled=True,
                program=[{"title": "Практика", "time": "19:00"}],
                participant_tasks=[{"title": "Сделать ролик", "points": 15}],
                reminders=[1440, 180, 60],
                wizard_step=8,
                is_complete=False,
            )
            session.add(experience)
            await session.commit()
            event_id = event.id

        async with self.sessions() as session:
            restored = await session.get(EventExperience, event_id)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.wizard_step, 8)
            self.assertEqual(restored.program[0]["title"], "Практика")
            self.assertEqual(restored.participant_tasks[0]["points"], 15)
            self.assertEqual(restored.reminders, [1440, 180, 60])
            self.assertTrue(restored.waitlist_enabled)


class MasterPromptStaticRegressionTests(unittest.TestCase):
    def test_project_constructor_is_sixteen_questions_plus_preview(self) -> None:
        self.assertEqual(len(PROJECT_QUESTIONS), 16)
        keys = [question.key for question in PROJECT_QUESTIONS]
        self.assertEqual(
            keys,
            [
                "idea",
                "title",
                "problem",
                "target_audience",
                "goal",
                "scenario",
                "format",
                "team",
                "implementation_plan",
                "resources",
                "activities",
                "tasks",
                "points",
                "expected_result",
                "success_metrics",
                "risks",
            ],
        )

    def test_project_ai_policy_forbids_invented_business_facts(self) -> None:
        for phrase in ("партнёров", "бюджет", "показатели", "количество участников", "результаты"):
            self.assertIn(phrase, PROJECT_ANSWER_INSTRUCTIONS)

        service = AIService(Settings(bot_token="1234567890:test-token"))
        with self.assertRaises(ValueError):
            # Validation happens before any network call / API-key requirement.
            import asyncio

            asyncio.run(
                service.assist_project_answer(
                    question="Что меняется?",
                    answer="Мой текст",
                    operation="invent",  # type: ignore[arg-type]
                )
            )

    def test_pinned_faq_buttons_open_private_start_payloads(self) -> None:
        markup = faq_keyboard("era_bot")
        urls = [button.url for row in markup.inline_keyboard for button in row]
        self.assertEqual(len(urls), 7)
        self.assertTrue(all(url and url.startswith("https://t.me/era_bot?start=faq_") for url in urls))

    def test_event_export_source_does_not_log_phone_numbers(self) -> None:
        source = Path("app/api/v1/admin_event_operations.py").read_text(encoding="utf-8")
        self.assertIn('participant.phone or ""', source)
        self.assertNotIn("logger.", source)
        self.assertNotIn("print(", source)

    def test_frontend_has_no_silent_deep_link_home_fallback(self) -> None:
        source = Path("frontend/src/app/App.tsx").read_text(encoding="utf-8")
        self.assertIn("return link({ invalid: true });", source)
        self.assertIn("event_(\\d+)", source)
        self.assertIn("project_(\\d+)", source)
        self.assertIn("task_(\\d+)", source)
        self.assertIn("admin_event_(\\d+)", source)
