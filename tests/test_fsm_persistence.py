"""FSM persistence across clients, using isolated real Redis keys in CI."""
import inspect
import os
from uuid import uuid4

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

from app import webapp


def test_startup_never_flushes_user_dialogues():
    assert '.flushdb(' not in inspect.getsource(webapp)


def test_redis_retains_dialogue_across_client_restart():
    import asyncio

    async def scenario():
        url = os.getenv('FSM_TEST_REDIS_URL')
        if not url:
            pytest.skip('Real Redis required; CI supplies FSM_TEST_REDIS_URL')
        builder = DefaultKeyBuilder(prefix='era-fsm-test:' + uuid4().hex)
        key = StorageKey(bot_id=1, chat_id=123, user_id=456)
        first = RedisStorage.from_url(url, key_builder=builder)
        second = RedisStorage.from_url(url, key_builder=builder)
        try:
            await first.set_state(key, 'EventWizard:date')
            await first.set_data(key, {'title': 'Test event', 'step': 3})
            await first.close()
            assert await second.get_state(key) == 'EventWizard:date'
            assert await second.get_data(key) == {'title': 'Test event', 'step': 3}
        finally:
            await second.set_state(key, None)
            await second.set_data(key, {})
            await second.close()
    asyncio.run(scenario())
