"""Expert platform (#616) — additive schema for profiles, invites, suggestions.

Draft profiles and suggestion contacts are private; only published profiles
are safe for public/Mini App listing responses.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ExpertProfileStatus:
    DRAFT = "draft"
    PUBLISHED = "published"


class ExpertInviteState:
    CREATED = "CREATED"
    SENT = "SENT"
    OPENED = "OPENED"
    CLAIMED = "CLAIMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ExpertInvitePurpose:
    PROFILE = "profile"
    ARTICLE = "article"
    EVENT = "event"


class ExpertSuggestionStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ExpertProfile(TimestampMixin, Base):
    """Public-facing expert card; drafts never appear in list/detail APIs."""

    __tablename__ = "expert_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_expert_profiles_status",
        ),
        Index("ix_expert_profiles_status_published", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ExpertProfileStatus.DRAFT, server_default="draft"
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio_short: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExpertInvite(TimestampMixin, Base):
    """One-time invite; token is hashed at rest and never logged."""

    __tablename__ = "expert_invites"
    __table_args__ = (
        CheckConstraint(
            "state IN ('CREATED', 'SENT', 'OPENED', 'CLAIMED', 'EXPIRED', 'REVOKED')",
            name="ck_expert_invites_state",
        ),
        CheckConstraint(
            "purpose IN ('profile', 'article', 'event')",
            name="ck_expert_invites_purpose",
        ),
        UniqueConstraint("token_hash", name="uq_expert_invites_token_hash"),
        Index("ix_expert_invites_state_expires", "state", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExpertInvitePurpose.PROFILE, server_default="profile"
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ExpertInviteState.CREATED, server_default="CREATED"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expert_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("expert_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("expert_suggestions.id", ondelete="SET NULL"), nullable=True
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    audit_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ExpertSuggestion(TimestampMixin, Base):
    """Participant nomination; contact fields must never leave admin surfaces."""

    __tablename__ = "expert_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
            name="ck_expert_suggestions_status",
        ),
        Index(
            "ix_expert_suggestions_nominator_created",
            "nominator_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nominator_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expert_name: Mapped[str] = mapped_column(String(200), nullable=False)
    field: Mapped[str] = mapped_column(String(200), nullable=False)
    why_interesting: Mapped[str] = mapped_column(Text, nullable=False)
    # Private: only for admin review after moderation; never in public serializers.
    contact_private: Mapped[str] = mapped_column(String(500), nullable=False)
    links: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ExpertSuggestionStatus.PENDING,
        server_default="pending",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
