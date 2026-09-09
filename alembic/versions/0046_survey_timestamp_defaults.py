"""Add DB defaults for admin survey timestamps.

Revision ID: 0046_survey_timestamps
Revises: 0045_confirmation_window
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_survey_timestamps"
down_revision = "0045_confirmation_window"
branch_labels = None
depends_on = None


_TABLES = ("admin_surveys", "admin_survey_responses")
_COLUMNS = ("created_at", "updated_at")


def upgrade() -> None:
    for table_name in _TABLES:
        for column_name in _COLUMNS:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=sa.text("now()"),
            )


def downgrade() -> None:
    for table_name in _TABLES:
        for column_name in _COLUMNS:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=None,
            )
