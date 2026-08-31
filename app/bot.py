import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
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
from app.handlers.participant import router as participant_router
from app.middlewares.auth import DatabaseAuthMiddleware
from app.middlewares.community_identity import CommunityIdentityMiddleware
from app.middlewares.legacy_chat_permission_recovery import LegacyChatPermissionRecoveryMiddleware
from app.middlewares.legacy_keyboard_cleanup import LegacyKeyboardCleanupMiddleware
from app.middlewares.media_chat_activity import MediaChatActivityMiddleware
from app.middlewares.referral_chat_reward import ReferralChatRewardMiddleware
from app.middlewares.subscription_check import SubscriptionMiddleware
from app.services.ai_service import AIService
from app.utils import texts

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )


def create_dispatcher(settings: Settings, session_factory) -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url)
    dispatcher = Dispatcher(storage=storage)
    dispatcher["settings"] = settings
    dispatcher["ai_service"] = AIService(settings)
    dispatcher.update.outer_middleware(DatabaseAuthMiddleware(session_factory))
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
        emergency.router,
        chat_unlock.router,
        start.router,
        registration.router,
        referrals.router,
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
