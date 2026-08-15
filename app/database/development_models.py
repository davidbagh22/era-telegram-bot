from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class AssessmentDefinition(TimestampMixin, Base):
    __tablename__ = "assessment_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255))
    methodology: Mapped[str] = mapped_column(String(255))
    license: Mapped[str | None] = mapped_column(String(255))
    license_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=5)
    min_age: Mapped[int | None] = mapped_column(Integer)
    recommended_retake_after_days: Mapped[int | None] = mapped_column(Integer)
    construct_type: Mapped[str] = mapped_column(String(32), default="state", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AssessmentVersion(TimestampMixin, Base):
    __tablename__ = "assessment_versions"
    __table_args__ = (UniqueConstraint("definition_id", "version", name="uq_assessment_definition_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("assessment_definitions.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), default="ru")
    translation_source: Mapped[str | None] = mapped_column(Text)
    response_scale_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interpretation_constraints_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scoring_notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AssessmentScale(TimestampMixin, Base):
    __tablename__ = "assessment_scales"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    state_dimension: Mapped[str | None] = mapped_column(String(64), index=True)


class AssessmentQuestion(TimestampMixin, Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_assessment_version_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    scale_code: Mapped[str | None] = mapped_column(String(64))
    reverse_keyed: Mapped[bool] = mapped_column(Boolean, default=False)


class AssessmentOption(TimestampMixin, Base):
    __tablename__ = "assessment_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("assessment_questions.id", ondelete="CASCADE"), index=True)
    value: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)


class AssessmentScoringRule(TimestampMixin, Base):
    __tablename__ = "assessment_scoring_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id", ondelete="CASCADE"), index=True)
    scale_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AssessmentSession(TimestampMixin, Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("assessment_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validity_status: Mapped[str] = mapped_column(String(32), default="preliminary")
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AssessmentAnswer(TimestampMixin, Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_code", name="uq_assessment_session_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True)
    question_code: Mapped[str] = mapped_column(String(64), index=True)
    value_json: Mapped[Any] = mapped_column(JSON)


class AssessmentScore(TimestampMixin, Base):
    __tablename__ = "assessment_scores"
    __table_args__ = (UniqueConstraint("session_id", "scale_code", name="uq_assessment_session_scale"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True)
    scale_code: Mapped[str] = mapped_column(String(64), index=True)
    raw_score: Mapped[float | None] = mapped_column()
    normalized_score: Mapped[float | None] = mapped_column()
    percentile: Mapped[float | None] = mapped_column()
    methodology_version: Mapped[str] = mapped_column(String(64))


class UserVectorProfile(TimestampMixin, Base):
    __tablename__ = "user_vector_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    current_index: Mapped[int | None] = mapped_column(Integer)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    traits_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interests_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    needs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    strengths_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    environment_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    baseline_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_checkin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonthlyCheckin(TimestampMixin, Base):
    __tablename__ = "monthly_checkins"
    __table_args__ = (UniqueConstraint("user_id", "month", name="uq_monthly_checkin_user_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    answers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    index_value: Mapped[int | None] = mapped_column(Integer)
    delta_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    insight_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonthlyContext(TimestampMixin, Base):
    __tablename__ = "monthly_context"

    id: Mapped[int] = mapped_column(primary_key=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("monthly_checkins.id", ondelete="CASCADE"), unique=True, index=True)
    factors_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    development_wants_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class WeeklyPulse(TimestampMixin, Base):
    __tablename__ = "weekly_pulses"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_pulse_user_week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    energy: Mapped[int] = mapped_column(Integer)


class DevelopmentGoal(TimestampMixin, Base):
    __tablename__ = "development_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    title: Mapped[str] = mapped_column(String(255))
    experiment: Mapped[str | None] = mapped_column(Text)
    semantic_tag: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)


class GoalReview(TimestampMixin, Base):
    __tablename__ = "goal_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("development_goals.id", ondelete="CASCADE"), unique=True, index=True)
    result: Mapped[str] = mapped_column(String(32))
    obstacle: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class PersonalInsight(TimestampMixin, Base):
    __tablename__ = "personal_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    checkin_id: Mapped[int | None] = mapped_column(ForeignKey("monthly_checkins.id", ondelete="SET NULL"), index=True)
    text: Mapped[str] = mapped_column(Text)
    semantic_tag: Mapped[str | None] = mapped_column(String(64), index=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class PersonalNote(TimestampMixin, Base):
    __tablename__ = "personal_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    checkin_id: Mapped[int | None] = mapped_column(ForeignKey("monthly_checkins.id", ondelete="SET NULL"), index=True)
    text: Mapped[str] = mapped_column(Text)
    remind_after_months: Mapped[int | None] = mapped_column(Integer)


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    semantic_tag: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    experiment: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class RecommendationHistory(TimestampMixin, Base):
    __tablename__ = "recommendation_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    checkin_id: Mapped[int | None] = mapped_column(ForeignKey("monthly_checkins.id", ondelete="SET NULL"), index=True)
    semantic_tag: Mapped[str] = mapped_column(String(64), index=True)
    family: Mapped[str] = mapped_column(String(64), index=True)
    insight: Mapped[str] = mapped_column(Text)
    experiment: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(String(64))
    completed: Mapped[bool | None] = mapped_column(Boolean)


class AssessmentConsent(TimestampMixin, Base):
    __tablename__ = "assessment_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_version: Mapped[str] = mapped_column(String(64))
    accepted: Mapped[bool] = mapped_column(Boolean)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminVisibilitySetting(TimestampMixin, Base):
    __tablename__ = "admin_visibility_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    summary_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    interests_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    goals_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class AnalyticsSnapshot(TimestampMixin, Base):
    __tablename__ = "analytics_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(32), index=True)
    cohort_key: Mapped[str] = mapped_column(String(128), index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DevelopmentAuditLog(TimestampMixin, Base):
    __tablename__ = "development_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(96), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
