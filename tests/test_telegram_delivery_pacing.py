import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import AnswerCallbackQuery, SendMessage

from app.middlewares.telegram_delivery import TelegramDeliveryMiddleware


class PacingTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0.0
        self.delays = []
        async def sleep(delay):
            self.delays.append(delay)
            self.now += delay
        self.limiter = TelegramDeliveryMiddleware(clock=lambda: self.now, sleep=sleep)

    async def test_private_and_group_chats_have_distinct_pacing(self):
        await self.limiter.acquire(11)
        await self.limiter.acquire(11)
        assert self.delays == [1.05]
        self.now = 10
        self.delays.clear()
        await self.limiter.acquire(-1001)
        await self.limiter.acquire(-1001)
        assert len(self.delays) == 1
        self.assertAlmostEqual(self.delays[0], 3.1)

    async def test_different_chats_share_global_budget_and_callbacks_stay_responsive(self):
        await self.limiter.acquire(11)
        await self.limiter.acquire(22)
        assert self.delays == [0.04]
        request = AsyncMock(return_value=True)
        await self.limiter(request, SimpleNamespace(), AnswerCallbackQuery(callback_query_id='callback'))
        assert len(self.delays) == 1
        request.assert_awaited_once()

    async def test_retry_after_updates_shared_cooldown_without_blind_retry(self):
        method = SendMessage(chat_id=11, text='test')
        request = AsyncMock(side_effect=TelegramRetryAfter(method=method, message='flood', retry_after=7))
        with self.assertRaises(TelegramRetryAfter):
            await self.limiter(request, SimpleNamespace(), method)
        request.assert_awaited_once()
        assert self.limiter.global_interval == 0.08
        await self.limiter.acquire(22)
        assert self.delays == [7]
        request.side_effect = None
        request.return_value = True
        await self.limiter(request, SimpleNamespace(), SendMessage(chat_id=33, text='test'))
        assert 0.04 < self.limiter.global_interval < 0.08

    async def test_sleeping_group_does_not_hold_the_global_lock(self):
        self.now = 10
        await self.limiter.acquire(-1001)
        waiting, release = asyncio.Event(), asyncio.Event()
        async def sleep(delay):
            waiting.set()
            await release.wait()
            self.now += delay
        self.limiter.sleep = sleep
        task = asyncio.create_task(self.limiter.acquire(-1001))
        await waiting.wait()
        self.now += 0.1
        await asyncio.wait_for(self.limiter.acquire(22), 0.5)
        release.set()
        await asyncio.wait_for(task, 0.5)
