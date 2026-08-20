from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class LeadershipReportPulse(TimestampMixin, Base):
    """One-to-one extension of the existing LeadershipReport.

    The report remains the single workflow/engine. This table separates
    immutable system facts from a leader's subjective weekly pulse so facts
    cannot be overwritten by the submit payload.
    """

    __tablename__ = "leadership_report_pulses"
    __table_args__ = (
        UniqueConstraint("report_id", name="uq_leadership_report_pulses_report"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("leadership_reports.id", ondelete="CASCADE"), index=True
    )
    system_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    pace_score: Mapped[int | None] = mapped_column(Integer)
    clarity_score: Mapped[int | None] = mapped_column(Integer)
    load_score: Mapped[int | None] = mapped_column(Integer)
    attention_text: Mapped[str | None] = mapped_column(Text)


class LeadershipFeedback(TimestampMixin, Base):
    """Reviewer feedback/history for one weekly leadership report."""

    __tablename__ = "leadership_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("leadership_reports.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="acknowledged", index=True)
    comment: Mapped[str | None] = mapped_column(Text)
