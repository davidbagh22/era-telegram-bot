"""Media OS content plan, delivery, task links and requests.

Revision ID: 0030_media_os
Revises: 0029_community_missions

Like 0029, this revision is intentionally idempotent because 0001_initial
historically calls the current Base.metadata.create_all(), so fresh databases
may already contain current-model tables before this revision is reached.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_media_os"
down_revision = "0029_community_missions"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


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


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    if not _table_exists("media_content_items"):
        op.create_table(
            "media_content_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_key", sa.String(length=160), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("week", sa.Integer(), nullable=True),
            sa.Column("theme", sa.String(length=120), nullable=True),
            sa.Column("rubric", sa.String(length=120), nullable=True),
            sa.Column("kind", sa.String(length=24), nullable=False, server_default="text"),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("poll_question", sa.Text(), nullable=True),
            sa.Column("poll_options", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="scheduled"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("telegram_message_id", sa.Integer(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint("source_key", name="uq_media_content_source_key"),
        )
    for column in [
        "source_kind",
        "source_key",
        "source_type",
        "source_id",
        "week",
        "kind",
        "scheduled_at",
        "status",
        "created_by",
        "published_at",
    ]:
        _create_index_if_missing(
            f"ix_media_content_items_{column}", "media_content_items", [column]
        )

    if not _table_exists("media_channel_deliveries"):
        op.create_table(
            "media_channel_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "content_id",
                sa.Integer(),
                sa.ForeignKey("media_content_items.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("delivery_key", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="claimed"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("telegram_message_id", sa.Integer(), nullable=True),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint("delivery_key", name="uq_media_delivery_key"),
        )
    for column in ["content_id", "delivery_key", "status", "claimed_at", "sent_at"]:
        _create_index_if_missing(
            f"ix_media_channel_deliveries_{column}", "media_channel_deliveries", [column]
        )

    if not _table_exists("media_content_tasks"):
        op.create_table(
            "media_content_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "content_id",
                sa.Integer(),
                sa.ForeignKey("media_content_items.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "task_id",
                sa.Integer(),
                sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("task_kind", sa.String(length=32), nullable=False),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint("content_id", "task_kind", name="uq_media_content_task_kind"),
            sa.UniqueConstraint("task_id", name="uq_media_content_task_task"),
        )
    _create_index_if_missing(
        "ix_media_content_tasks_content_id", "media_content_tasks", ["content_id"]
    )
    _create_index_if_missing("ix_media_content_tasks_task_id", "media_content_tasks", ["task_id"])
    _create_index_if_missing(
        "ix_media_content_tasks_task_kind", "media_content_tasks", ["task_kind"]
    )

    if not _table_exists("media_library_items"):
        op.create_table(
            "media_library_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            _timestamp("created_at"),
            _timestamp("updated_at"),
        )
    _create_index_if_missing("ix_media_library_items_kind", "media_library_items", ["kind"])
    _create_index_if_missing(
        "ix_media_library_items_is_active", "media_library_items", ["is_active"]
    )

    if not _table_exists("media_requests"):
        op.create_table(
            "media_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(length=24), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("package_type", sa.String(length=32), nullable=False),
            sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "content_id",
                sa.Integer(),
                sa.ForeignKey("media_content_items.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint(
                "source_type",
                "source_id",
                "package_type",
                name="uq_media_request_source_package",
            ),
        )
    for column in [
        "source_type",
        "source_id",
        "package_type",
        "requester_id",
        "content_id",
        "status",
    ]:
        _create_index_if_missing(f"ix_media_requests_{column}", "media_requests", [column])

    if not _table_exists("media_chat_notices"):
        op.create_table(
            "media_chat_notices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notice_key", sa.String(length=255), nullable=False),
            sa.Column("notice_kind", sa.String(length=32), nullable=False),
            sa.Column("ref_type", sa.String(length=32), nullable=False),
            sa.Column("ref_id", sa.Integer(), nullable=False),
            sa.Column("telegram_message_id", sa.Integer(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint("notice_key", name="uq_media_chat_notice_key"),
        )
    for column in ["notice_key", "notice_kind", "ref_type", "ref_id", "sent_at"]:
        _create_index_if_missing(
            f"ix_media_chat_notices_{column}", "media_chat_notices", [column]
        )


def downgrade() -> None:
    for table_name in (
        "media_chat_notices",
        "media_requests",
        "media_library_items",
        "media_content_tasks",
        "media_channel_deliveries",
        "media_content_items",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
