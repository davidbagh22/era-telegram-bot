from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class GeneralContentOverride(TimestampMixin, Base):
    """Persistent editor state for one immutable content-pack item."""

    __tablename__ = "general_content_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    override_text: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class GeneralCustomContent(TimestampMixin, Base):
    """Admin-created dates, primarily extra holidays, stored outside deploy files."""

    __tablename__ = "general_custom_content"
    __table_args__ = (
        Index("ix_general_custom_content_date_type", "date_key", "content_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(32), index=True)
    date_key: Mapped[str] = mapped_column(String(10), index=True)
    slot: Mapped[str] = mapped_column(String(16), default="morning")
    title: Mapped[str | None] = mapped_column(String(180))
    text: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class GeneralContentDelivery(TimestampMixin, Base):
    """One scheduled/manual attempt, including terminal skipped/missed states.

    Scheduled idempotency is enforced by the unique idempotency_key. A restart
    can therefore call the same slot again safely without re-sending Telegram.
    """

    __tablename__ = "general_content_deliveries"
    __table_args__ = (
        Index("ix_general_content_delivery_planned", "planned_at"),
        Index("ix_general_content_delivery_content", "content_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    content_id: Mapped[str] = mapped_column(String(100))
    content_type: Mapped[str] = mapped_column(String(32), index=True)
    slot: Mapped[str] = mapped_column(String(16))
    chat_key: Mapped[str] = mapped_column(String(32), default="general")
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(String(500))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
