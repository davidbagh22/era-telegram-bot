"""Restore TimestampMixin server defaults for migrations 0027-0031.

The ORM's TimestampMixin declares created_at/updated_at with
server_default=func.now(). Migrations 0027, 0029, 0030 and 0031 created the
same columns without that database default. PostgreSQL therefore rejected ORM
inserts that omit the timestamp columns (the ORM correctly expects the server
to populate them). This surfaced during Render startup seeding immediately
after #237.

Revision ID: 0032_timestamp_defaults
Revises: 0031_media_pipeline_files
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_timestamp_defaults"
down_revision = "0031_media_pipeline_files"
branch_labels = None
depends_on = None

_TIMESTAMP_TABLES = (
    "activity_metrics",
    "community_mission_templates",
    "task_squads",
    "task_subtasks",
    "media_content_items",
    "media_channel_deliveries",
    "media_content_tasks",
    "media_library_items",
    "media_requests",
    "media_chat_notices",
    "media_attachments",
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _set_default(table_name: str, column_name: str, default: sa.TextClause | None) -> None:
    # batch_alter_table keeps this migration usable on SQLite dev databases
    # while PostgreSQL emits a direct ALTER COLUMN ... SET/DROP DEFAULT.
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=sa.DateTime(timezone=True),
            server_default=default,
        )


def upgrade() -> None:
    tables = _table_names()
    for table_name in _TIMESTAMP_TABLES:
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        for column_name in ("created_at", "updated_at"):
            if column_name in columns:
                _set_default(table_name, column_name, sa.text("CURRENT_TIMESTAMP"))


def downgrade() -> None:
    tables = _table_names()
    for table_name in _TIMESTAMP_TABLES:
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        for column_name in ("created_at", "updated_at"):
            if column_name in columns:
                _set_default(table_name, column_name, None)
