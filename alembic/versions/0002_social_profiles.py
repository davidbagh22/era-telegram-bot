"""Add social profile tables."""

from alembic import op
import sqlalchemy as sa

revision = "0002_social_profiles"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("photo_file_id", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_social_profiles_user_id", "social_profiles", ["user_id"])
    op.create_index("ix_social_profiles_contact_email", "social_profiles", ["contact_email"])
    op.create_table(
        "social_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "url"),
    )
    op.create_index("ix_social_links_user_id", "social_links", ["user_id"])
    op.create_index("ix_social_links_platform", "social_links", ["platform"])
    op.create_index("ix_social_links_is_active", "social_links", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_social_links_is_active", table_name="social_links")
    op.drop_index("ix_social_links_platform", table_name="social_links")
    op.drop_index("ix_social_links_user_id", table_name="social_links")
    op.drop_table("social_links")
    op.drop_index("ix_social_profiles_contact_email", table_name="social_profiles")
    op.drop_index("ix_social_profiles_user_id", table_name="social_profiles")
    op.drop_table("social_profiles")
