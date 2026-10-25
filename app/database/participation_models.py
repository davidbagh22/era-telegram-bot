from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ParticipationLifecycle(TimestampMixin, Base):
    """1:1 lifecycle state for an existing User.

    Identity, registration, points and rank continue to live on ``users``.
    This row only stores participation-mode/lifecycle state so we do not create
    a second user source of truth.
    """

    __tablename__ = "participation_lifecycles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    participation_mode: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", nullable=False, index=True
    )
    mode_before_pause: Mapped[str | None] = mapped_column(String(16))
    activity_state: Mapped[str] = mapped_column(
        String(24), default="ADAPTATION", nullable=False, index=True
    )
    state_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_meaningful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    pause_until: Mapped[date | None] = mapped_column(Date, index=True)
    mode_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReactivationCampaign(TimestampMixin, Base):
    __tablename__ = "reactivation_campaigns"
    __table_args__ = (
        UniqueConstraint("campaign_key", name="uq_reactivation_campaign_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    campaign_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    current_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(40))
    inactivity_reason: Mapped[str | None] = mapped_column(Text)


class ReactivationDelivery(TimestampMixin, Base):
    __tablename__ = "reactivation_deliveries"
    __table_args__ = (
        UniqueConstraint("campaign_id", "attempt_no", name="uq_reactivation_campaign_attempt"),
        UniqueConstraint("idempotency_key", name="uq_reactivation_delivery_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("reactivation_campaigns.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
