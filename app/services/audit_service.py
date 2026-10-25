from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, ProjectMember


async def _dispatch_verified_activity_side_effect(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
) -> None:
    """Bridge verified domain actions to secondary rewards in the same transaction.

    Audit remains the immutable record, while this tiny dispatcher prevents the
    referral economy from depending on UI/API entry points. A project
    contribution can be confirmed from any authorized surface and still counts
    as the referred participant's first verified ERA activity.
    """
    if (
        action != "project.member.contribution_confirmed"
        or entity_type != "project_member"
        or entity_id is None
    ):
        return

    member = await session.get(ProjectMember, entity_id)
    if member is None or member.contribution_status != "confirmed":
        return

    # Local import avoids making the generic audit module part of the referral
    # service import graph. The referral service owns idempotency and the hard
    # +100 per-invitee cap, so event/project confirmations cannot pay twice.
    from app.services.referral_service import award_first_activity_referral

    await award_first_activity_referral(
        session,
        invitee_user_id=member.user_id,
    )


async def audit(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
        )
    )
    await _dispatch_verified_activity_side_effect(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
