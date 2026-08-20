"""Add per-episode generation for crash-safe system incident alerts.

Revision ID: 0043_incident_generation
Revises: 0042_media_content_pipeline
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0043_incident_generation"
down_revision = "0042_media_content_pipeline"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if not _table_exists("system_incidents"):
        return
    if "notification_generation" not in _column_names("system_incidents"):
        op.add_column(
            "system_incidents",
            sa.Column(
                "notification_generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    if _table_exists("system_incidents") and "notification_generation" in _column_names("system_incidents"):
        op.drop_column("system_incidents", "notification_generation")
