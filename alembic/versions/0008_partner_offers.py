"""Extend partner initiatives and add applications."""

import sqlalchemy as sa
from alembic import op

revision = "0008_partner_offers"
down_revision = "0007_merge_current_heads"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("partner_initiatives", "point_cost"):
        op.add_column("partner_initiatives", sa.Column("point_cost", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column("partner_initiatives", "quantity"):
        op.add_column("partner_initiatives", sa.Column("quantity", sa.Integer(), nullable=True))
    if not _has_column("partner_initiatives", "instruction"):
        op.add_column("partner_initiatives", sa.Column("instruction", sa.Text(), nullable=True))
    op.create_table(
        "partner_offer_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initiative_id", sa.Integer(), sa.ForeignKey("partner_initiatives.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("initiative_id", "user_id"),
    )
    op.create_index("ix_partner_offer_applications_initiative_id", "partner_offer_applications", ["initiative_id"])
    op.create_index("ix_partner_offer_applications_user_id", "partner_offer_applications", ["user_id"])
    op.create_index("ix_partner_offer_applications_status", "partner_offer_applications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_partner_offer_applications_status", table_name="partner_offer_applications")
    op.drop_index("ix_partner_offer_applications_user_id", table_name="partner_offer_applications")
    op.drop_index("ix_partner_offer_applications_initiative_id", table_name="partner_offer_applications")
    op.drop_table("partner_offer_applications")
    op.drop_column("partner_initiatives", "instruction")
    op.drop_column("partner_initiatives", "quantity")
    op.drop_column("partner_initiatives", "point_cost")
