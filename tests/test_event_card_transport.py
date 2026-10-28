"""Event previews and legacy cards must preserve Unicode text within Telegram limits."""
from datetime import date, time
from html import unescape
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage, SendPhoto

from app.services.event_card import format_event_text, send_event_card, send_event_card_to_chat


class EventCardTransportTests(IsolatedAsyncioTestCase):
    def event(self, *, poster=True, description="Программа <3 & встреча"):
        return SimpleNamespace(title="ЭРА <встреча>", description=description,
            event_date=date(2026, 11, 7), event_time=time(18), location="Дом Москвы & зал",
            format="offline", points_for_visit=5, poster_file_id="poster" if poster else None,
            additional_info=None)

    def transport(self):
        calls = []

        async def message(*args, **kwargs):
            text = args[-1]
            self.assertEqual(kwargs.get("parse_mode"), "HTML")
            self.assertNotIn("<встреча>", text)
            self.assertLessEqual(len(unescape(text).encode("utf-16-le")) // 2, 4096)
            calls.append((unescape(text), kwargs))

        async def photo(*args, **kwargs):
            self.assertEqual(kwargs.get("parse_mode"), "HTML")
            self.assertNotIn("<встреча>", kwargs["caption"])
            self.assertLessEqual(len(unescape(kwargs["caption"]).encode("utf-16-le")) // 2, 1024)
            calls.append((unescape(kwargs["caption"]), kwargs))

        target = SimpleNamespace(answer=AsyncMock(side_effect=message), answer_photo=AsyncMock(side_effect=photo))
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=message), send_photo=AsyncMock(side_effect=photo))
        return target, bot, calls

    async def test_long_emoji_card_preserves_all_text_and_keyboard_only_on_last_part(self):
        event = self.event(description="🎉" * 5000 + " & <3\nКонец")
        keyboard = object()
        for in_chat in (False, True):
            with self.subTest(in_chat=in_chat):
                target, bot, calls = self.transport()
                if in_chat:
                    self.assertTrue(await send_event_card_to_chat(bot, -1001, event,
                        keyboard=keyboard, message_thread_id=77))
                    self.assertTrue(all(kwargs.get("message_thread_id") == 77 for _, kwargs in calls))
                else:
                    await send_event_card(target, event, keyboard=keyboard)
                self.assertEqual("".join(text for text, _ in calls), format_event_text(event))
                self.assertIs(calls[-1][1]["reply_markup"], keyboard)
                self.assertTrue(all(kwargs.get("reply_markup") is None for _, kwargs in calls[:-1]))

    async def test_short_card_stays_one_photo_with_literal_title_and_body(self):
        target, _, calls = self.transport()
        event = self.event()
        await send_event_card(target, event)
        target.answer_photo.assert_awaited_once()
        target.answer.assert_not_awaited()
        self.assertEqual(calls[0][0], format_event_text(event))

    async def test_rejected_poster_falls_back_to_all_text_in_bounded_messages(self):
        target, bot, calls = self.transport()
        event = self.event(description="🎮 текст & <3 " * 800)
        bot.send_photo.side_effect = TelegramBadRequest(method=SendPhoto(chat_id=-1001, photo="x"), message="invalid photo")
        self.assertTrue(await send_event_card_to_chat(bot, -1001, event))
        self.assertEqual("".join(text for text, _ in calls), format_event_text(event))
        self.assertGreater(bot.send_message.await_count, 1)

    async def test_text_failure_stops_before_later_parts_or_final_keyboard(self):
        _, bot, _ = self.transport()
        event = self.event(poster=False, description="Текст " * 3000)
        bot.send_message.side_effect = TelegramBadRequest(method=SendMessage(chat_id=-1001, text="x"), message="rejected")
        self.assertFalse(await send_event_card_to_chat(bot, -1001, event, keyboard=object()))
        bot.send_message.assert_awaited_once()
        self.assertIsNone(bot.send_message.await_args.kwargs.get("reply_markup"))
