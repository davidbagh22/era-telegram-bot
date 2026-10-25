from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ParticipationModeDelivery(TimestampMixin, Base):
    """Durable, idempotent notifications that belong to participation mode.

    Kept separate from ReactivationDelivery because PAUSED/OBSERVER explicitly
    stop the reactivation campaign. This table stores only pause-end and rare
    observer check-ins; it does not create a second participant/lifecycle model.
    """

    __tablename__ = "participation_mode_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_participation_mode_delivery_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
