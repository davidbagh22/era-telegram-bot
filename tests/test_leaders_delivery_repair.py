from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
import json

from app.services.leaders_campaign_service import delivery_options
from app.handlers.chat_binding import repair_leaders_panel


class DeliveryRepairTests(IsolatedAsyncioTestCase):
    async def test_unauthorized_repair_does_not_touch_database_or_telegram(self):
        msg = NS(from_user=NS(id=7), chat=NS(id=-1001))
        session, bot = NS(scalar=AsyncMock()), NS(edit_message_text=AsyncMock())
        with patch('app.handlers.chat_binding._can_bind', return_value=False):
            await repair_leaders_panel(msg, None, NS(leaders_chat_id=-1001, general_chat_id=-1002), session, bot)
        session.scalar.assert_not_awaited()
        bot.edit_message_text.assert_not_awaited()

    async def test_unconfirmed_panel_offers_explicit_dm_only(self):
        with patch('app.services.leaders_topics_service.delivery_topic', new=AsyncMock(side_effect=ValueError('unsafe'))):
            modes, notice = await delivery_options(None, NS(leaders_chat_id=-1001))
        self.assertEqual(modes, [('Лично', 'dm')])
        self.assertIn('/leaders_repair important', notice)

    async def test_confirmed_panel_restores_group_choices(self):
        with patch('app.services.leaders_topics_service.delivery_topic', new=AsyncMock(return_value=42)):
            modes, notice = await delivery_options(None, NS(leaders_chat_id=-1001))
        self.assertEqual([m[1] for m in modes], ['group', 'dm', 'both'])
        self.assertIsNone(notice)

    async def test_scoped_delivery_does_not_need_group_panel(self):
        self.assertEqual(await delivery_options(None, None, scoped=True), ([('Лично', 'dm')], None))

    async def test_repair_updates_existing_message_without_sending_new_panel(self):
        row = NS(value=json.dumps({'thread_id': 42, 'message_state': 'uncertain'}))
        session = NS(bind=NS(dialect=NS(name='sqlite')), scalar=AsyncMock(return_value=row), commit=AsyncMock())
        bot = NS(id=9, get_me=AsyncMock(return_value=NS(username='ERA_1bot')), edit_message_text=AsyncMock(), send_message=AsyncMock())
        msg = NS(from_user=NS(id=1), chat=NS(id=-1001), text='/leaders_repair important', message_thread_id=42,
            reply_to_message=NS(from_user=NS(id=9), chat=NS(id=-1001), message_thread_id=42, message_id=80), reply=AsyncMock())
        with patch('app.handlers.chat_binding._can_bind', return_value=True), \
             patch('app.services.leaders_topics_service._has_duplicate_thread_route', new=AsyncMock(return_value=False)), \
             patch('app.services.leaders_topics_service._has_duplicate_panel_route', new=AsyncMock(return_value=False)), \
             patch('app.services.leaders_topics_service.panel', new=AsyncMock(return_value=('Panel', None))):
            await repair_leaders_panel(msg, None, NS(leaders_chat_id=-1001, general_chat_id=-1002), session, bot)
        self.assertEqual(json.loads(row.value)['message_state'], 'sent')
        self.assertEqual(json.loads(row.value)['message_id'], 80)
        bot.edit_message_text.assert_awaited_once()
        bot.send_message.assert_not_awaited()
        session.commit.assert_awaited_once()
