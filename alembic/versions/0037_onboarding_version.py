"""User onboarding version/completion (post-approval onboarding).

Community Verification ToR §35/§47: one-time "Как устроена ЭРА" screen on
first approved Mini App launch, versioned so future copy changes can
re-show it without a data migration.

Revision ID: 0037_onboarding_version
Revises: 0036_community_verification

Idempotent like 0032-0034/0036: 0001_initial calls the current
Base.metadata.create_all(), so a fresh database may already have these
columns by the time this revision runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_onboarding_version"
down_revision = "0036_community_verification"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("users")
    if "onboarding_version" not in columns:
        op.add_column(
            "users",
            sa.Column("onboarding_version", sa.Integer(), nullable=False, server_default="0"),
        )
    if "onboarding_completed_at" not in columns:
        op.add_column(
            "users",
            sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    columns = _columns("users")
    if "onboarding_completed_at" in columns:
        op.drop_column("users", "onboarding_completed_at")
    if "onboarding_version" in columns:
        op.drop_column("users", "onboarding_version")
