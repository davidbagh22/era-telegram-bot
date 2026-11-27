from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserUiPreference(Base):
    """Per-user Mini App appearance settings kept apart from ``users``.

    A companion row (one per user, created on first save) keeps cosmetic
    preferences out of the hot ``users`` table and its ``updated_at``
    semantics. ``accent_color`` is a canonical lowercase ``#rrggbb`` or NULL
    for the default ERA colour.
    """

    __tablename__ = "user_ui_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
