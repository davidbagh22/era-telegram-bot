from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ReferralCode(TimestampMixin, Base):
    """Stable public invite code owned by one participant."""

    __tablename__ = "referral_codes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(6), unique=True, index=True)


class ReferralRelationship(TimestampMixin, Base):
    """Immutable inviter -> newcomer relationship and its two reward stages."""

    __tablename__ = "referral_relationships"
    __table_args__ = (
        CheckConstraint("inviter_id <> invitee_id", name="ck_referral_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inviter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    invitee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    code: Mapped[str] = mapped_column(String(6))
    registration_rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    first_event_rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    first_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
