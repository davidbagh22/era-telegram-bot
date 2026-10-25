"""Add data_deletion_requests table — self-service deletion request tracking.

See docs/DATA_INVENTORY.md section 4 and
docs/FINAL_PRODUCTION_ACCEPTANCE.md item #118. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_data_deletion_requests"
down_revision = "0014_consent_log"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("data_deletion_requests"):
        return
    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_data_deletion_requests_user_id", "data_deletion_requests", ["user_id"])
    op.create_index("ix_data_deletion_requests_status", "data_deletion_requests", ["status"])


def downgrade() -> None:
    if not _table_exists("data_deletion_requests"):
        return
    op.drop_index("ix_data_deletion_requests_status", table_name="data_deletion_requests")
    op.drop_index("ix_data_deletion_requests_user_id", table_name="data_deletion_requests")
    op.drop_table("data_deletion_requests")
