"""Unify career and operational portfolio into portfolio_items.

Revision ID: 0038_unify_portfolio
Revises: 0037_community_verification

Fresh installs may already contain the current PortfolioItem columns because the
historical 0001 migration creates current metadata. Older production databases
still have the legacy career table and need its rows migrated. The upgrade
therefore checks physical schema state instead of assuming either shape.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_unify_portfolio"
down_revision = "0037_community_verification"
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
        if column.get("name")
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    # Preserve richer career metadata on the canonical portfolio table. On a
    # fresh database current metadata already defines these columns.
    _add_column_if_missing(
        "portfolio_items", sa.Column("organization", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        "portfolio_items", sa.Column("file_name", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        "portfolio_items",
        sa.Column("include_in_resume", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column_if_missing(
        "portfolio_items", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        "portfolio_items", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)
    )

    if _table_exists("career_portfolio_items"):
        # Copy legacy CareerPortfolioItem rows without preserving their numeric
        # ids: the two historical tables had independent primary-key sequences.
        # The content guard makes retries safe and prevents obvious mirrors.
        op.execute(
            sa.text(
                """
                INSERT INTO portfolio_items (
                    user_id, title, item_type, description, file_id, url,
                    issued_at, status, submitted_by, verified_by, admin_comment,
                    created_at, organization, file_name, include_in_resume,
                    submitted_at, verified_at
                )
                SELECT
                    c.user_id,
                    c.title,
                    c.item_type,
                    c.description,
                    c.file_id,
                    c.url,
                    c.issued_at,
                    c.status,
                    c.user_id,
                    c.verified_by,
                    c.admin_comment,
                    c.created_at,
                    c.organization,
                    c.file_name,
                    c.include_in_resume,
                    c.submitted_at,
                    c.verified_at
                FROM career_portfolio_items c
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM portfolio_items p
                    WHERE p.user_id = c.user_id
                      AND p.item_type = c.item_type
                      AND p.title = c.title
                      AND COALESCE(p.url, '') = COALESCE(c.url, '')
                      AND COALESCE(p.file_id, '') = COALESCE(c.file_id, '')
                )
                """
            )
        )
        # From this revision onward there is one physical portfolio source.
        op.drop_table("career_portfolio_items")


def downgrade() -> None:
    if not _table_exists("career_portfolio_items"):
        op.create_table(
            "career_portfolio_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("item_type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("issued_at", sa.Date(), nullable=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("file_id", sa.String(length=255), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="self_reported"),
            sa.Column("include_in_resume", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("admin_comment", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by", sa.Integer(), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_career_portfolio_items_user_id", "career_portfolio_items", ["user_id"])
        op.create_index("ix_career_portfolio_items_item_type", "career_portfolio_items", ["item_type"])
        op.create_index("ix_career_portfolio_items_status", "career_portfolio_items", ["status"])

    columns = _column_names("portfolio_items")
    if {"organization", "file_name", "include_in_resume", "submitted_at", "verified_at"}.issubset(columns):
        op.execute(
            sa.text(
                """
                INSERT INTO career_portfolio_items (
                    user_id, item_type, title, organization, description, issued_at,
                    url, file_id, file_name, status, include_in_resume, admin_comment,
                    submitted_at, verified_by, verified_at, created_at, updated_at
                )
                SELECT
                    user_id, item_type, title, organization, description, issued_at,
                    url, file_id, file_name, status, include_in_resume, admin_comment,
                    submitted_at, verified_by, verified_at, created_at, created_at
                FROM portfolio_items
                WHERE submitted_by = user_id OR status IN ('self_reported', 'pending', 'rejected')
                """
            )
        )

    for column_name in ("verified_at", "submitted_at", "include_in_resume", "file_name", "organization"):
        if column_name in _column_names("portfolio_items"):
            op.drop_column("portfolio_items", column_name)
