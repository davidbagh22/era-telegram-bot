from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class EraProApplication(TimestampMixin, Base):
    __tablename__ = "era_pro_applications"
    __table_args__ = (
        Index("ix_era_pro_applications_user_created", "user_id", "created_at"),
        Index("ix_era_pro_applications_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted", server_default="submitted")

    motivation: Mapped[str] = mapped_column(Text, nullable=False)
    directions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    target_result: Mapped[str] = mapped_column(Text, nullable=False)
    community_value: Mapped[str] = mapped_column(Text, nullable=False)
    portfolio_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
