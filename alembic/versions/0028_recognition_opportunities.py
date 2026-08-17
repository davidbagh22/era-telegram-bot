"""Recognition eligibility on the existing Opportunity system.

Revision ID: 0028_recognition_opportunities
Revises: 0027_event_scoring_profile
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_recognition_opportunities"
down_revision = "0027_event_scoring_profile"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    initiative_cols = _columns("partner_initiatives")
    if "opportunity_type" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column(
                "opportunity_type",
                sa.String(length=32),
                nullable=False,
                server_default="external",
            ),
        )
        op.create_index(
            "ix_partner_initiatives_opportunity_type",
            "partner_initiatives",
            ["opportunity_type"],
        )
    if "min_rank" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column("min_rank", sa.String(length=32), nullable=True),
        )
        op.create_index(
            "ix_partner_initiatives_min_rank", "partner_initiatives", ["min_rank"]
        )
    if "eligibility_json" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column(
                "eligibility_json", sa.JSON(), nullable=False, server_default="{}"
            ),
        )
    if "default_award_wording" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column("default_award_wording", sa.Text(), nullable=True),
        )
    if "partner_review_required" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column(
                "partner_review_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "portfolio_item_type" not in initiative_cols:
        op.add_column(
            "partner_initiatives",
            sa.Column("portfolio_item_type", sa.String(length=50), nullable=True),
        )

    app_cols = _columns("partner_offer_applications")
    if "eligibility_snapshot_json" not in app_cols:
        op.add_column(
            "partner_offer_applications",
            sa.Column(
                "eligibility_snapshot_json",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
        )
    if "basis_text" not in app_cols:
        op.add_column(
            "partner_offer_applications",
            sa.Column("basis_text", sa.Text(), nullable=True),
        )
    if "award_wording" not in app_cols:
        op.add_column(
            "partner_offer_applications",
            sa.Column("award_wording", sa.Text(), nullable=True),
        )
    if "issued_at" not in app_cols:
        op.add_column(
            "partner_offer_applications",
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "portfolio_item_id" not in app_cols:
        op.add_column(
            "partner_offer_applications",
            sa.Column(
                "portfolio_item_id",
                sa.Integer(),
                sa.ForeignKey("portfolio_items.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    app_cols = _columns("partner_offer_applications")
    for name in (
        "portfolio_item_id",
        "issued_at",
        "award_wording",
        "basis_text",
        "eligibility_snapshot_json",
    ):
        if name in app_cols:
            with op.batch_alter_table("partner_offer_applications") as batch_op:
                batch_op.drop_column(name)

    initiative_cols = _columns("partner_initiatives")
    if "min_rank" in initiative_cols:
        op.drop_index("ix_partner_initiatives_min_rank", table_name="partner_initiatives")
    if "opportunity_type" in initiative_cols:
        op.drop_index(
            "ix_partner_initiatives_opportunity_type",
            table_name="partner_initiatives",
        )
    for name in (
        "portfolio_item_type",
        "partner_review_required",
        "default_award_wording",
        "eligibility_json",
        "min_rank",
        "opportunity_type",
    ):
        if name in initiative_cols:
            with op.batch_alter_table("partner_initiatives") as batch_op:
                batch_op.drop_column(name)
