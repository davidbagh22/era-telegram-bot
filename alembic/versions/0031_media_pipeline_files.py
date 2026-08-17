"""Media pipeline metadata and confirmed attachments.

Revision ID: 0031_media_pipeline_files
Revises: 0030_media_os
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_media_pipeline_files"
down_revision = "0030_media_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_content_items", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("media_content_items", sa.Column("channel_id", sa.String(length=128), nullable=True))
    op.add_column(
        "media_content_items",
        sa.Column("needs_visual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "media_content_items",
        sa.Column("needs_video", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_media_content_items_needs_visual", "media_content_items", ["needs_visual"])
    op.create_index("ix_media_content_items_needs_video", "media_content_items", ["needs_video"])

    op.add_column(
        "media_library_items",
        sa.Column("category", sa.String(length=64), nullable=False, server_default="archive"),
    )
    op.create_index("ix_media_library_items_category", "media_library_items", ["category"])

    op.create_table(
        "media_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("media_type", sa.String(length=24), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=512), nullable=True),
        sa.Column("telegram_file_unique_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("source_chat_id", sa.Integer(), nullable=True),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_chat_id",
            "source_message_id",
            "uploader_id",
            name="uq_media_attachment_chat_message_user",
        ),
    )
    for column in [
        "target_type",
        "target_id",
        "uploader_id",
        "status",
        "media_type",
        "source_chat_id",
        "source_message_id",
        "confirmed_at",
    ]:
        op.create_index(f"ix_media_attachments_{column}", "media_attachments", [column])


def downgrade() -> None:
    op.drop_table("media_attachments")
    op.drop_index("ix_media_library_items_category", table_name="media_library_items")
    op.drop_column("media_library_items", "category")
    op.drop_index("ix_media_content_items_needs_video", table_name="media_content_items")
    op.drop_index("ix_media_content_items_needs_visual", table_name="media_content_items")
    op.drop_column("media_content_items", "needs_video")
    op.drop_column("media_content_items", "needs_visual")
    op.drop_column("media_content_items", "channel_id")
    op.drop_column("media_content_items", "title")
