from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, PermissionGrant, PortfolioItem, User, UserBadge
from app.database.socials import SocialLink
from app.services.audit_service import audit
from app.services.authorization_service import (
    AuthorizationDecision,
    can_change_access_status,
    can_change_permission,
    can_change_role,
)
from app.services.points_service import add_points, add_portfolio_item, make_idempotency_key, total_points
from app.utils.constants import PERMISSIONS, Role

# People directory: the Mini App equivalent of the bot's `admin:participants`
# inline-keyboard list (app/handlers/admin/rights_block6.py), but paginated
# and searchable instead of paging through Telegram messages.
DEFAULT_USER_SEARCH_LIMIT = 30
MAX_USER_SEARCH_LIMIT = 100
MAX_POINTS_ADJUSTMENT = 10_000


async def search_users(
    session: AsyncSession,
    *,
    query: str = "",
    role: str | None = None,
    include_archived: bool = False,
    limit: int = DEFAULT_USER_SEARCH_LIMIT,
    offset: int = 0,
) -> tuple[list[User], int]:
    """Returns (page of matching users, total matching count)."""
    limit = max(1, min(limit, MAX_USER_SEARCH_LIMIT))
    conditions = []
    if not include_archived:
        # Some pre-migration production rows can still have NULL here. NULL
        # means "not archived", so do not silently lose an existing participant
        # from the admin directory just because the old row predates the bool default.
        conditions.append(User.is_archived.is_not(True))
    if role:
        conditions.append(User.role == role)
    stripped = query.strip()
    if stripped:
        like = f"%{stripped}%"
        name_match = [User.first_name.ilike(like), User.last_name.ilike(like), User.username.ilike(like)]
        digits = stripped.lstrip("+")
        if digits.isdigit():
            name_match.append(User.telegram_id == int(digits))
        conditions.append(or_(*name_match))

    base = select(User).where(*conditions) if conditions else select(User)
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await session.scalars(base.order_by(User.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return list(rows), total


async def user_badges(session: AsyncSession, user_id: int) -> list[Badge]:
    return list(
        (
            await session.scalars(
                select(Badge)
                .join(UserBadge, UserBadge.badge_id == Badge.id)
                .where(UserBadge.user_id == user_id)
                .order_by(Badge.name)
            )
        ).all()
    )


async def available_badges(session: AsyncSession, user_id: int) -> list[Badge]:
    """Badges not yet awarded to this user — mirrors the bot's badge picker,
    which only ever shows badges the participant doesn't already have."""
    owned = set(
        (await session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user_id))).all()
    )
    all_badges = (await session.scalars(select(Badge).order_by(Badge.name))).all()
    return [badge for badge in all_badges if badge.id not in owned]


async def portfolio_count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(PortfolioItem).where(PortfolioItem.user_id == user_id)
        )
        or 0
    )


async def social_links(session: AsyncSession, user_id: int) -> list[SocialLink]:
    return list(
        (
            await session.scalars(
                select(SocialLink)
                .where(SocialLink.user_id == user_id, SocialLink.is_active.is_(True))
                .order_by(SocialLink.platform)
            )
        ).all()
    )


def active_permission_set(target: User) -> set[str]:
    return {grant.permission for grant in (getattr(target, "permission_grants", None) or []) if grant.is_active}


async def change_role(
    session: AsyncSession,
    *,
    actor: User | None,
    actor_telegram_id: int,
    target: User,
    new_role: Role,
    settings: Settings,
) -> AuthorizationDecision:
    decision = await can_change_role(
        session,
        actor=actor,
        actor_telegram_id=actor_telegram_id,
        target=target,
        new_role=new_role,
        settings=settings,
    )
    if not decision.allowed:
        return decision
    old_role = target.role
    target.role = new_role.value
    await audit(
        session,
        actor_id=actor.id if actor else None,
        action="user.role_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={"role": old_role},
        new_value={"role": new_role.value},
    )
    return decision


