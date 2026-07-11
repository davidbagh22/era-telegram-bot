import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent, Message

from app.config import Settings
from app.handlers import chat, chat_binding, emergency, leader_event_photo, registration, start
from app.handlers.admin import router as admin_router
from app.handlers.leader import router as leader_router
from app.handlers.participant import router as participant_router
from app.middlewares.auth import DatabaseAuthMiddleware
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

    subscription = SubscriptionMiddleware(settings)
    participant_router.message.outer_middleware(subscription)
    participant_router.callback_query.outer_middleware(subscription)
    leader_event_photo.router.message.outer_middleware(subscription)
    leader_event_photo.router.callback_query.outer_middleware(subscription)
    leader_router.message.outer_middleware(subscription)
    leader_router.callback_query.outer_middleware(subscription)

    dispatcher.include_routers(
        emergency.router,
        start.router,
        registration.router,
        admin_router,
        leader_event_photo.router,
        leader_router,
        participant_router,
        chat_binding.router,
        chat.router,
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
