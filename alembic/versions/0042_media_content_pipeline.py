"""Normalize Media content pipeline statuses.

Revision ID: 0042_media_content_pipeline
Revises: 0041_leadership_weekly_loop
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_media_content_pipeline"
down_revision = "0041_leadership_weekly_loop"
branch_labels = None
depends_on = None

_ALLOWED = (
    "idea",
    "planned",
    "assigned",
    "in_progress",
    "review",
    "ready",
    "scheduled",
    "published",
    "skipped",
    "failed",
)


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _check_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
        if item.get("name")
    }


def upgrade() -> None:
    if not _table_exists("media_content_items"):
        return
    # Historical builds emitted `draft` and one metadata version defaulted to
    # upper-case PLANNED. Normalize both before enforcing the single pipeline.
    op.execute(
        sa.text(
            "UPDATE media_content_items "
            "SET status = CASE "
            "WHEN lower(status) = 'draft' THEN 'planned' "
            "ELSE lower(status) END"
        )
    )
    allowed_sql = ",".join(f"'{value}'" for value in _ALLOWED)
    op.execute(
        sa.text(
            f"UPDATE media_content_items SET status = 'planned' "
            f"WHERE status NOT IN ({allowed_sql})"
        )
    )
    if "ck_media_content_status" not in _check_names("media_content_items"):
        op.create_check_constraint(
            "ck_media_content_status",
            "media_content_items",
            f"status IN ({allowed_sql})",
        )


def downgrade() -> None:
    if not _table_exists("media_content_items"):
        return
    if "ck_media_content_status" in _check_names("media_content_items"):
        op.drop_constraint(
            "ck_media_content_status",
            "media_content_items",
            type_="check",
        )
