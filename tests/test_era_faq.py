from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText
from aiogram.types import CallbackQuery, Chat, Message, User as TelegramUser

from app.content.era_faq import (
    FAQ_ACTIONS,
    FAQ_CATEGORIES,
    FAQ_DATA,
    FAQ_HOME_TEXT,
    faq_message_context,
)
from app.handlers.participant import faq, navigation, questions
from app.keyboards.bot_shell import main_inline_keyboard
from app.keyboards.faq import faq_category_keyboard, get_faq_answer_keyboard
from app.middlewares.faq_context import FaqContextMiddleware
from app.states.question import QuestionStates
from app.utils.constants import ApplicationStatus
from app.utils.telegram import edit_text_or_answer


def approved(**kwargs):
    return SimpleNamespace(
        id=1,
        telegram_id=123,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
        **kwargs,
    )


def state():
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=123, user_id=123)
    )


def call(data, text=None):
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=SimpleNamespace(text=text, edit_text=AsyncMock(), answer=AsyncMock()),
    )


def telegram_call(data, text):
    return CallbackQuery(
        id="1",
        from_user=TelegramUser(id=123, is_bot=False, first_name="User"),
        chat_instance="1",
        data=data,
        message=Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=123, type="private"),
            text=text,
        ),
    )


class FaqTests(unittest.IsolatedAsyncioTestCase):
    def test_complete_content_and_navigation(self):
        self.assertEqual(set(FAQ_DATA), {f"q{i}" for i in range(1, 23)})
        seen = []
        for key, category in FAQ_CATEGORIES.items():
            self.assertLessEqual(len(category["questions"]), 5)
            for q in category["questions"]:
                seen.append(q)
                item = FAQ_DATA[q]
                self.assertEqual(item["category"], key)
                self.assertLess(len(item["text"]), 4096)
                self.assertIn("\n\n", item["text"])
                markup = get_faq_answer_keyboard(f"faq:cat:{key}", item.get("action"))
                callbacks = [
                    b.callback_data for row in markup.inline_keyboard for b in row
                ]
                self.assertIn("contact:menu", callbacks)
                self.assertEqual(callbacks[-2:], [f"faq:cat:{key}", "menu:main"])
                if item.get("action"):
                    self.assertEqual(callbacks[0], FAQ_ACTIONS[item["action"]][1])
                self.assertTrue(all(len(c.encode()) <= 64 for c in callbacks))
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), set(FAQ_DATA))
        for url in ["", "https://example.org/app"]:
            self.assertIn(
                "faq:home",
                [
                    b.callback_data
                    for row in main_inline_keyboard(miniapp_url=url).inline_keyboard
                    for b in row
                ],
            )

    async def test_every_screen_edits_and_records_audit_and_clears_state(self):
        for data in [
            "faq:home",
            *[f"faq:cat:{c}" for c in FAQ_CATEGORIES],
            *[f"faq:q:{q}" for q in FAQ_DATA],
        ]:
            c, s = call(data), state()
            await s.set_state(QuestionStates.text)
            session = SimpleNamespace(add=lambda row: None)
            with patch.object(faq, "audit", AsyncMock()) as audit:
                await faq.faq_navigation(c, approved(), s, session)
            c.answer.assert_awaited_once()
            c.message.edit_text.assert_awaited_once()
            c.message.answer.assert_not_awaited()
            self.assertIsNone(await s.get_state())
            self.assertIsNone(c.message.edit_text.call_args.kwargs["parse_mode"])
            audit.assert_awaited_once()

    async def test_missing_category_and_question_recover_to_home(self):
        for data in ["faq:q:deleted", "faq:q:", "faq:cat:deleted"]:
            c = call(data)
            await faq.faq_navigation(c, approved(), state(), None)
            self.assertEqual(c.message.edit_text.call_args.args[0], FAQ_HOME_TEXT)
            c.answer.assert_awaited_once()

    def test_empty_category_and_missing_data_keep_navigation(self):
        with patch.dict(
            FAQ_CATEGORIES, {"empty": {"title": "Пусто", "questions": ["deleted"]}}
        ):
            markup = faq_category_keyboard("empty")
            self.assertEqual(
                [b.callback_data for row in markup.inline_keyboard for b in row],
                ["contact:menu", "faq:home", "menu:main"],
            )

    async def test_access_gate(self):
        for user in [None, approved(), approved(), approved()]:
            if user:
                if not hasattr(self, "gate_index"):
                    self.gate_index = 0
                attr, value = [
                    ("is_blocked", True),
                    ("is_archived", True),
                    ("application_status", "pending"),
                ][self.gate_index]
                setattr(user, attr, value)
                self.gate_index += 1
            c = call("faq:home")
            await faq.faq_navigation(c, user, state(), None)
            c.message.edit_text.assert_not_awaited()
            c.answer.assert_awaited_once()

    async def test_repeat_click_and_old_message_fallback(self):
        for error, sends in [
            ("message is not modified", 0),
            ("message to edit not found", 1),
            ("message can't be edited", 1),
        ]:
            c = call("faq:home")
            c.message.edit_text.side_effect = TelegramBadRequest(
                method=EditMessageText(text="x"), message=error
            )
            await edit_text_or_answer(c.message, "Hello")
            self.assertEqual(c.message.answer.await_count, sends)
        c.message.edit_text.side_effect = TelegramBadRequest(
            method=EditMessageText(text="x"), message="unrelated invalid markup"
        )
        with self.assertRaises(TelegramBadRequest):
            await edit_text_or_answer(c.message, "Hello")

    async def test_actions_delegate_unchanged_and_audit_context(self):
        for q, item in FAQ_DATA.items():
            targets = ["contact:menu"]
            if item.get("action"):
                targets.append(FAQ_ACTIONS[item["action"]][1])
            for target in targets:
                c = telegram_call(target, item["text"])
                handler, audit = AsyncMock(), AsyncMock()
                data = {"user": approved(), "session": object()}
                with patch("app.middlewares.faq_context.audit", audit):
                    await FaqContextMiddleware()(handler, c, data)
                handler.assert_awaited_once_with(c, data)
                self.assertEqual(data["faq_context"]["question"], q)
                self.assertEqual(
                    audit.call_args.kwargs["new_value"]["category"], item["category"]
                )

    async def test_unrelated_callbacks_are_not_analytics_events(self):
        handler = AsyncMock()
        with patch("app.middlewares.faq_context.audit", AsyncMock()) as audit:
            await FaqContextMiddleware()(
                handler, telegram_call("contact:menu", "Unrelated"), {}
            )
        handler.assert_awaited_once()
        audit.assert_not_awaited()

    async def test_contact_menu_to_question_to_category(self):
        c, s = call("contact:menu"), state()
        ctx = faq_message_context(FAQ_DATA["q17"]["text"])
        await navigation.contact_callback(c, approved(), s, ctx)
        markup = c.message.answer.call_args.kwargs["reply_markup"]
        self.assertIn(
            "faq:cat:travel",
            [b.callback_data for row in markup.inline_keyboard for b in row],
        )
        await questions.question_start(call("question:start"), s, approved())
        self.assertEqual(await s.get_state(), QuestionStates.text.state)
        self.assertEqual((await s.get_data())["faq_context"]["back"], "faq:cat:travel")
        back = call("faq:cat:travel")
        with patch.object(faq, "audit", AsyncMock()):
            await faq.faq_navigation(back, approved(), s, None)
        self.assertIsNone(await s.get_state())

    async def test_contextual_contact_saves_topic_and_shows_return(self):
        s, c = state(), call("question:start")
        ctx = {
            **faq_message_context(FAQ_DATA["q18"]["text"]),
            "topic": "Хочу стать активнее в ЭРА",
        }
        user = approved(first_name="User", last_name="Test")
        await questions.question_start(c, s, user, ctx)
        await s.update_data(question_text="Хочу помогать")
        session = SimpleNamespace(
            add=lambda row: setattr(self, "saved_question", row), flush=AsyncMock()
        )
        with (
            patch.object(questions, "audit", AsyncMock()),
            patch.object(questions, "notify_admins", AsyncMock()),
        ):
            await questions._save_question(c.message, s, session, user, None, None)
        self.assertIn(ctx["topic"], self.saved_question.text)
        self.assertIsNone(await s.get_state())
        markup = c.message.answer.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[-1][0].callback_data, "faq:cat:growth")

    async def test_existing_callback_owners_are_reachable(self):
        from app.handlers import registration, start
        from app.handlers.participant import router as participant_router

        async def find_owner(router, event):
            observer = router.callback_query
            ok, _ = await observer.check_root_filters(event)
            if not ok:
                return None
            for handler in observer.handlers:
                ok, _ = await handler.check(event)
                if ok:
                    return handler.callback.__module__, handler.callback.__name__
            for child in router.sub_routers:
                found = await find_owner(child, event)
                if found:
                    return found
            return None

        expected = {
            "registration:start": "registration_start",
            "events:list": "event_list",
            "tasks:hub": "tasks_root",
            "cabinet:rating": "show_rating",
            "offers:menu": "offers_menu",
            "project:new:guided": "project_start",
            "question:start": "question_start",
            "contact:menu": "contact_callback",
            "menu:main": "main_menu_callback",
            "faq:home": "faq_navigation",
            "faq:cat:travel": "faq_navigation",
            "faq:q:q22": "faq_navigation",
        }
        for target, name in expected.items():
            event = telegram_call(target, FAQ_HOME_TEXT)
            found = None
            for root in [start.router, registration.router, participant_router]:
                found = await find_owner(root, event)
                if found:
                    break
            self.assertIsNotNone(found, target)
            self.assertEqual(found[1], name, target)

    async def test_contact_file_steps_keep_back_navigation(self):
        s, c = state(), call("question:start")
        context = faq_message_context(FAQ_DATA["q22"]["text"])
        await questions.question_start(c, s, approved(), context)
        message = SimpleNamespace(text="Нужен дизайнер", answer=AsyncMock())
        await questions.question_text(message, s)
        self.assertEqual(await s.get_state(), QuestionStates.attachment_choice.state)
        callbacks = [
            b.callback_data
            for row in message.answer.call_args.kwargs["reply_markup"].inline_keyboard
            for b in row
        ]
        self.assertIn("faq:cat:projects", callbacks)
        await questions.question_with_file(c, s)
        self.assertEqual(await s.get_state(), QuestionStates.attachment.state)
        callbacks = [
            b.callback_data
            for row in c.message.answer.call_args.kwargs["reply_markup"].inline_keyboard
            for b in row
        ]
        self.assertIn("faq:cat:projects", callbacks)

    async def test_outbound_actions_recheck_access(self):
        for user in [None, approved()]:
            if user:
                user.is_blocked = True
            handler = AsyncMock()
            with patch.object(CallbackQuery, "answer", AsyncMock()) as answer:
                await FaqContextMiddleware()(
                    handler,
                    telegram_call("project:new:guided", FAQ_DATA["q11"]["text"]),
                    {"user": user},
                )
            handler.assert_not_awaited()
            answer.assert_awaited_once()
