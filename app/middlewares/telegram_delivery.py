"""Shared transport pacing; Telegram RetryAfter remains authoritative.

Limits: https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this
One running Bot owns one limiter. Production runs a single instance.
"""
import asyncio
import time

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramRetryAfter

MESSAGE_METHODS = {
    'sendMessage', 'sendPhoto', 'sendVideo', 'sendAnimation', 'sendAudio', 'sendDocument',
    'sendVoice', 'sendVideoNote', 'sendSticker', 'sendMediaGroup', 'sendPoll', 'sendDice',
    'copyMessage', 'copyMessages', 'forwardMessage', 'forwardMessages',
    'editMessageText', 'editMessageCaption', 'editMessageMedia', 'editMessageReplyMarkup',
}


class TelegramDeliveryMiddleware(BaseRequestMiddleware):
    def __init__(self, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.clock, self.sleep = clock, sleep
        self.lock = asyncio.Lock()
        self.global_next = self.cooldown_until = 0.0
        self.global_interval = self.base_interval = 1 / 25
        self.chat_next = {}

    async def acquire(self, chat_id, units=1):
        interval = 1.05 if isinstance(chat_id, int) and chat_id > 0 else 3.1
        while True:
            async with self.lock:
                now = self.clock()
                due = max(self.global_next, self.cooldown_until, self.chat_next.get(chat_id, 0.0))
                delay = due - now
                if delay <= 0:
                    self.global_next = now + self.global_interval * units
                    if chat_id is not None:
                        self.chat_next[chat_id] = now + interval * units
                    # Keep only live cooldowns; never retain a permanent audience map.
                    if len(self.chat_next) > 2048:
                        self.chat_next = {key: value for key, value in self.chat_next.items() if value > now}
                    return
            # A waiting group never holds the global lock or blocks other chats.
            await self.sleep(min(delay, 30))

    async def __call__(self, make_request, bot, method):
        if method.__api_method__ not in MESSAGE_METHODS:
            return await make_request(bot, method)
        grouped = getattr(method, 'media', None) or getattr(method, 'message_ids', None)
        units = len(grouped) if isinstance(grouped, (list, tuple)) and grouped else 1
        await self.acquire(getattr(method, 'chat_id', None), units)
        try:
            result = await make_request(bot, method)
        except TelegramRetryAfter as exc:
            async with self.lock:
                self.cooldown_until = max(self.cooldown_until, self.clock() + max(0, exc.retry_after))
                self.global_interval = min(0.5, self.global_interval * 2)
            # Existing durable sender owns bounded retries and delivery receipts.
            raise
        async with self.lock:
            self.global_interval = max(self.base_interval, self.global_interval * 0.98)
        return result
