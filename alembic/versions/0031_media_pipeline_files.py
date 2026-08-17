"""Media pipeline metadata and confirmed attachments.

Revision ID: 0031_media_pipeline_files
Revises: 0030_media_os

Idempotent for both legacy production databases and fresh databases whose
0001_initial created current-model tables/columns through Base.metadata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_media_pipeline_files"
down_revision = "0030_media_os"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    content_columns = _columns("media_content_items")
    if "title" not in content_columns:
        op.add_column("media_content_items", sa.Column("title", sa.String(length=255), nullable=True))
    if "channel_id" not in content_columns:
        op.add_column(
            "media_content_items", sa.Column("channel_id", sa.String(length=128), nullable=True)
        )
    if "needs_visual" not in content_columns:
        op.add_column(
            "media_content_items",
            sa.Column("needs_visual", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "needs_video" not in content_columns:
        op.add_column(
            "media_content_items",
            sa.Column("needs_video", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    _create_index_if_missing(
        "ix_media_content_items_needs_visual", "media_content_items", ["needs_visual"]
    )
    _create_index_if_missing(
        "ix_media_content_items_needs_video", "media_content_items", ["needs_video"]
    )

    library_columns = _columns("media_library_items")
    if "category" not in library_columns:
        op.add_column(
            "media_library_items",
            sa.Column("category", sa.String(length=64), nullable=False, server_default="archive"),
        )
    _create_index_if_missing(
        "ix_media_library_items_category", "media_library_items", ["category"]
    )

    if not _table_exists("media_attachments"):
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
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        _create_index_if_missing(
            f"ix_media_attachments_{column}", "media_attachments", [column]
        )


def downgrade() -> None:
    if _table_exists("media_attachments"):
        op.drop_table("media_attachments")

    if _table_exists("media_library_items"):
        library_columns = _columns("media_library_items")
        if "category" in library_columns:
            if "ix_media_library_items_category" in _index_names("media_library_items"):
                op.drop_index("ix_media_library_items_category", table_name="media_library_items")
            op.drop_column("media_library_items", "category")

    if _table_exists("media_content_items"):
        content_columns = _columns("media_content_items")
        for index_name in (
            "ix_media_content_items_needs_video",
            "ix_media_content_items_needs_visual",
        ):
            if index_name in _index_names("media_content_items"):
                op.drop_index(index_name, table_name="media_content_items")
        for column_name in ("needs_video", "needs_visual", "channel_id", "title"):
            if column_name in content_columns:
                op.drop_column("media_content_items", column_name)
