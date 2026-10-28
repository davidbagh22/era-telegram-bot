"""Legacy admin broadcast must not open registration on unconfirmed delivery."""
from datetime import date, time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.handlers.admin.events_block6 import (
    PREPARED_MARK, _deliver_prepared_announcement, broadcast_publish,
)
from app.services.notification_service import NotificationDeliveryResult
from app.utils.constants import EventStatus


def receipt(status="sent", *, duplicate=False):
    return NotificationDeliveryResult(
        sent=status in {"sent", "sent_unconfirmed"},
        status=status, duplicate=duplicate, attempt_count=1,
    )


def event(*, description="Описание", status=EventStatus.APPROVED):
    return SimpleNamespace(
        id=42, title="Встреча <ЭРА> & друзья", description=description,
        event_date=date(2026, 11, 4), event_time=time(18),
        location="Дом Москвы", format="офлайн", points_for_visit=0,
        poster_file_id=None, additional_info="Подробности\n" + PREPARED_MARK,
        status=status,
    )


class LegacyBroadcastDurabilityTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            bot_username="ERA_1bot", general_chat_id=-100123,
        )
        self.bot = object()

    async def test_partial_delivery_retry_uses_identical_durable_keys(self):
        item = event(description="🙂<&" * 420)
        with patch(
            "app.handlers.admin.events_block6.send_general_topic_once",
            new=AsyncMock(side_effect=[
                receipt(), receipt("failed"),
                receipt(duplicate=True), receipt(),
            ]),
        ) as sender:
            first = await _deliver_prepared_announcement(self.bot, self.settings, item)
            second = await _deliver_prepared_announcement(self.bot, self.settings, item)
        self.assertEqual((first, second), ("failed", "sent"))
        self.assertEqual(sender.await_count, 4)
        keys = [call.kwargs["delivery_key"] for call in sender.await_args_list]
        self.assertEqual(keys, [
            "legacy-event:42:broadcast:part:0",
            "legacy-event:42:broadcast:part:1",
            "legacy-event:42:broadcast:part:0",
            "legacy-event:42:broadcast:part:1",
        ])
        self.assertEqual(
            [call.kwargs["reply_markup"] is not None for call in sender.await_args_list],
            [False, True, False, True],
        )
        self.assertTrue(all(call.kwargs["parse_mode"] == "HTML" for call in sender.await_args_list))
        self.assertIn("&lt;ЭРА&gt; &amp; друзья", sender.await_args_list[0].args[3])

    async def test_uncertain_and_ack_write_failure_never_confirm_publication(self):
        item = event()
        for status in ("uncertain", "pending", "conflict", "sent_unconfirmed"):
            with self.subTest(status=status):
                with patch(
                    "app.handlers.admin.events_block6.send_general_topic_once",
                    new=AsyncMock(return_value=receipt(status)),
                ):
                    self.assertEqual(
                        await _deliver_prepared_announcement(self.bot, self.settings, item),
                        status,
                    )

    async def test_photo_uses_same_durable_transport_and_final_button(self):
        item = event(description="🎥" * 1400)
        item.poster_file_id = "existing-file-id"
        with patch(
            "app.handlers.admin.events_block6.send_general_topic_once",
            new=AsyncMock(return_value=receipt()),
        ) as sender:
            result = await _deliver_prepared_announcement(self.bot, self.settings, item)
        self.assertEqual(result, "sent")
        self.assertGreater(sender.await_count, 1)
        self.assertEqual(sender.await_args_list[0].kwargs["photo"], "existing-file-id")
        self.assertTrue(all(call.kwargs["photo"] is None for call in sender.await_args_list[1:]))
        self.assertIsNotNone(sender.await_args_list[-1].kwargs["reply_markup"])

    def callback(self):
        return SimpleNamespace(
            data="admin:event:broadcast_publish:42",
            from_user=SimpleNamespace(id=987),
            message=SimpleNamespace(answer=AsyncMock()),
        )

    async def test_failed_delivery_keeps_approved_status_and_prepared_marker(self):
        item = event()
        session = SimpleNamespace(get=AsyncMock(return_value=item), commit=AsyncMock())
        call = self.callback()
        with (
            patch("app.handlers.admin.events_block6.guard", new=AsyncMock(return_value=True)),
            patch("app.handlers.admin.events_block6._deliver_prepared_announcement",
                  new=AsyncMock(return_value="uncertain")) as delivery,
            patch("app.handlers.admin.events_block6.audit", new=AsyncMock()) as audit,
        ):
            await broadcast_publish(call, SimpleNamespace(id=5), self.settings, session, self.bot)
        delivery.assert_awaited_once()
        session.commit.assert_not_awaited()
        audit.assert_not_awaited()
        self.assertEqual(item.status, EventStatus.APPROVED)
        self.assertIn(PREPARED_MARK, item.additional_info)
        self.assertIn("не открыта", call.message.answer.await_args.args[0])

    async def test_confirmed_delivery_opens_registration_once(self):
        item = event()
        session = SimpleNamespace(get=AsyncMock(return_value=item), commit=AsyncMock())
        call = self.callback()
        with (
            patch("app.handlers.admin.events_block6.guard", new=AsyncMock(return_value=True)),
            patch("app.handlers.admin.events_block6._deliver_prepared_announcement",
                  new=AsyncMock(return_value="sent")) as delivery,
            patch("app.handlers.admin.events_block6.event_kb", return_value=None),
            patch("app.handlers.admin.events_block6.audit", new=AsyncMock()) as audit,
        ):
            await broadcast_publish(call, SimpleNamespace(id=5), self.settings, session, self.bot)
            await broadcast_publish(call, SimpleNamespace(id=5), self.settings, session, self.bot)
        delivery.assert_awaited_once()
        session.commit.assert_awaited_once()
        audit.assert_awaited_once()
        self.assertEqual(item.status, EventStatus.REGISTRATION_OPEN)
        self.assertNotIn(PREPARED_MARK, item.additional_info)

    async def test_invalid_status_does_not_send_even_with_stale_prepared_marker(self):
        item = event(status=EventStatus.CANCELLED)
        session = SimpleNamespace(get=AsyncMock(return_value=item), commit=AsyncMock())
        call = self.callback()
        with (
            patch("app.handlers.admin.events_block6.guard", new=AsyncMock(return_value=True)),
            patch("app.handlers.admin.events_block6._deliver_prepared_announcement",
                  new=AsyncMock()) as delivery,
        ):
            await broadcast_publish(call, SimpleNamespace(id=5), self.settings, session, self.bot)
        delivery.assert_not_awaited()
        session.commit.assert_not_awaited()
