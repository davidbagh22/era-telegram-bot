"""Media library item destination type (internal route vs. external link).

DELTA ToR §32-34: internal ERA pages (e.g. the Media Guide) must never be
opened with window.open/Telegram openLink -- that drops Telegram initData.
This column lets the frontend tell internal routes apart from real external
links data-drivenly instead of hardcoding it by `kind`.

Idempotent like 0030/0031: 0001_initial calls the current
Base.metadata.create_all(), so a fresh database may already have this
column (and its index) by the time this revision runs.

Revision ID: 0032_media_library_dest_type
Revises: 0031_media_pipeline_files
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_media_library_dest_type"
down_revision = "0031_media_pipeline_files"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    if "destination_type" not in _columns("media_library_items"):
        op.add_column(
            "media_library_items",
            sa.Column("destination_type", sa.String(length=24), nullable=False, server_default="external_url"),
        )
    if "ix_media_library_items_destination_type" not in _index_names("media_library_items"):
        op.create_index("ix_media_library_items_destination_type", "media_library_items", ["destination_type"])


def downgrade() -> None:
    if "ix_media_library_items_destination_type" in _index_names("media_library_items"):
        op.drop_index("ix_media_library_items_destination_type", table_name="media_library_items")
    if "destination_type" in _columns("media_library_items"):
        op.drop_column("media_library_items", "destination_type")
