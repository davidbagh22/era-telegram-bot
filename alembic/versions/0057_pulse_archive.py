"""Frozen weekly Pulse archives.

The initial baseline can include the up-to-date SQLAlchemy metadata when
bootstrapping a new database. Avoid recreating those tables/indexes, while
preserving the normal path for older deployments that need this revision.
"""
from alembic import op
import sqlalchemy as sa

revision = "0057_pulse_archive"
down_revision = "0056_remove_wrong_trajectory"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    op.alter_column("tasks", "deadline", existing_type=sa.DateTime(timezone=True), nullable=True)
    tables = _table_names()
    if "weekly_pulse_archives" not in tables:
        op.create_table(
            "weekly_pulse_archives",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("weekly_pulse_cycles.id"), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("docx_data", sa.LargeBinary()),
            sa.Column("pdf_data", sa.LargeBinary()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if "weekly_pulse_participants" not in tables:
        op.create_table(
            "weekly_pulse_participants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("weekly_pulse_cycles.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="not_started"),
            sa.Column("override", sa.String(24)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("cycle_id", "telegram_user_id", name="uq_pulse_participant_cycle_user"),
        )
    if "ix_weekly_pulse_participants_cycle_id" not in _index_names("weekly_pulse_participants"):
        op.create_index(
            "ix_weekly_pulse_participants_cycle_id", "weekly_pulse_participants", ["cycle_id"]
        )
    if "ix_weekly_pulse_archives_cycle_id" not in _index_names("weekly_pulse_archives"):
        op.create_index(
            "ix_weekly_pulse_archives_cycle_id", "weekly_pulse_archives", ["cycle_id"], unique=True
        )


def downgrade():
    # This migration has no ownership marker distinguishing a table created
    # by the baseline from one created by this revision. Never silently drop
    # potentially pre-existing archives or participation records.
    raise NotImplementedError(
        "0057 downgrade is data-destructive; restore from a verified backup instead"
    )
