from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, AuditLog, Direction, User
from app.services.audit_service import audit
from app.utils.constants import ApplicationStatus


def is_media_chair(user: User | None, settings: Settings) -> bool:
    return bool(user and getattr(settings, "era_chair_user_id", None) and user.id == settings.era_chair_user_id
                and not user.is_blocked and not user.is_archived
                and user.application_status == ApplicationStatus.APPROVED)


async def require_chair(session: AsyncSession, actor: User, settings: Settings) -> User:
    actor = await session.scalar(select(User).where(User.id == actor.id)
                                  .execution_options(populate_existing=True))
    if not is_media_chair(actor, settings):
        raise ValueError("media_chair_required")
    return actor


async def leadership_state(session: AsyncSession, *, lock: bool = False) -> tuple[Direction, int]:
    query = select(Direction).where(Direction.name == "Медиа")
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    direction = await session.scalar(query)
    if direction is None:
        raise ValueError("media_direction_missing")
    revision = int(await session.scalar(select(func.max(AuditLog.id)).where(
        AuditLog.action == "media.leader_changed", AuditLog.entity_id == direction.id)) or 0)
    return direction, revision


async def leader_target(session: AsyncSession, telegram_id: int) -> User:
    if not 0 < telegram_id <= 2**63 - 1:
        raise ValueError("media_registered_active_target_required")
    target = await session.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update()
                                  .execution_options(populate_existing=True))
    if (target is None or target.is_blocked or target.is_archived
            or target.application_status != ApplicationStatus.APPROVED):
        raise ValueError("media_registered_active_target_required")
    return target


async def change_leader(session: AsyncSession, actor: User, settings: Settings, *,
                        target_telegram_id: int | None, expected_revision: int) -> User | None:
    actor = await require_chair(session, actor, settings)
    # Match membership's User → Direction lock order to avoid appointment/join deadlocks.
    target = await leader_target(session, target_telegram_id) if target_telegram_id is not None else None
    direction, revision = await leadership_state(session, lock=True)
    if revision != expected_revision:
        raise ValueError("media_leader_stale_confirmation")
    target_id = target.id if target else None
    if direction.leader_id == target_id:
        return target
    previous = direction.leader_id
    if previous is not None:
        from app.services.media_scope_service import revoke_editor_grants
        await revoke_editor_grants(session, previous, direction.id, actor_id=actor.id, include_delegations=True)
    direction.leader_id = target_id
    await audit(session, actor_id=actor.id, action="media.leader_changed", entity_type="direction",
                entity_id=direction.id, old_value={"leader_id": previous}, new_value={"leader_id": target_id})
    await session.flush()
    return target


async def set_invitation(session: AsyncSession, actor: User, settings: Settings, *, enabled: bool) -> None:
    from app.services.media_service import DEFAULT_MEDIA_CONFIG, MEDIA_SETTINGS_KEY
    actor = await require_chair(session, actor, settings)
    # Serialize with leadership changes and other invitation settings updates.
    await leadership_state(session, lock=True)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == MEDIA_SETTINGS_KEY).with_for_update())
    config = {**DEFAULT_MEDIA_CONFIG, **(row.value if row and isinstance(row.value, dict) else {})}
    old = bool(config.get("join_enabled", True))
    config["join_enabled"] = bool(enabled)
    if row is None:
        session.add(AppSetting(key=MEDIA_SETTINGS_KEY, value=config, updated_by=actor.id))
    else:
        row.value, row.updated_by = config, actor.id
    await audit(session, actor_id=actor.id, action="media.invitation_changed", entity_type="direction",
                old_value={"enabled": old}, new_value={"enabled": bool(enabled)})
    await session.flush()
