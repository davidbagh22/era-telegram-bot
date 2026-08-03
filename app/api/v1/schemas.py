from __future__ import annotations

from pydantic import BaseModel

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import active_permissions, is_full_admin
from app.utils.constants import PRIVILEGED_ROLES


class MiniAppUserSummary(BaseModel):
    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    role: str
    application_status: str
    is_blocked: bool
    is_leader: bool
    is_admin: bool
    permissions: list[str]


def summarize_user(user: User, settings: Settings) -> MiniAppUserSummary:
    return MiniAppUserSummary(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        application_status=user.application_status,
        is_blocked=user.is_blocked,
        is_leader=user.role in PRIVILEGED_ROLES,
        is_admin=is_full_admin(user, settings, user.telegram_id),
        permissions=sorted(active_permissions(user)),
    )
