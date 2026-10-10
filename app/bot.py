from app.handlers.leaders_broadcast import router as leaders_broadcast_router
from app.handlers.leaders_workspace import router as leaders_workspace_router
from app.handlers.pulse_private import router as pulse_private_router
from app.handlers.book_club import router as book_club_router 
from app.handlers.era_game_room import router as era_game_room_router
from app.handlers.era_leisure import router as era_leisure_router
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent, Message

from app.config import Settings
from app.handlers import (
    chat,
    chat_binding,
    chat_faq,
    chat_unlock,
    emergency,
    general_chat_navigation,
    leader_event_photo,
    media_chat_files,
    referrals,
    registration,
    start,
)
from app.handlers.admin import router as admin_router
from app.handlers.leader import router as leader_router
from app.handlers.leader_chat_workcenter import router as leader_chat_workcenter_router
from app.handlers.participant import router as participant_router
from app.middlewares.auth import DatabaseAuthMiddleware
from app.middlewares.faq_context import FaqContextMiddleware
from app.middlewares.community_identity import CommunityIdentityMiddleware
from app.middlewares.legacy_chat_permission_recovery import LegacyChatPermissionRecoveryMiddleware
from app.middlewares.legacy_keyboard_cleanup import LegacyKeyboardCleanupMiddleware
from app.middlewares.media_chat_activity import MediaChatActivityMiddleware
from app.middlewares.referral_chat_reward import ReferralChatRewardMiddleware
from app.middlewares.subscription_check import SubscriptionMiddleware
from app.services.ai_service import AIService
from app.utils import texts

logger = logging.getLogger(__name__)


class _NoopRedisCompat:
    """Minimal Redis-shaped adapter used by webapp recovery logic in memory mode."""

    async def exists(self, *_args, **_kwargs):
        return True

    async def flushdb(self, *_args, **_kwargs):
        return True

    async def set(self, *_args, **_kwargs):
        return True


class _MemoryStorageCompat(MemoryStorage):
    """In-memory FSM storage that keeps the legacy webapp Redis hook harmless."""

    def __init__(self) -> None:
        super().__init__()
        self.redis = _NoopRedisCompat()


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )


def create_dispatcher(settings: Settings, session_factory) -> Dispatcher:
    storage_mode = os.getenv("FSM_STORAGE_MODE", "redis").strip().lower()
    if storage_mode == "memory":
        storage = _MemoryStorageCompat()
        logger.warning(
            "FSM_STORAGE_MODE=memory: using in-memory FSM storage because external Redis is unavailable"
        )
    else:
        storage = RedisStorage.from_url(
            settings.redis_url,
            connection_kwargs={
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
                "health_check_interval": 30,
            },
        )

    dispatcher = Dispatcher(storage=storage, events_isolation=storage.create_isolation() if isinstance(storage, RedisStorage) else SimpleEventIsolation())
    dispatcher["settings"] = settings
    dispatcher["ai_service"] = AIService(settings)
    dispatcher.update.outer_middleware(DatabaseAuthMiddleware(session_factory))
    dispatcher.callback_query.outer_middleware(FaqContextMiddleware())
    # Repair historical per-user general-chat mutes as soon as any Telegram
    # account contacts the bot privately. This also covers people absent from
    # the database, which the periodic DB-backed sweep cannot discover.
    dispatcher.update.outer_middleware(LegacyChatPermissionRecoveryMiddleware(settings))
    dispatcher.update.outer_middleware(LegacyKeyboardCleanupMiddleware())

    subscription = SubscriptionMiddleware(settings)
    participant_router.message.outer_middleware(subscription)
    participant_router.callback_query.outer_middleware(subscription)
    leader_event_photo.router.message.outer_middleware(subscription)
    leader_event_photo.router.callback_query.outer_middleware(subscription)
    leader_router.message.outer_middleware(subscription)
    leader_router.callback_query.outer_middleware(subscription)

    referral_chat_reward = ReferralChatRewardMiddleware()
    chat.router.chat_join_request.outer_middleware(referral_chat_reward)
    chat.router.message.outer_middleware(referral_chat_reward)

    community_identity = CommunityIdentityMiddleware()
    chat.router.chat_join_request.outer_middleware(community_identity)
    chat.router.message.outer_middleware(community_identity)

    media_chat_activity = MediaChatActivityMiddleware()
    media_chat_files.router.message.outer_middleware(media_chat_activity)
    chat.router.message.outer_middleware(media_chat_activity)

    dispatcher.include_routers(
        # Referral deep links are a specialised /start form and must be handled
        # before the emergency catch-all /start router, otherwise ref_<code>
        # is discarded before registration begins.
        referrals.router,
        leaders_broadcast_router,
        leaders_workspace_router,
        pulse_private_router,
        book_club_router, 
        era_game_room_router,
        era_leisure_router,
        leader_chat_workcenter_router,
        emergency.router,
        chat_unlock.router,
        start.router,
        registration.router,
        admin_router,
        leader_event_photo.router,
        leader_router,
        participant_router,
        chat_binding.router,
        media_chat_files.router,
        general_chat_navigation.router,
        chat.router,
        chat_faq.router,
    )

    @dispatcher.error()
    async def global_error_handler(event: ErrorEvent) -> bool:
        logger.exception("Unhandled update error", exc_info=event.exception)
        update = event.update
        message = update.message or (
            update.callback_query.message if update.callback_query else None
        )
        if isinstance(message, Message):
            await message.answer(texts.UNEXPECTED_ERROR)
        return True

    return dispatcher
