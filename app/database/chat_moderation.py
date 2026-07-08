from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ChatModerationSetting(TimestampMixin, Base):
    __tablename__ = "chat_moderation_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
