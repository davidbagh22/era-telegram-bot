"""Media library item destination type (internal route vs. external link).

DELTA ToR §32-34: internal ERA pages (e.g. the Media Guide) must never be
opened with window.open/Telegram openLink -- that drops Telegram initData.
This column lets the frontend tell internal routes apart from real external
links data-drivenly instead of hardcoding it by `kind`.

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


def upgrade() -> None:
    op.add_column(
        "media_library_items",
        sa.Column("destination_type", sa.String(length=24), nullable=False, server_default="external_url"),
    )
    op.create_index("ix_media_library_items_destination_type", "media_library_items", ["destination_type"])


def downgrade() -> None:
    op.drop_index("ix_media_library_items_destination_type", table_name="media_library_items")
    op.drop_column("media_library_items", "destination_type")
