import logging
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import Settings

logger = logging.getLogger(__name__)


class SubscriptionCheckError(RuntimeError):
    pass


class SubscriptionConfigurationError(SubscriptionCheckError):
    pass


class SubscriptionBotAccessError(SubscriptionCheckError):
    pass


def channel_target(settings: Settings) -> int | str | None:
    if settings.era_channel_id not in (None, ""):
        return settings.era_channel_id
    path = urlparse(settings.era_channel_url).path.strip("/")
    if path and not path.startswith("+") and path != "joinchat":
        return f"@{path}"
    return None


async def is_channel_member(bot: Bot, telegram_id: int, settings: Settings) -> bool:
    if telegram_id in settings.admin_ids:
        return True
    target = channel_target(settings)
    if target is None:
        logger.error(
            "ERA_CHANNEL_ID is required for a private channel; subscription gate is closed"
        )
        raise SubscriptionConfigurationError(
            "ERA_CHANNEL_ID is required for private channel subscription checks"
        )
    try:
        member = await bot.get_chat_member(target, telegram_id)
        return member.status not in {"left", "kicked"}
    except TelegramForbiddenError as exc:
        logger.exception(
            "Subscription check failed. Bot has no access to the ERA channel."
        )
        raise SubscriptionBotAccessError(
            "Bot must be an administrator of the ERA channel"
        ) from exc
    except TelegramBadRequest as exc:
        logger.exception(
            "Subscription check failed. Check ERA_CHANNEL_ID and bot channel permissions."
        )
        raise SubscriptionBotAccessError(
            "Could not verify subscription. Check ERA_CHANNEL_ID and bot permissions"
        ) from exc
