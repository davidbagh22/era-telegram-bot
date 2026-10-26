"""Regression tests for read-only Leaders chat binding validation."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import unittest

from app.handlers.chat_binding import _binding_conflict, _leaders_permission_error


class LeadersChatBindSafetyTests(unittest.TestCase):
    def test_cannot_bind_general_chat_as_leaders_or_reverse(self):
        settings = SimpleNamespace(general_chat_id=-10011, leaders_chat_id=-10022)
        self.assertIsNotNone(_binding_conflict("leaders", -10011, settings))
        self.assertIsNotNone(_binding_conflict("general", -10022, settings))
        self.assertIsNone(_binding_conflict("leaders", -10022, settings))
        self.assertIsNone(_binding_conflict("general", -10011, settings))

    def test_leaders_forum_requires_admin_and_manage_topics(self):
        forum = SimpleNamespace(type="supergroup", is_forum=True)
        ordinary = SimpleNamespace(status="member", can_manage_topics=True)
        no_topics = SimpleNamespace(status="administrator", can_manage_topics=False)
        admin = SimpleNamespace(status="administrator", can_manage_topics=True)
        self.assertIsNotNone(_leaders_permission_error(forum, ordinary))
        self.assertIsNotNone(_leaders_permission_error(forum, no_topics))
        self.assertIsNone(_leaders_permission_error(forum, admin))

    def test_forwarded_binding_checks_before_persisting(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "app" / "handlers" / "admin" / "chat_binding_stability.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_binding_conflict(str(key), chat.id, settings)", source)
        self.assertIn("_leaders_permission_error(actual_chat, member)", source)
        self.assertLess(
            source.index("_leaders_permission_error(actual_chat, member)"),
            source.index("    await _save_binding(", source.index("async def bind_chat_finish_stable")),
        )

    def test_plain_group_supported_and_channel_rejected(self):
        plain = SimpleNamespace(type="supergroup", is_forum=False)
        channel = SimpleNamespace(type="channel", is_forum=False)
        admin = SimpleNamespace(status="administrator", can_manage_topics=False)
        self.assertIsNone(_leaders_permission_error(plain, admin))
        self.assertIsNotNone(_leaders_permission_error(channel, admin))




class LeadersReadOnlyDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            admin_ids=[1001], leaders_chat_id=-1001, general_chat_id=-1002,
        )
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001), answer=AsyncMock(),
        )
        self.session = SimpleNamespace(
            scalar=AsyncMock(),
            execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
            commit=AsyncMock(),
        )
        self.bot = SimpleNamespace(
            id=77,
            get_chat=AsyncMock(return_value=SimpleNamespace(
                type="supergroup", is_forum=True,
            )),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(
                status="administrator", can_manage_topics=True,
            )),
        )

    async def test_diagnostics_show_live_pin_rights_without_writes(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [None] * 9
        member = self.bot.get_chat_member.return_value
        for can_pin, expected in ((True, "да"), (False, "нет"), (None, "нет")):
            with self.subTest(can_pin=can_pin):
                member.can_pin_messages = can_pin
                await leaders_readonly_diagnostics(
                    self.message, None, self.settings, self.session, self.bot,
                )
                result = self.message.answer.await_args.args[0]
                self.assertIn(f"Закрепление сообщений: {expected}", result)
        self.bot.get_chat_member.assert_awaited()
        self.session.commit.assert_not_awaited()

    async def test_only_admin_can_read_diagnostics(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.message.from_user.id = 999
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        self.bot.get_chat.assert_not_awaited()
        self.session.scalar.assert_not_awaited()
        self.assertIn("только администратору", self.message.answer.await_args.args[0])

    async def test_saved_ids_are_not_claimed_to_be_live_and_no_mutations(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"thread_id": 31, "message_id": 90})),
            SimpleNamespace(value=json.dumps({"thread_state": "creating"})),
            SimpleNamespace(value=json.dumps({"message_state": "uncertain"})),
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("thread_id=31 (из БД, не проверен в Telegram)", result)
        self.assertIn("нужна ручная сверка, не создавать повторно", result)
        self.assertIn("доставка не подтверждена", result)
        self.assertIn("Управление темами: да", result)
        self.assertEqual(self.session.scalar.await_count, 3)
        self.session.commit.assert_not_awaited()

    async def test_unconfirmed_thread_state_takes_priority_over_saved_id(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({
                "mode": "forum", "thread_id": 31, "thread_state": "failed",
            })),
            SimpleNamespace(value=json.dumps({
                "mode": "forum", "thread_id": 32, "thread_state": "uncertain",
            })),
            None,
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Задачи: создание не подтверждено", result)
        self.assertIn("Пульс: создание не подтверждено", result)
        self.assertNotIn("thread_id=31 (из БД", result)
        self.assertNotIn("thread_id=32 (из БД", result)
        self.session.commit.assert_not_awaited()

    async def test_damaged_mode_and_thread_id_are_not_reported_ready(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"mode": "broken", "thread_id": 31})),
            SimpleNamespace(value=json.dumps({"mode": "forum", "thread_id": True})),
            SimpleNamespace(value=json.dumps({"mode": "plain", "thread_id": 45})),
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Задачи: режим темы повреждён", result)
        self.assertIn("Пульс: настройка темы повреждена", result)
        self.assertIn("Важно: Telegram: форум, но сохранён режим обычной группы", result)
        self.assertNotIn("thread_id=31 (из БД", result)
        self.session.commit.assert_not_awaited()

    async def test_live_plain_group_never_reports_stale_forum_ids_as_topics(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.bot.get_chat.return_value.is_forum = False
        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"mode": "forum", "thread_id": 31})),
            SimpleNamespace(value=json.dumps({"thread_id": 32})),
            SimpleNamespace(value=json.dumps({"mode": "plain", "message_id": 10})),
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Форум: нет", result)
        self.assertIn("Задачи: Telegram: обычная группа, но сохранён ID темы", result)
        self.assertIn("Пульс: Telegram: обычная группа, но сохранён ID темы", result)
        self.assertIn("Важно: обычная группа, отдельной темы нет", result)
        self.assertNotIn("thread_id=31 (из БД", result)
        self.assertNotIn("thread_id=32 (из БД", result)
        self.session.commit.assert_not_awaited()

    async def test_live_forum_never_reports_stale_plain_mode_as_ready(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"mode": "plain", "message_id": 10})),
            None,
            None,
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Форум: да", result)
        self.assertIn("Задачи: Telegram: форум, но сохранён режим обычной группы", result)
        self.assertNotIn("Задачи: обычная группа, отдельной темы нет", result)
        self.session.commit.assert_not_awaited()

    async def test_plain_tasks_without_confirmed_panel_require_review(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.bot.get_chat.return_value.is_forum = False
        for payload in (
            {"mode": "plain"},
            {"mode": "plain", "message_id": 17, "message_state": "uncertain"},
            {"mode": "plain", "message_id": True, "message_state": "sent"},
        ):
            with self.subTest(payload=payload):
                self.session.scalar.side_effect = [
                    SimpleNamespace(value=json.dumps(payload)), None, None,
                ]
                await leaders_readonly_diagnostics(
                    self.message, None, self.settings, self.session, self.bot,
                )
                result = self.message.answer.await_args.args[0]
                self.assertIn("Задачи: панель задач не подтверждена", result)
                self.assertNotIn("Задачи: обычная группа, отдельной темы нет", result)
        self.session.commit.assert_not_awaited()

    async def test_malformed_plain_panel_receipts_never_crash_or_claim_delivery(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.bot.get_chat.return_value.is_forum = False
        for receipt in (
            {"message_state": ["sending"], "message_id": 17},
            {"message_state": {"status": "sent"}, "message_id": 17},
            {"message_state": "sent", "message_id": ["17"]},
            {"message_state": "sent", "message_id": {"id": 17}},
        ):
            with self.subTest(receipt=receipt):
                self.session.scalar.side_effect = [
                    SimpleNamespace(value=json.dumps({"mode": "plain", **receipt})),
                    None, None,
                ]
                await leaders_readonly_diagnostics(
                    self.message, None, self.settings, self.session, self.bot,
                )
                result = self.message.answer.await_args.args[0]
                self.assertIn("Задачи: панель задач не подтверждена", result)
                self.assertIn("Карточка: данные квитанции повреждены", result)
                self.assertNotIn("Карточка message_id=17", result)
        self.session.commit.assert_not_awaited()

    async def test_malformed_forum_card_receipt_is_reported_without_mutations(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({
                "mode": "forum", "thread_id": 31,
                "message_state": ["uncertain"], "message_id": {"id": 22},
            })),
            None, None,
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Задачи: thread_id=31 (из БД, не проверен в Telegram)", result)
        self.assertIn("Карточка: данные квитанции повреждены", result)
        self.assertNotIn("Карточка message_id=", result)
        self.session.commit.assert_not_awaited()

    async def test_diagnostics_do_not_read_general_chat_binding(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.settings.leaders_chat_id = self.settings.general_chat_id
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        self.bot.get_chat.assert_not_awaited()
        self.session.scalar.assert_not_awaited()
        self.assertIn("не привязан отдельно", self.message.answer.await_args.args[0])

    async def test_diagnostics_count_uncertain_task_deliveries_without_mutations(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.session.scalar.side_effect = [None, None, None]
        self.session.execute.return_value = SimpleNamespace(
            all=lambda: [("sent", 4), ("pending", 1), ("review_required", 2), ("failed", 3)]
        )
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("отправлено 4", result)
        self.assertIn("ожидает 1", result)
        self.assertIn("требует сверки 2", result)
        self.assertIn("ошибки 3", result)
        self.assertIn("Не повторяйте отправку", result)
        self.session.execute.assert_awaited_once()
        self.session.commit.assert_not_awaited()

    async def test_plain_chat_mode_is_distinguished_from_forum_topic(self):
        from app.handlers.chat_binding import leaders_readonly_diagnostics

        self.bot.get_chat.return_value.is_forum = False
        self.session.scalar.side_effect = [
            SimpleNamespace(value=json.dumps({"mode": "plain", "message_id": 17, "message_state": "sent"})),
            None,
            None,
        ]
        await leaders_readonly_diagnostics(
            self.message, None, self.settings, self.session, self.bot,
        )
        result = self.message.answer.await_args.args[0]
        self.assertIn("Форум: нет", result)
        self.assertIn("обычная группа, отдельной темы нет", result)
        self.session.commit.assert_not_awaited()


class LeadersTopicRoutingSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrupt_or_invalid_thread_ids_never_become_routing_targets(self):
        from app.services.leaders_topics_service import delivery_topic, topic_id

        for stored in (None, "not-json", "[]", '{"thread_id":"7"}',
                       '{"thread_id":true}', '{"thread_id":0}',
                       '{"mode":"plain","thread_id":7}'):
            with self.subTest(stored=stored):
                row = SimpleNamespace(value=stored) if stored is not None else None
                session = SimpleNamespace(scalar=AsyncMock(return_value=row))
                self.assertIsNone(await topic_id(session, -1001, "tasks"))
                with self.assertRaises(ValueError):
                    await delivery_topic(session, -1001, "tasks")

    async def test_valid_forum_thread_and_explicit_plain_mode(self):
        from app.services.leaders_topics_service import delivery_topic, topic_id

        for value, expected in (('{"thread_id":7}', 7), ('{"mode":"plain","message_id":17,"message_state":"sent"}', None)):
            with self.subTest(value=value):
                session = SimpleNamespace(
                    scalar=AsyncMock(return_value=SimpleNamespace(value=value)),
                    scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
                )
                self.assertEqual(await topic_id(session, -1001, "tasks"), expected)
                self.assertEqual(await delivery_topic(session, -1001, "tasks"), expected)

    async def test_plain_tasks_require_confirmed_panel_receipt(self):
        from app.services.leaders_topics_service import delivery_topic, topic_id

        unsafe = (
            '{"mode":"plain"}',
            '{"mode":"plain","message_id":17}',
            '{"mode":"plain","message_id":17,"message_state":"sending"}',
            '{"mode":"plain","message_id":17,"message_state":"uncertain"}',
            '{"mode":"plain","message_id":true,"message_state":"sent"}',
            '{"mode":"plain","message_id":0,"message_state":"sent"}',
            '{"mode":"plain","message_id":"17","message_state":"sent"}',
        )
        for value in unsafe:
            with self.subTest(value=value):
                session = SimpleNamespace(scalar=AsyncMock(
                    return_value=SimpleNamespace(value=value),
                ))
                self.assertIsNone(await topic_id(session, -1001, "tasks"))
                with self.assertRaisesRegex(ValueError, "Панель задач"):
                    await delivery_topic(session, -1001, "tasks")

    async def test_plain_pulse_and_important_do_not_require_task_panel(self):
        from app.services.leaders_topics_service import delivery_topic

        for key in ("pulse", "important"):
            with self.subTest(key=key):
                session = SimpleNamespace(scalar=AsyncMock(
                    return_value=SimpleNamespace(value='{"mode":"plain","thread_id":null}'),
                ))
                self.assertIsNone(await delivery_topic(session, -1001, key))

    async def test_card_sync_never_sends_into_default_topic_when_setting_is_corrupt(self):
        from unittest.mock import patch

        from app.services.leaders_workcenter_service import sync_one_card
        from app.utils.constants import TaskStatus

        task = SimpleNamespace(
            id=1, title="Проверить отчёт", assignee_id=None, deadline=None,
            status=TaskStatus.NEW, comment=None, reward_json={},
        )
        delivery = SimpleNamespace(
            id=10, task_id=1, chat_id=-1001, status="pending",
            telegram_message_id=None, last_card_snapshot=None, error=None,
        )
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[
            delivery, SimpleNamespace(value="not-json"),
        ]))
        bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
        settings = SimpleNamespace(leaders_chat_id=-1001)
        with patch("app.services.notification_service.safe_send_once",
                   new_callable=AsyncMock) as safe:
            await sync_one_card(session, bot, settings, task)
            safe.assert_not_awaited()
        bot.send_message.assert_not_awaited()
        self.assertEqual(delivery.status, "pending")
        self.assertIn("не настроена", delivery.error)


if __name__ == "__main__":
    unittest.main()
