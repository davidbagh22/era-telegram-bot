from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting, AuditLog, User
from app.services.audit_service import audit
from app.services.digital_engagement_service import award_profile_completion
from app.services.points_service import add_points
from app.services.referral_service import award_registration_referral
from app.utils.constants import ApplicationStatus, ParticipationStatus, Role


@dataclass(frozen=True)
class ApplicationDecision:
    changed: bool
    code: str
    old_status: str | None
    new_status: str | None


APPLICATION_REVIEW_ACTIONS = ('user.registered', 'user.resubmitted', 'user.approved', 'user.rejected', 'user.needs_info')


async def application_review_version(session: AsyncSession, user_id: int) -> int:
    await session.flush()
    return int(await session.scalar(select(func.max(AuditLog.id)).where(
        AuditLog.entity_type == 'user', AuditLog.entity_id == user_id,
        AuditLog.action.in_(APPLICATION_REVIEW_ACTIONS))) or 0)


async def stage_application_notice(session: AsyncSession, target: User, *, text: str) -> str:
    """Same-transaction pending intent; Telegram uses the shared delivery ledger."""
    import json
    revision = await application_review_version(session, target.id)
    key = f'application-notice:{target.id}:{revision}'
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        session.add(AppSetting(key=key, value=json.dumps({
            'user_id': target.id, 'telegram_id': target.telegram_id,
            'status': target.application_status, 'text': text,
        }, ensure_ascii=False)))
    return key


async def deliver_application_notices(bot, settings, session_factory, *, only_key: str | None = None) -> None:
    """Retry definite failures; uncertain deliveries remain for operator review."""
    import json
    from app.keyboards.participant import main_inline_keyboard
    from app.services.notification_service import safe_send_once
    async with session_factory() as session:
        query = select(AppSetting.key).where(AppSetting.key.like('application-notice:%')).order_by(AppSetting.key).limit(50)
        if only_key:
            query = select(AppSetting.key).where(AppSetting.key == only_key)
        keys = list((await session.scalars(query)).all())
    for key in keys:
        async with session_factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            if row is None:
                continue
            payload = json.loads(row.value) if isinstance(row.value, str) else row.value
            target = await session.scalar(select(User).where(User.id == payload['user_id']).with_for_update())
            if (not target or target.is_archived or target.is_blocked
                or target.telegram_id != payload['telegram_id'] or target.application_status != payload['status']
                or await application_review_version(session, target.id) != int(key.rsplit(':', 1)[-1])):
                await session.delete(row)
                await session.commit()
                continue
            result = await safe_send_once(bot, settings, target.telegram_id, payload['text'],
                delivery_key=key, notification_type='application_decision', parse_mode=None,
                reply_markup=main_inline_keyboard(miniapp_url=settings.effective_miniapp_url)
                    if payload['status'] == ApplicationStatus.APPROVED else None)
            permanent_failure = result.status == 'failed' and (
                result.error_code not in {'telegram_retry_after', 'delivery_ledger_unavailable', 'delivery_in_flight', 'delivery_retry_ledger_failed'}
                or result.attempt_count >= 3)
            if permanent_failure or result.status in {'sent', 'blocked', 'unreachable', 'uncertain', 'skipped'}:
                await session.delete(row)
                await session.commit()


async def approve_application(
    session: AsyncSession,
    target: User,
    *,
    actor_id: int | None,
) -> ApplicationDecision:
    await session.flush()
    await session.refresh(target, attribute_names=['application_status'], with_for_update=True)
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
    # Registration requires the full participant profile. Award the approved
    # profile-completion rule only when the persisted User fields really
    # satisfy the completeness check; idempotency prevents re-approval/retry
    # from paying twice and the global monthly digital cap still applies.
    await award_profile_completion(session, target, profile_version="v1")

    # Referral stage 1 is tied to the authoritative application decision.
    # Opening/joining a chat must never produce referral points. The referral
    # service remains idempotent, so retries or repeated approval handlers
    # cannot pay this stage twice.
    await award_registration_referral(session, invitee_user_id=target.id)

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
    await session.flush()
    await session.refresh(target, attribute_names=['application_status'], with_for_update=True)
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


async def request_more_info(
    session: AsyncSession,
    target: User,
    *,
    actor_id: int | None,
    comment: str,
) -> ApplicationDecision:
    await session.flush()
    await session.refresh(target, attribute_names=['application_status'], with_for_update=True)
    if target.application_status == ApplicationStatus.APPROVED:
        return ApplicationDecision(False, "already_approved", target.application_status, target.application_status)
    if target.application_status == ApplicationStatus.REJECTED:
        return ApplicationDecision(False, "already_rejected", target.application_status, target.application_status)

    old = target.application_status
    target.application_status = ApplicationStatus.NEEDS_INFO
    await audit(
        session,
        actor_id=actor_id,
        action="user.needs_info",
        entity_type="user",
        entity_id=target.id,
        old_value={"application_status": old},
        new_value={"application_status": target.application_status, "comment": comment},
    )
    return ApplicationDecision(True, "needs_info", old, target.application_status)
