from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Partner(TimestampMixin, Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="partner", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class PartnerInitiative(TimestampMixin, Base):
    """The single Opportunity catalog object used by the platform.

    ``point_cost`` is retained for backward compatibility with existing
    external offers. For recognition opportunities (certificate/letter) it
    means the minimum accumulated reputation points and is never deducted.
    Eligibility/rank/experience requirements are additive fields on this
    existing model rather than a second Opportunity subsystem.
    """

    __tablename__ = "partner_initiatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    point_cost: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int | None] = mapped_column(Integer)
    instruction: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Points/Ranks/Opportunities master ToR, additive extension of the
    # existing catalog. "external" preserves legacy partner-offer behavior;
    # certificate/letter are reputation-gated recognition opportunities.
    opportunity_type: Mapped[str] = mapped_column(String(32), default="external", index=True)
    min_rank: Mapped[str | None] = mapped_column(String(32), index=True)
    # DELTA ToR §16: "Направление результата" filter -- one of projects/
    # events/volunteering/public_activity/media/leadership/international.
    # Nullable: legacy/external offers predate this and stay uncategorized
    # rather than being force-fit into a guessed bucket.
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    eligibility_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    default_award_wording: Mapped[str | None] = mapped_column(Text)
    partner_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    portfolio_item_type: Mapped[str | None] = mapped_column(String(50))


class PartnerOfferApplication(TimestampMixin, Base):
    __tablename__ = "partner_offer_applications"
    __table_args__ = (UniqueConstraint("initiative_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    initiative_id: Mapped[int] = mapped_column(ForeignKey("partner_initiatives.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)

    # Snapshot only contains public/verified eligibility facts. It never
    # contains Vector answers, private notes or psychological data.
    eligibility_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    basis_text: Mapped[str | None] = mapped_column(Text)
    award_wording: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    portfolio_item_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_items.id"))


class SavedOpportunity(TimestampMixin, Base):
    """A participant's bookmark on a PartnerInitiative."""

    __tablename__ = "saved_opportunities"
    __table_args__ = (UniqueConstraint("initiative_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    initiative_id: Mapped[int] = mapped_column(ForeignKey("partner_initiatives.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class PartnerTask(TimestampMixin, Base):
    __tablename__ = "partner_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    points: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