async def set_blocked(
    session: AsyncSession, *, actor: User | None, target: User, settings: Settings, blocked: bool
) -> AuthorizationDecision:
    decision = await can_change_access_status(session, actor=actor, target=target, settings=settings)
    if not decision.allowed:
        return decision
    target.is_blocked = blocked
    await audit(
        session,
        actor_id=actor.id if actor else None,
        action=f"user.{'block' if blocked else 'unblock'}",
        entity_type="user",
        entity_id=target.id,
    )
    return decision


async def set_archived(
    session: AsyncSession, *, actor: User | None, target: User, settings: Settings, archived: bool
) -> AuthorizationDecision:
    decision = await can_change_access_status(session, actor=actor, target=target, settings=settings)
    if not decision.allowed:
        return decision
    if archived:
        target.is_archived = True
        target.archived_at = datetime.now().astimezone()
        target.archived_by = actor.id if actor else None
        action = "user.archive"
    else:
        target.is_archived = False
        target.archived_at = None
        target.archived_by = None
        action = "user.unarchive"
    await audit(session, actor_id=actor.id if actor else None, action=action, entity_type="user", entity_id=target.id)
    return decision


async def toggle_permission(
    session: AsyncSession, *, actor: User | None, target: User, permission: str
) -> tuple[AuthorizationDecision, bool]:
    """Returns (decision, enabled_after_toggle) — the second value is only
    meaningful when decision.allowed is True."""
    if permission not in PERMISSIONS:
        return AuthorizationDecision(False, "unknown_permission"), False
    decision = await can_change_permission(actor=actor, target=target)
    if not decision.allowed:
        return decision, False
    grant = await session.scalar(
        select(PermissionGrant).where(
            PermissionGrant.user_id == target.id,
            PermissionGrant.permission == permission,
            PermissionGrant.scope_type == "global",
            PermissionGrant.scope_id == 0,
        )
    )
    if grant:
        grant.is_active = not grant.is_active
        enabled = grant.is_active
    else:
        session.add(
            PermissionGrant(
                user_id=target.id,
                permission=permission,
                scope_type="global",
                scope_id=0,
                granted_by=actor.id if actor else target.id,
            )
        )
        enabled = True
    await audit(
        session,
        actor_id=actor.id if actor else None,
        action="user.permission_changed",
        entity_type="user",
        entity_id=target.id,
        new_value={"permission": permission, "enabled": enabled},
    )
    return decision, enabled


async def award_points(
    session: AsyncSession,
    *,
    target: User,
    amount: int,
    reason: str,
    approved_by_id: int | None,
) -> int:
    """Direct admin points adjustment (positive awards, negative deducts).
    Returns the user's new balance. Mirrors
    app/handlers/admin/user_profile_block3_safe.py's points flow — amount
    range and non-empty reason are validated by the API layer before this
    is called, same rule (`-10000..10000`, excluding zero) as the bot."""
    seed = datetime.now().timestamp()
    await add_points(
        session,
        user_id=target.id,
        points=amount,
        reason=reason,
        approved_by=approved_by_id,
        source_type="manual_points",
        source_id=target.id,
        idempotency_key=make_idempotency_key("manual_points", target.id, amount, reason, seed, approved_by_id),
    )
    return await total_points(session, target.id)


async def award_badge(
    session: AsyncSession, *, target: User, badge: Badge, reason: str, awarded_by_id: int | None
) -> bool:
    """Returns False (no-op, already owned) or True (awarded)."""
    exists = await session.scalar(
        select(UserBadge).where(UserBadge.user_id == target.id, UserBadge.badge_id == badge.id)
    )
    if exists:
        return False
    session.add(UserBadge(user_id=target.id, badge_id=badge.id, reason=reason, awarded_by=awarded_by_id))
    await add_portfolio_item(
        session, user_id=target.id, title=badge.name, item_type="badge", description=reason, issued_by=awarded_by_id
    )
    return True
