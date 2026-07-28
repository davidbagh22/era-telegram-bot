from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.services.audit_service import audit
from app.services.points_service import add_points
from app.utils.constants import ApplicationStatus, ParticipationStatus, Role


@dataclass(frozen=True)
class ApplicationDecision:
    changed: bool
    code: str
    old_status: str | None
    new_status: str | None


async def approve_application(
    session: AsyncSession,
    target: User,
    *,
    actor_id: int | None,
) -> ApplicationDecision:
    if target.application_status == ApplicationStatus.APPROVED:
        return ApplicationDecision(False, "already_approved", target.application_status, target.application_status)
    if target.application_status == ApplicationStatus.REJECTED:
        return ApplicationDecision(False, "already_rejected", target.application_status, target.application_status)

    old = target.application_status
    target.application_status = ApplicationStatus.APPROVED
    target.role = Role.PARTICIPANT
    target.participation_status = ParticipationStatus.NEW_MEMBER
    await add_points(
        session,
        user_id=target.id,
        points=100,
        reason="Регистрация в боте",
        approved_by=actor_id,
        source_type="registration_approval",
        source_id=target.id,
        idempotency_key=f"registration_approval:{target.id}",
    )
    await audit(
        session,
        actor_id=actor_id,
        action="user.approved",
        entity_type="user",
        entity_id=target.id,
        old_value={"application_status": old},
        new_value={"application_status": target.application_status},
    )
    return ApplicationDecision(True, "approved", old, target.application_status)


async def reject_application(
    session: AsyncSession,
    target: User,
    *,
    actor_id: int | None,
    comment: str,
) -> ApplicationDecision:
    if target.application_status == ApplicationStatus.APPROVED:
        return ApplicationDecision(False, "already_approved", target.application_status, target.application_status)
    if target.application_status == ApplicationStatus.REJECTED:
        return ApplicationDecision(False, "already_rejected", target.application_status, target.application_status)

    old = target.application_status
    target.application_status = ApplicationStatus.REJECTED
    await audit(
        session,
        actor_id=actor_id,
        action="user.rejected",
        entity_type="user",
        entity_id=target.id,
        old_value={"application_status": old},
        new_value={"application_status": target.application_status, "comment": comment},
    )
    return ApplicationDecision(True, "rejected", old, target.application_status)
