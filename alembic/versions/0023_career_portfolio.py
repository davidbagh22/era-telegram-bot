"""career portfolio and recommendation documents

Revision ID: 0023_career_portfolio
Revises: 0022_event_attendance_code

career_profiles is also a declarative model on Base.metadata, so 0001's
Base.metadata.create_all() (which reflects whatever models.py currently
defines, not a historical snapshot) already creates it on a from-scratch
upgrade -- guarding each create_table here with _table_exists so this
migration stays a no-op for that table instead of erroring "already
exists". career_portfolio_items/recommendation_requests aren't ORM models
so they're unaffected, but guarded too for consistency with the rest of
this migration set's idempotent-create pattern (see e.g. 0017, 0025).
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_career_portfolio"
down_revision = "0022_event_attendance_code"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("career_profiles"):
        op.create_table(
            "career_profiles",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("headline", sa.String(length=180), nullable=True),
            sa.Column("about", sa.Text(), nullable=True),
            sa.Column("languages", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
        )

    if not _table_exists("career_portfolio_items"):
        op.create_table(
            "career_portfolio_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("item_type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("issued_at", sa.Date(), nullable=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("file_id", sa.String(length=255), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="self_reported"),
            sa.Column("include_in_resume", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("admin_comment", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by", sa.Integer(), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_career_portfolio_items_user_id", "career_portfolio_items", ["user_id"])
        op.create_index("ix_career_portfolio_items_status", "career_portfolio_items", ["status"])
        op.create_index("ix_career_portfolio_items_item_type", "career_portfolio_items", ["item_type"])

    if not _table_exists("recommendation_requests"):
        op.create_table(
            "recommendation_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False, server_default="universal"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
            sa.Column("draft_text", sa.Text(), nullable=False),
            sa.Column("final_text", sa.Text(), nullable=True),
            sa.Column("document_number", sa.String(length=64), nullable=True),
            sa.Column("verification_token", sa.String(length=96), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_number"),
            sa.UniqueConstraint("verification_token"),
        )
        op.create_index("ix_recommendation_requests_user_id", "recommendation_requests", ["user_id"])
        op.create_index("ix_recommendation_requests_status", "recommendation_requests", ["status"])
        op.create_index("ix_recommendation_requests_document_number", "recommendation_requests", ["document_number"], unique=True)
        op.create_index("ix_recommendation_requests_verification_token", "recommendation_requests", ["verification_token"], unique=True)


def downgrade() -> None:
    if _table_exists("recommendation_requests"):
        op.drop_index("ix_recommendation_requests_verification_token", table_name="recommendation_requests")
        op.drop_index("ix_recommendation_requests_document_number", table_name="recommendation_requests")
        op.drop_index("ix_recommendation_requests_status", table_name="recommendation_requests")
        op.drop_index("ix_recommendation_requests_user_id", table_name="recommendation_requests")
        op.drop_table("recommendation_requests")
    if _table_exists("career_portfolio_items"):
        op.drop_index("ix_career_portfolio_items_item_type", table_name="career_portfolio_items")
        op.drop_index("ix_career_portfolio_items_status", table_name="career_portfolio_items")
        op.drop_index("ix_career_portfolio_items_user_id", table_name="career_portfolio_items")
        op.drop_table("career_portfolio_items")
    if _table_exists("career_profiles"):
        op.drop_table("career_profiles")
