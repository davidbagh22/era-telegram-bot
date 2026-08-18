from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ChatModerationSetting(TimestampMixin, Base):
    __tablename__ = "chat_moderation_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PendingChatJoinRequest(TimestampMixin, Base):
    __tablename__ = "pending_chat_join_requests"
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_key: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(String(100))


class CommunityVerificationCampaign(TimestampMixin, Base):
    """Community Verification ToR §7: the admin-run "first wave" that gives
    existing (pre-launch) chat members a grace window to register before any
    manual removal decision is even offered. Deliberately just a status +
    window -- segment counts (ToR §19) are computed on read from User /
    CommunityVerificationDelivery / PendingChatJoinRequest, never stored
    redundantly here."""

    __tablename__ = "community_verification_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="not_started", index=True)
    window_hours: Mapped[int] = mapped_column(default=72)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CommunityVerificationDelivery(TimestampMixin, Base):
    """ToR §11-12: per-recipient status for the launch/reminder DM sends.
    Unique on (campaign_id, telegram_id, kind) is the idempotency key itself
    -- ToR §12's `community_verification:{campaign_id}:{telegram_id}:initial`
    maps 1:1 onto (campaign_id, telegram_id, kind='initial')."""

    __tablename__ = "community_verification_deliveries"
    __table_args__ = (UniqueConstraint("campaign_id", "telegram_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("community_verification_campaigns.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
