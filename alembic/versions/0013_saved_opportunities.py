"""Add saved_opportunities (bookmarks) table."""

import sqlalchemy as sa
from alembic import op

revision = "0013_saved_opportunities"
down_revision = "0012_project_workspace"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("saved_opportunities"):
        return
    op.create_table(
        "saved_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initiative_id", sa.Integer(), sa.ForeignKey("partner_initiatives.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("initiative_id", "user_id"),
    )
    op.create_index("ix_saved_opportunities_initiative_id", "saved_opportunities", ["initiative_id"])
    op.create_index("ix_saved_opportunities_user_id", "saved_opportunities", ["user_id"])


def downgrade() -> None:
    if not _table_exists("saved_opportunities"):
        return
    op.drop_index("ix_saved_opportunities_user_id", table_name="saved_opportunities")
    op.drop_index("ix_saved_opportunities_initiative_id", table_name="saved_opportunities")
    op.drop_table("saved_opportunities")
