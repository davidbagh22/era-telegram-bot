"""Typography and existing-message migration for November 2026 events."""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event
from app.services.event_announcement_format import event_topic_html, november_digest_html
from app.services.moscow_house_november import EVENTS, KEY, STYLED_REVISION, _restyle_published


def example(day: int, event_id: int):
    row = next(row for row in EVENTS if row[0] == day)
    event = SimpleNamespace(
        id=event_id, title=row[2], description=row[3],
        event_date=date(2026, 11, day), event_time=time(row[1]),
        location="Дом Москвы, ул. Аргишти, 7",
        additional_info=f"{KEY}:{day}",
    )
    experience = SimpleNamespace(
        full_description=row[3], end_time=time(14) if day == 28 else None,
        chat_url=f"https://t.me/c/2973371133/{26688 + (day % 23) * 2}",
    )
    return event, experience


class TelegramTypographyTests(TestCase):
    def test_topics_use_emphasis_and_named_links(self):
        event, exp = example(24, 31)
        output = event_topic_html(
            event, exp, registration="https://t.me/ERA_1bot?startapp=event_31",
            chat="https://t.me/+ERA", topic=exp.chat_url,
        )
        self.assertIn("<b>Тайны Серебряного века</b>", output)
        self.assertIn("<i>", output)
        self.assertIn('<a href="https://t.me/ERA_1bot?startapp=event_31">Зарегистрироваться</a>', output)
        self.assertIn("Обсуждение проекта</a>", output)
        self.assertNotIn("Регистрация: https://", output)

    def test_digest_has_four_events_and_short_registration_labels(self):
        items = []
        for i, day in enumerate((23, 24, 25, 28), 30):
            event, exp = example(day, i)
            items.append((event, exp, f"https://t.me/ERA_1bot?startapp=event_{i}"))
        output = november_digest_html(items, chat="https://t.me/+ERA")
        self.assertEqual(output.count(">Регистрация</a>"), 4)
        self.assertEqual(output.count(">Обсуждение</a>"), 4)
        self.assertIn("<b>ЧЕТЫРЕ СОБЫТИЯ", output)
        self.assertIn("10:00–14:00", output)


class TelegramEditInPlaceTests(IsolatedAsyncioTestCase):
    def make_context(self):
        ids = [30, 31, 32, 33]
        pairs = {event_id: example(day, event_id) for event_id, day in zip(ids, (23, 24, 25, 28))}
        receipt = SimpleNamespace(value={"complete": True, "events": ids, "message": 27000})
        ledger_rows = [SimpleNamespace(status="sent", chat_id=-1002973371133, message_id=26689 + index * 2)
                       for index in range(4)]
        digest = SimpleNamespace(status="sent", chat_id=-1002973371133, message_id=27000)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=lambda model, event_id:
                pairs[event_id][0] if model is Event else pairs[event_id][1]
                if model is EventExperience else None),
            scalar=AsyncMock(side_effect=[receipt, *ledger_rows, digest]),
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="ERA_1bot")),
            edit_message_text=AsyncMock(),
        )
        settings = SimpleNamespace(
            general_chat_id=-1002973371133, general_chat_url="https://t.me/+ERA"
        )
        return session, bot, settings, receipt

    async def test_edits_original_five_messages_without_resending(self):
        session, bot, settings, receipt = self.make_context()
        await _restyle_published(bot, settings, session)
        self.assertEqual(bot.edit_message_text.await_count, 5)
        self.assertEqual([c.kwargs["message_id"] for c in bot.edit_message_text.await_args_list],
                         [26689, 26691, 26693, 26695, 27000])
        self.assertIn('<a href=', bot.edit_message_text.await_args.kwargs["text"])
        self.assertEqual(receipt.value["styled_revision"], STYLED_REVISION)
        session.commit.assert_awaited_once()

    async def test_no_receipt_means_no_telegram_mutations(self):
        session, bot, settings, _ = self.make_context()
        session.scalar = AsyncMock(return_value=None)
        await _restyle_published(bot, settings, session)
        bot.edit_message_text.assert_not_awaited()

    async def test_missing_message_id_stops_before_any_edits(self):
        session, bot, settings, _ = self.make_context()
        receipt = SimpleNamespace(value={"complete": True, "events": [30, 31, 32, 33], "message": 27000})
        session.scalar = AsyncMock(side_effect=[
            receipt,
            SimpleNamespace(status="sent", chat_id=-1002973371133, message_id=None)
        ])
        await _restyle_published(bot, settings, session)
        bot.edit_message_text.assert_not_awaited()
