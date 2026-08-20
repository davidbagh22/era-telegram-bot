from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin
from app.database.models import PortfolioItem


class CareerProfile(TimestampMixin, Base):
    __tablename__ = "career_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str | None] = mapped_column(String(180))
    about: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


# Career portfolio is no longer a separate entity/table. Add the richer
# career-only metadata to the already-mapped canonical PortfolioItem so all
# operational achievements, uploaded evidence, certificates and career items
# share one source of truth. Alembic 0038 adds these physical columns and
# migrates/drops the historical career_portfolio_items table.
if "organization" not in PortfolioItem.__table__.c:
    PortfolioItem.organization = mapped_column(String(255), nullable=True)
if "file_name" not in PortfolioItem.__table__.c:
    PortfolioItem.file_name = mapped_column(String(255), nullable=True)
if "include_in_resume" not in PortfolioItem.__table__.c:
    PortfolioItem.include_in_resume = mapped_column(Boolean, default=True, nullable=False)
if "submitted_at" not in PortfolioItem.__table__.c:
    PortfolioItem.submitted_at = mapped_column(DateTime(timezone=True), nullable=True)
if "verified_at" not in PortfolioItem.__table__.c:
    PortfolioItem.verified_at = mapped_column(DateTime(timezone=True), nullable=True)

# Compatibility import name for existing career_service/admin API/tests. It is
# an alias, not a second mapped class and not a second table.
CareerPortfolioItem = PortfolioItem


class RecommendationRequest(TimestampMixin, Base):
    __tablename__ = "recommendation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), default="universal")
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    draft_text: Mapped[str] = mapped_column(Text)
    final_text: Mapped[str | None] = mapped_column(Text)
    document_number: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    verification_token: Mapped[str | None] = mapped_column(String(96), unique=True, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_comment: Mapped[str | None] = mapped_column(Text)
