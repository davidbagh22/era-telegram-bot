"""Add chat moderation settings."""

import sqlalchemy as sa
from alembic import op

revision = "0006_chat_moderation"
down_revision = "0005_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_moderation_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_chat_moderation_settings_chat_id", "chat_moderation_settings", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_moderation_settings_chat_id", table_name="chat_moderation_settings")
    op.drop_table("chat_moderation_settings")
