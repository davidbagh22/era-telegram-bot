import logging
import asyncio
from aiogram import BaseMiddleware, Router
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Update
from app.services.telegram_analytics_service import observe_message, source_targets, mark_coverage_gap, persist_coverage_gap

logger = logging.getLogger(__name__)
router = Router(name='telegram-analytics-observer')


async def _keep_routing(event):
    return UNHANDLED


# Subscribe to all observed update types without consuming business handlers.
router.channel_post.register(_keep_routing)
router.edited_channel_post.register(_keep_routing)
router.edited_message.register(_keep_routing)
router.my_chat_member.register(_keep_routing)


class TelegramAnalyticsMiddleware(BaseMiddleware):
    def __init__(self, session_factory, settings):
        self.session_factory = session_factory
        self.settings = settings

    async def __call__(self, handler, event, data):
        if isinstance(event, Update):
            membership = event.my_chat_member
            if membership and membership.chat.id in source_targets(self.settings).values():
                mark_coverage_gap(membership.chat.id)
                try:
                    from app.database.telegram_analytics import TelegramAnalyticsSource
                    async with self.session_factory() as session:
                        row = await session.get(TelegramAnalyticsSource, membership.chat.id)
                        if row:
                            row.status, row.coverage_since, row.detail = 'unverified', None, 'membership_changed'
                            await session.commit()
                except Exception:
                    logger.exception('Telegram source membership observation failed')
            message = event.channel_post or event.edited_channel_post or event.message or event.edited_message
            if message:
                targets = source_targets(self.settings)
                kind = next((key for key, chat_id in targets.items() if chat_id == message.chat.id), None)
                if kind is None and message.chat.type == 'channel':
                    expected = getattr(self.settings, 'era_channel_username', '').removeprefix('@').casefold()
                    if expected and (message.chat.username or '').casefold() == expected:
                        kind = 'channel'
                        self.settings.era_channel_id = message.chat.id
                if kind:
                    try:
                        # Separate transaction: business handler rollbacks must not lose observations,
                        # and analytics failures must not break registration, games or webhook routing.
                        async with self.session_factory() as session:
                            recorded = await observe_message(session, message, kind=kind)
                            await session.commit()
                            if recorded:
                                logger.info('Telegram analytics observation committed: kind=%s', kind)
                    except Exception:
                        mark_coverage_gap(message.chat.id)
                        logger.exception('Telegram analytics observation failed')
                        await _invalidate_gap(self.session_factory, message.chat.id)
        return await handler(event, data)


from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import Message


class TelegramSentAnalyticsMiddleware(BaseRequestMiddleware):
    """Observe successful channel send/edit results too, deduplicated with channel_post."""
    def __init__(self, session_factory, settings):
        self.session_factory, self.settings = session_factory, settings

    async def __call__(self, make_request, bot, method):
        result = await make_request(bot, method)
        messages = result if isinstance(result, list) else [result]
        for message in messages:
            if not isinstance(message, Message) or message.chat.type != 'channel':
                continue
            targets = source_targets(self.settings)
            expected_username = getattr(self.settings, 'era_channel_username', '').removeprefix('@').casefold()
            matches = message.chat.id == targets.get('channel') or (expected_username and (message.chat.username or '').casefold() == expected_username)
            if matches:
                self.settings.era_channel_id = message.chat.id
                # Do not acquire another DB connection while a sender is holding one.
                # Delivery returns immediately; a bounded task writes after the handler can commit.
                if len(_sent_observations) >= 1000:
                    mark_coverage_gap(message.chat.id)
                    logger.error('Telegram sent-observation queue is full')
                    # Bound acquisition: a sender may still hold a DB connection.
                    await _invalidate_gap(self.session_factory, message.chat.id)
                    continue
                task = asyncio.create_task(self._record(message))
                _sent_observations.add(task)
                task.add_done_callback(_sent_observations.discard)
        return result


    async def _record(self, message):
        try:
            async with self.session_factory() as session:
                await observe_message(session, message, kind='channel')
                await session.commit()
        except Exception:
            mark_coverage_gap(message.chat.id)
            logger.exception('Sent channel analytics observation failed')
            await _invalidate_gap(self.session_factory, message.chat.id)


_sent_observations = set()


async def drain_sent_observations():
    if _sent_observations:
        done, pending = await asyncio.wait(list(_sent_observations), timeout=10)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def _invalidate_gap(session_factory, chat_id):
    mark_coverage_gap(chat_id)
    try:
        async with asyncio.timeout(2):
            async with session_factory() as session:
                await persist_coverage_gap(session, chat_id)
                await session.commit()
    except Exception:
        # DB downtime cannot be papered over: the local pending marker keeps reports
        # unavailable until the source probe persists a fresh continuous boundary.
        logger.exception('Telegram coverage invalidation pending')
