from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class CommunityMemberIdentity(TimestampMixin, Base):
    """Known Telegram identity observed in the managed general community chat.

    This is not a second User. It exists only so Community Verification can
    remember an unregistered Telegram account before that account has a User
    row. Once registration exists, ``user_id`` links back to the canonical User.
    """

    __tablename__ = "community_member_identities"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True)
    general_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_current_member: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    retained_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CommunityVerificationCampaign(TimestampMixin, Base):
    __tablename__ = "community_verification_campaigns"
    __table_args__ = (UniqueConstraint("launch_key", name="uq_community_verification_launch_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    launch_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    group_message_id: Mapped[int | None] = mapped_column(BigInteger)
    group_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CommunityVerificationDelivery(TimestampMixin, Base):
    __tablename__ = "community_verification_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_community_verification_delivery_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("community_verification_campaigns.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    delivery_kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
