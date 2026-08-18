"""Media Chat daily activity aggregate.

DELTA ToR §38-41: how many people are actually working in the Media chat,
without archiving any private conversation content -- one row per
(chat_id, date) with a message count and a same-day dedup of author ids.

Revision ID: 0034_media_chat_activity
Revises: 0033_opportunity_category
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_media_chat_activity"
down_revision = "0033_opportunity_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_chat_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("human_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        # TimestampMixin's ORM insert omits these columns and relies on the
        # server default -- 0027-0031 shipped without one and broke Render
        # startup seeding (fixed retroactively in 0032_timestamp_defaults).
        # Set it here from the start instead of repeating that incident.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("chat_id", "activity_date", name="uq_media_chat_activity_chat_date"),
    )
    op.create_index("ix_media_chat_activity_chat_id", "media_chat_activity", ["chat_id"])
    op.create_index("ix_media_chat_activity_activity_date", "media_chat_activity", ["activity_date"])


def downgrade() -> None:
    op.drop_index("ix_media_chat_activity_activity_date", table_name="media_chat_activity")
    op.drop_index("ix_media_chat_activity_chat_id", table_name="media_chat_activity")
    op.drop_table("media_chat_activity")
