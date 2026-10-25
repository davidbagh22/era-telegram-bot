"""Points/Ranks ToR phase 1 -- category column on PointTransaction

Additive only: nullable `category` String column on `points`, backfilled
from the existing `source_type` values via the same
SOURCE_TYPE_TO_CATEGORY map app/services/points_service.py uses for new
rows, so historical transactions are bucketed too. No other table changes.

Revision ID: 0026_points_category
Revises: 0025_leadership_os_phase1
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_points_category"
down_revision = "0025_leadership_os_phase1"
branch_labels = None
depends_on = None


# Mirrors app.utils.constants.SOURCE_TYPE_TO_CATEGORY at the time this
# migration was written. Kept as a plain literal (not imported) so this
# migration's backfill behavior stays fixed even if that mapping evolves
# later -- the standard Alembic practice of not depending on application
# code that can change out from under a historical migration.
_SOURCE_TYPE_TO_CATEGORY = {
    "registration": "registration",
    "registration_approval": "registration",
    "event_attendance": "event",
    "event_activity": "event",
    "attendance_proof": "event",
    "task_submission": "task",
    "task_completion": "task",
    "project_approval": "project",
    "proposal_points": "project",
    "manual_points": "manual",
    "manual_points_command": "manual",
    "badge_award": "manual",
    "partner_offer": "redemption",
    "reward_redemption": "redemption",
    "auction_win": "redemption",
    "referral_registration": "referral",
    "referral_first_event": "referral",
    "point_transfer": "other",
}


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "category" not in _columns("points"):
        op.add_column("points", sa.Column("category", sa.String(length=32), nullable=True))

    points = sa.table(
        "points",
        sa.column("source_type", sa.String),
        sa.column("category", sa.String),
    )
    bind = op.get_bind()
    for source_type, category in _SOURCE_TYPE_TO_CATEGORY.items():
        bind.execute(
            points.update()
            .where(points.c.source_type == source_type)
            .values(category=category)
        )
    bind.execute(points.update().where(points.c.category.is_(None)).values(category="other"))


def downgrade() -> None:
    if "category" in _columns("points"):
        with op.batch_alter_table("points") as batch_op:
            batch_op.drop_column("category")
