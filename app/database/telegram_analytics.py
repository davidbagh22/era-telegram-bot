"""Minimal Telegram observations. Message bodies and author identities are never stored."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class TelegramMessageFact(Base):
    __tablename__ = "telegram_message_facts"
    __table_args__ = (Index("ix_telegram_fact_chat_time", "chat_id", "published_at"),)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    media_group_id: Mapped[str | None] = mapped_column(String(100))
    topic_id: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[str] = mapped_column(String(24))
    deleted_state: Mapped[str] = mapped_column(String(16), default="unknown")


class TelegramAnalyticsSource(Base):
    __tablename__ = "telegram_analytics_sources"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    coverage_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(String(80))
