"""Add DB timestamp defaults for admin survey tables.

Revision ID: 0036_admin_survey_timestamps
Revises: 0035_organization_integrity
Create Date: 2026-08-18
"""

from alembic import op


revision = "0036_admin_survey_timestamps"
down_revision = "0035_organization_integrity"
branch_labels = None
depends_on = None


_TABLES = ("admin_surveys", "admin_survey_responses")


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bool(bind is not None and bind.dialect.name == "postgresql")


def upgrade() -> None:
    if not _is_postgresql():
        return

    for table_name in _TABLES:
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN created_at SET DEFAULT now()"
        )
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN updated_at SET DEFAULT now()"
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for table_name in _TABLES:
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN updated_at DROP DEFAULT"
        )
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN created_at DROP DEFAULT"
        )
