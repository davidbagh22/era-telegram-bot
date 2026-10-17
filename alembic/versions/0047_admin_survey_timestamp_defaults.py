"""Restore database timestamp defaults for admin surveys.

Revision ID: 0047_survey_timestamp_defaults
Revises: 0046_media_chat_ids_bigint
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0047_survey_timestamp_defaults"
down_revision = "0046_media_chat_ids_bigint"
branch_labels = None
depends_on = None

_TABLES = ("admin_surveys", "admin_survey_responses")


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _set_default(table_name: str, column_name: str, default: sa.TextClause | None) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=default,
        )


def upgrade() -> None:
    tables = _table_names()
    for table_name in _TABLES:
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        for column_name in ("created_at", "updated_at"):
            if column_name in columns:
                _set_default(table_name, column_name, sa.text("CURRENT_TIMESTAMP"))


def downgrade() -> None:
    tables = _table_names()
    for table_name in _TABLES:
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        for column_name in ("created_at", "updated_at"):
            if column_name in columns:
                _set_default(table_name, column_name, None)
