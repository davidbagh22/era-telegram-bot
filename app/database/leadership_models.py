from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
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
    answers_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WeeklyPulseCycle(TimestampMixin, Base):
    """One organization-wide collection window for the existing leadership reports."""

    __tablename__ = "weekly_pulse_cycles"
    __table_args__ = (
        UniqueConstraint("date_from", "date_to", name="uq_weekly_pulse_cycle_period"),
        Index("ix_weekly_pulse_cycles_status_deadline", "status", "deadline_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_count: Mapped[int] = mapped_column(Integer, default=0)
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leader_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    announcement_message_id: Mapped[int | None] = mapped_column(Integer)


class WeeklyPulseSchedule(TimestampMixin, Base):
    """Admin-editable cadence; deployed first with safe Armenia-time defaults."""

    __tablename__ = "weekly_pulse_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    open_weekday: Mapped[int] = mapped_column(Integer, default=4)
    open_time: Mapped[time] = mapped_column(Time, default=time(18, 0))
    deadline_hours: Mapped[int] = mapped_column(Integer, default=48)
    first_reminder_hours: Mapped[int] = mapped_column(Integer, default=24)
    final_reminder_hours: Mapped[int] = mapped_column(Integer, default=4)
    report_weekday: Mapped[int] = mapped_column(Integer, default=6)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Yerevan")


class LeaderChatMembership(TimestampMixin, Base):
    """Roster of the operational Leaders chat; eligibility is separate from ERA role."""

    __tablename__ = "leader_chat_memberships"
    __table_args__ = (
        UniqueConstraint(
            "leader_chat_id", "telegram_user_id", name="uq_leader_chat_membership_user"
        ),
        Index("ix_leader_chat_memberships_eligible", "leader_chat_id", "is_weekly_pulse_eligible"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    leader_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(255), default="")
    membership_status: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_weekly_pulse_eligible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class BroadcastAcknowledgement(TimestampMixin, Base):
    """Private read receipt for an important Leaders chat announcement."""

    __tablename__ = "broadcast_acknowledgements"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_ack_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(
        ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
