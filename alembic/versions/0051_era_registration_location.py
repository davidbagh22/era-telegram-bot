"""Add country and region to ERA participant profiles.

Revision ID: 0051_era_registration_location
Revises: 0050_office_recruitment_fields
"""

from alembic import op
import sqlalchemy as sa


revision = "0051_era_registration_location"
down_revision = "0050_office_recruitment_fields"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "country"):
        op.add_column("users", sa.Column("country", sa.String(length=100), nullable=True))
    if not _has_column("users", "region"):
        op.add_column("users", sa.Column("region", sa.String(length=120), nullable=True))


def downgrade() -> None:
    if _has_column("users", "region"):
        op.drop_column("users", "region")
    if _has_column("users", "country"):
        op.drop_column("users", "country")
