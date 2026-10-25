"""Points/Ranks ToR phase 2 -- Event Scoring Profile + activity metrics

Additive only:
- new `activity_metrics` table (per-user counters driven by
  app.services.activity_scoring_service).
- `events.scoring_preset` (default "standard") and `events.scoring_metrics`
  (default "[]") -- every existing event keeps its current behavior.
- `event_registrations.role` (default "participant", no bonus) and
  `event_registrations.volunteer_hours` (nullable).

No existing column, value, or award amount changes.

Revision ID: 0027_event_scoring_profile
Revises: 0026_points_category
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_event_scoring_profile"
down_revision = "0026_points_category"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if not _table_exists("activity_metrics"):
        op.create_table(
            "activity_metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("metric_key", sa.String(length=64), nullable=False),
            sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "metric_key", name="uq_activity_metric_user_key"),
        )
        op.create_index("ix_activity_metrics_user_id", "activity_metrics", ["user_id"])
        op.create_index("ix_activity_metrics_metric_key", "activity_metrics", ["metric_key"])

    events_cols = _columns("events")
    if "scoring_preset" not in events_cols:
        op.add_column(
            "events",
            sa.Column("scoring_preset", sa.String(length=32), nullable=False, server_default="standard"),
        )
    if "scoring_metrics" not in events_cols:
        op.add_column(
            "events", sa.Column("scoring_metrics", sa.JSON(), nullable=False, server_default="[]")
        )

    registration_cols = _columns("event_registrations")
    if "role" not in registration_cols:
        op.add_column(
            "event_registrations",
            sa.Column("role", sa.String(length=32), nullable=False, server_default="participant"),
        )
    if "volunteer_hours" not in registration_cols:
        op.add_column("event_registrations", sa.Column("volunteer_hours", sa.Integer(), nullable=True))


def downgrade() -> None:
    registration_cols = _columns("event_registrations")
    if "volunteer_hours" in registration_cols:
        with op.batch_alter_table("event_registrations") as batch_op:
            batch_op.drop_column("volunteer_hours")
    if "role" in registration_cols:
        with op.batch_alter_table("event_registrations") as batch_op:
            batch_op.drop_column("role")

    events_cols = _columns("events")
    if "scoring_metrics" in events_cols:
        with op.batch_alter_table("events") as batch_op:
            batch_op.drop_column("scoring_metrics")
    if "scoring_preset" in events_cols:
        with op.batch_alter_table("events") as batch_op:
            batch_op.drop_column("scoring_preset")

    if _table_exists("activity_metrics"):
        op.drop_table("activity_metrics")
