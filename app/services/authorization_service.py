from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.utils.constants import Role


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str = ""


def active_permissions(user: User | None) -> set[str]:
    return {
        grant.permission
        for grant in (getattr(user, "permission_grants", None) or [])
        if grant.is_active
    }


def is_full_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (
            user
            and user.role == Role.ADMIN
            and not user.is_blocked
            and not user.is_archived
        )
    )


def can_view_people(user: User | None, settings: Settings, telegram_id: int) -> bool:
    if is_full_admin(user, settings, telegram_id):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    return bool(active_permissions(user).intersection({"people.view", "people.manage"}))


def can_manage_people(user: User | None, settings: Settings, telegram_id: int) -> bool:
    if is_full_admin(user, settings, telegram_id):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    return "people.manage" in active_permissions(user)


def can_manage_permissions(
    user: User | None, settings: Settings, telegram_id: int
) -> bool:
    return is_full_admin(user, settings, telegram_id)


async def active_full_admin_count(session: AsyncSession, settings: Settings) -> int:
    admin_conditions = [User.role == Role.ADMIN]
    if settings.admin_ids:
        admin_conditions.append(User.telegram_id.in_(settings.admin_ids))
    return int(
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
                or_(*admin_conditions),
            )
        )
        or 0
    )


async def can_change_role(
    session: AsyncSession,
    *,
    actor: User | None,
    actor_telegram_id: int,
    target: User,
    new_role: Role,
    settings: Settings,
) -> AuthorizationDecision:
    if actor and actor.id == target.id and target.role != new_role.value:
        return AuthorizationDecision(False, "Нельзя менять собственную роль")
    if target.telegram_id in settings.admin_ids and new_role != Role.ADMIN:
        return AuthorizationDecision(
            False, "Основного администратора нельзя понизить из бота"
        )
    if new_role == Role.ADMIN and not can_manage_permissions(
        actor, settings, actor_telegram_id
    ):
        return AuthorizationDecision(
            False, "Назначать админов может только действующий администратор"
        )
    if target.role == Role.ADMIN and new_role != Role.ADMIN:
        if await active_full_admin_count(session, settings) <= 1:
            return AuthorizationDecision(
                False, "Нельзя понизить последнего администратора"
            )
    return AuthorizationDecision(True)


async def can_change_permission(
    *,
    actor: User | None,
    target: User,
) -> AuthorizationDecision:
    if actor and actor.id == target.id:
        return AuthorizationDecision(False, "Нельзя менять собственные права")
    return AuthorizationDecision(True)


async def can_change_access_status(
    session: AsyncSession,
    *,
    actor: User | None,
    target: User,
    settings: Settings,
) -> AuthorizationDecision:
    if actor and actor.id == target.id:
        return AuthorizationDecision(False, "Нельзя изменить собственный доступ")
    if target.telegram_id in settings.admin_ids:
        return AuthorizationDecision(
            False, "Основного администратора нельзя заблокировать или архивировать из бота"
        )
    if target.role == Role.ADMIN and await active_full_admin_count(session, settings) <= 1:
        return AuthorizationDecision(
            False, "Нельзя отключить последнего администратора"
        )
    return AuthorizationDecision(True)
