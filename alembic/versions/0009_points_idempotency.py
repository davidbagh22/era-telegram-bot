"""Add point transaction idempotency metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0009_points_idempotency"
down_revision = "0008_partner_offers"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("points", "source_type"):
        op.add_column("points", sa.Column("source_type", sa.String(length=64), nullable=True))
    if not _has_column("points", "source_id"):
        op.add_column("points", sa.Column("source_id", sa.Integer(), nullable=True))
    if not _has_column("points", "idempotency_key"):
        op.add_column("points", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    if not _has_index("points", "ix_points_source_type"):
        op.create_index("ix_points_source_type", "points", ["source_type"])
    if not _has_index("points", "ix_points_source_id"):
        op.create_index("ix_points_source_id", "points", ["source_id"])
    if not _has_index("points", "uq_points_idempotency_key"):
        op.create_index("uq_points_idempotency_key", "points", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_points_idempotency_key", table_name="points")
    op.drop_index("ix_points_source_id", table_name="points")
    op.drop_index("ix_points_source_type", table_name="points")
    op.drop_column("points", "idempotency_key")
    op.drop_column("points", "source_id")
    op.drop_column("points", "source_type")
