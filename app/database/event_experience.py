from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class EventExperience(Base):
    """Extended event data used by the Mini App event experience.

    The historical ``events`` table stays untouched so existing events keep
    working. Rich/wizard-only fields live in this one-to-one companion row and
    are optional; old events therefore render with graceful fallbacks.
    """

    __tablename__ = "event_experiences"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    short_description: Mapped[str | None] = mapped_column(Text)
    full_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    end_time: Mapped[time | None] = mapped_column(Time)
    address: Mapped[str | None] = mapped_column(String(500))
    attendance_mode: Mapped[str] = mapped_column(String(24), default="offline")
    organizer: Mapped[str | None] = mapped_column(String(255))
    participant_value: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(255))
    chat_url: Mapped[str | None] = mapped_column(String(500))

    registration_required: Mapped[bool] = mapped_column(Boolean, default=True)
    registration_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waitlist_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    registration_audience: Mapped[str] = mapped_column(String(64), default="all")

    program: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    participant_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reminders: Mapped[list[int]] = mapped_column(JSON, default=list)
    broadcast_targets: Mapped[list[str]] = mapped_column(JSON, default=list)
    broadcast_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    wizard_step: Mapped[int] = mapped_column(Integer, default=1)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    poster_content_type: Mapped[str | None] = mapped_column(String(100))
    poster_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )
