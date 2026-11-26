"""Expert platform (#616) service — invites, suggestions, published catalog.

No outbound Telegram sends, emails, or article workflows in this slice.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.expert_models import (
    ExpertInvite,
    ExpertInvitePurpose,
    ExpertInviteState,
    ExpertProfile,
    ExpertProfileStatus,
    ExpertSuggestion,
    ExpertSuggestionStatus,
)
from app.database.models import User

DEFAULT_INVITE_TTL_HOURS = 72
SUGGESTION_RATE_LIMIT = 5
SUGGESTION_RATE_WINDOW = timedelta(hours=24)
TOKEN_BYTES = 32


class ExpertPlatformError(ValueError):
    """Domain error with a stable machine-readable code in str(self)."""


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_published_expert(profile: ExpertProfile) -> dict[str, object]:
    """Public card only — never include draft or private fields."""
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "title": profile.title,
        "organization": profile.organization,
        "bio_short": profile.bio_short,
        "topics": profile.topics,
        "published_at": profile.published_at.isoformat() if profile.published_at else None,
    }


def serialize_suggestion_ack(suggestion: ExpertSuggestion) -> dict[str, object]:
    """Participant acknowledgement — contact_private intentionally omitted."""
    return {
        "id": suggestion.id,
        "expert_name": suggestion.expert_name,
        "field": suggestion.field,
        "status": suggestion.status,
        "submitted_at": suggestion.submitted_at.isoformat() if suggestion.submitted_at else None,
    }


@dataclass(frozen=True)
class CreatedInvite:
    invite: ExpertInvite
    token: str
    profile: ExpertProfile


async def create_invite(
    session: AsyncSession,
    *,
    admin: User,
    display_name: str,
    purpose: str = ExpertInvitePurpose.PROFILE,
    ttl_hours: int = DEFAULT_INVITE_TTL_HOURS,
    title: str | None = None,
    organization: str | None = None,
    bio_short: str | None = None,
    topics: str | None = None,
    suggestion_id: int | None = None,
    audit_note: str | None = None,
    mark_sent: bool = False,
) -> CreatedInvite:
    name = (display_name or "").strip()
    if not name:
        raise ExpertPlatformError("display_name_required")
    if purpose not in {
        ExpertInvitePurpose.PROFILE,
        ExpertInvitePurpose.ARTICLE,
        ExpertInvitePurpose.EVENT,
    }:
        raise ExpertPlatformError("invalid_purpose")
    if ttl_hours < 1 or ttl_hours > 24 * 30:
        raise ExpertPlatformError("invalid_ttl")

    if suggestion_id is not None:
        suggestion = await session.get(ExpertSuggestion, suggestion_id)
        if suggestion is None:
            raise ExpertPlatformError("suggestion_not_found")

    profile = ExpertProfile(
        status=ExpertProfileStatus.DRAFT,
        display_name=name[:200],
        title=(title or None) and title.strip()[:200] or None,
        organization=(organization or None) and organization.strip()[:200] or None,
        bio_short=(bio_short or None) and bio_short.strip()[:500] or None,
        topics=(topics or None) and topics.strip()[:2000] or None,
        created_by_admin_id=admin.id,
    )
    session.add(profile)
    await session.flush()

    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    now = _utcnow()
    invite = ExpertInvite(
        token_hash=hash_invite_token(raw_token),
        purpose=purpose,
        state=ExpertInviteState.SENT if mark_sent else ExpertInviteState.CREATED,
        expires_at=now + timedelta(hours=ttl_hours),
        expert_profile_id=profile.id,
        suggestion_id=suggestion_id,
        created_by_admin_id=admin.id,
        sent_at=now if mark_sent else None,
        audit_note=(audit_note or None) and audit_note.strip()[:500] or None,
    )
    session.add(invite)
    await session.flush()
    return CreatedInvite(invite=invite, token=raw_token, profile=profile)


async def _get_invite_by_token(
    session: AsyncSession, token: str
) -> ExpertInvite | None:
    token = (token or "").strip()
    if not token or len(token) > 200:
        return None
    digest = hash_invite_token(token)
    result = await session.execute(
        select(ExpertInvite).where(ExpertInvite.token_hash == digest)
    )
    return result.scalar_one_or_none()


def _expire_if_needed(invite: ExpertInvite, now: datetime) -> bool:
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if invite.state in {
        ExpertInviteState.CLAIMED,
        ExpertInviteState.REVOKED,
        ExpertInviteState.EXPIRED,
    }:
        return invite.state == ExpertInviteState.EXPIRED
    if expires <= now:
        invite.state = ExpertInviteState.EXPIRED
        return True
    return False


async def mark_invite_opened(
    session: AsyncSession, *, token: str
) -> ExpertInvite:
    invite = await _get_invite_by_token(session, token)
    # Anti-enumeration: identical error for unknown/invalid.
    if invite is None:
        raise ExpertPlatformError("invite_unavailable")
    now = _utcnow()
    if _expire_if_needed(invite, now):
        raise ExpertPlatformError("invite_unavailable")
    if invite.state == ExpertInviteState.REVOKED:
        raise ExpertPlatformError("invite_unavailable")
    if invite.state in {ExpertInviteState.CREATED, ExpertInviteState.SENT}:
        invite.state = ExpertInviteState.OPENED
        invite.opened_at = now
        await session.flush()
    return invite


async def claim_invite(
    session: AsyncSession,
    *,
    token: str,
    telegram_id: int,
) -> tuple[ExpertInvite, ExpertProfile]:
    """Claim start for a Telegram identity — ERA membership is not required."""

    if type(telegram_id) is not int or telegram_id <= 0:
        raise ExpertPlatformError("invalid_telegram_id")

    invite = await _get_invite_by_token(session, token)
    if invite is None:
        raise ExpertPlatformError("invite_unavailable")

    now = _utcnow()
    if _expire_if_needed(invite, now):
        raise ExpertPlatformError("invite_unavailable")
    if invite.state in {ExpertInviteState.REVOKED, ExpertInviteState.EXPIRED}:
        raise ExpertPlatformError("invite_unavailable")
    if invite.state == ExpertInviteState.CLAIMED:
        # Same claimant may re-enter; other telegram ids cannot reuse the token.
        if invite.claimed_telegram_id != telegram_id:
            raise ExpertPlatformError("invite_unavailable")
        profile = await session.get(ExpertProfile, invite.expert_profile_id)
        if profile is None:
            raise ExpertPlatformError("invite_unavailable")
        return invite, profile
    if invite.state not in {
        ExpertInviteState.CREATED,
        ExpertInviteState.SENT,
        ExpertInviteState.OPENED,
    }:
        raise ExpertPlatformError("invite_unavailable")

    profile = await session.get(ExpertProfile, invite.expert_profile_id)
    if profile is None:
        raise ExpertPlatformError("invite_unavailable")

    invite.state = ExpertInviteState.CLAIMED
    invite.claimed_at = now
    invite.claimed_telegram_id = telegram_id
    if invite.opened_at is None:
        invite.opened_at = now
    profile.claimed_telegram_id = telegram_id
    # Bind to an ERA user only when one already exists; never invent membership.
    existing = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )
    if existing is not None:
        profile.user_id = existing.id
    await session.flush()
    return invite, profile


async def revoke_invite(
    session: AsyncSession, *, invite_id: int, admin: User
) -> ExpertInvite:
    invite = await session.get(ExpertInvite, invite_id)
    if invite is None:
        raise ExpertPlatformError("invite_not_found")
    if invite.state == ExpertInviteState.CLAIMED:
        raise ExpertPlatformError("invite_already_claimed")
    if invite.state == ExpertInviteState.REVOKED:
        return invite
    invite.state = ExpertInviteState.REVOKED
    invite.revoked_at = _utcnow()
    invite.revoked_by_admin_id = admin.id
    await session.flush()
    return invite


async def suggest_expert(
    session: AsyncSession,
    *,
    nominator: User,
    expert_name: str,
    field: str,
    why_interesting: str,
    contact_private: str,
    consent_given: bool,
    links: str | None = None,
    now: datetime | None = None,
) -> ExpertSuggestion:
    if not consent_given:
        raise ExpertPlatformError("consent_required")
    name = (expert_name or "").strip()
    sphere = (field or "").strip()
    why = (why_interesting or "").strip()
    contact = (contact_private or "").strip()
    if not name or not sphere or not why or not contact:
        raise ExpertPlatformError("suggestion_fields_required")
    if len(name) > 200 or len(sphere) > 200 or len(contact) > 500:
        raise ExpertPlatformError("suggestion_too_long")
    if len(why) > 4000:
        raise ExpertPlatformError("suggestion_too_long")

    clock = now or _utcnow()
    window_start = clock - SUGGESTION_RATE_WINDOW
    recent = await session.scalar(
        select(func.count())
        .select_from(ExpertSuggestion)
        .where(
            ExpertSuggestion.nominator_user_id == nominator.id,
            ExpertSuggestion.created_at >= window_start,
        )
    )
    if (recent or 0) >= SUGGESTION_RATE_LIMIT:
        raise ExpertPlatformError("suggestion_rate_limited")

    suggestion = ExpertSuggestion(
        nominator_user_id=nominator.id,
        expert_name=name[:200],
        field=sphere[:200],
        why_interesting=why[:4000],
        contact_private=contact[:500],
        links=(links or None) and links.strip()[:2000] or None,
        consent_given=True,
        status=ExpertSuggestionStatus.PENDING,
        submitted_at=clock,
    )
    session.add(suggestion)
    await session.flush()
    return suggestion


def _published_query() -> Select[tuple[ExpertProfile]]:
    return (
        select(ExpertProfile)
        .where(ExpertProfile.status == ExpertProfileStatus.PUBLISHED)
        .order_by(ExpertProfile.published_at.desc(), ExpertProfile.id.desc())
    )


async def list_published_experts(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[ExpertProfile]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    result = await session.execute(_published_query().limit(limit).offset(offset))
    return list(result.scalars().all())


async def get_published_expert(
    session: AsyncSession, expert_id: int
) -> ExpertProfile | None:
    profile = await session.get(ExpertProfile, expert_id)
    if profile is None or profile.status != ExpertProfileStatus.PUBLISHED:
        return None
    return profile


async def publish_expert_profile(
    session: AsyncSession, *, profile_id: int, admin: User
) -> ExpertProfile:
    """Admin-only helper for tests/ops in this slice; not auto-wired to email."""
    del admin  # reserved for future audit identity
    profile = await session.get(ExpertProfile, profile_id)
    if profile is None:
        raise ExpertPlatformError("profile_not_found")
    if profile.status == ExpertProfileStatus.PUBLISHED:
        return profile
    profile.status = ExpertProfileStatus.PUBLISHED
    profile.published_at = _utcnow()
    await session.flush()
    return profile


def tokens_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
