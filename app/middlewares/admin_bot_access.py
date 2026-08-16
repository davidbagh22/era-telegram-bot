from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.models import User
from app.utils.constants import Role


def has_admin_bot_access(
    user: User | None,
    settings: Settings,
    telegram_id: int,
) -> bool:
    """Keep bot-native admin routes admin-only.

    Delegated permissions are enforced by the Mini App/API per capability.
    They must not make a user admin-equivalent for the legacy Telegram admin
    router, where older handlers share broad guards.
    """
    return bool(
        telegram_id in settings.admin_ids
        or (
            user
            and user.role == Role.ADMIN
            and not user.is_blocked
            and not user.is_archived
        )
    )


class AdminBotAccessFilter(Filter):
    """Skip the whole legacy admin router for non-admin users.

    This must be a router filter, not an outer middleware. An outer middleware
    runs before child-handler matching and therefore intercepts every private
    participant callback merely because the admin router is ordered first.
    Returning False from a root filter leaves the update unhandled by the
    admin router so participant/leader routers can process their own buttons.
    """

    async def __call__(
        self,
        event: Message | CallbackQuery,
        user: User | None,
        settings: Settings,
    ) -> bool:
        return bool(
            event.from_user
            and has_admin_bot_access(user, settings, event.from_user.id)
        )
