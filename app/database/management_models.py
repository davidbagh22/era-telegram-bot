from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class MonthlyGoal(TimestampMixin, Base):
    __tablename__ = "monthly_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="global", index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    target_value: Mapped[int] = mapped_column(Integer, default=0)
    current_value: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class OrganizationContact(TimestampMixin, Base):
    __tablename__ = "organization_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_name: Mapped[str] = mapped_column(String(255), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255))
    second_contact_name: Mapped[str | None] = mapped_column(String(255))
    second_position: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AdminSurvey(TimestampMixin, Base):
    __tablename__ = "admin_surveys"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    questions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    audience_type: Mapped[str] = mapped_column(String(50), default="approved", index=True)
    audience_filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    is_monthly: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_sent_month: Mapped[str | None] = mapped_column(String(7), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AdminSurveyResponse(TimestampMixin, Base):
    __tablename__ = "admin_survey_responses"
    __table_args__ = (UniqueConstraint("survey_id", "user_id", name="uq_admin_survey_user_response"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("admin_surveys.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    answers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
