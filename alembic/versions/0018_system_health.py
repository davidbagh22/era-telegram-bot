"""Add runtime diagnostics, incidents and backup metadata tables.

Additive-only migration for the final production-readiness System layer.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_system_health"
down_revision = "0017_task_deliveries"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("system_diagnostic_runs"):
        op.create_table(
            "system_diagnostic_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_type", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("checks_json", sa.JSON(), nullable=False),
            sa.Column("commit_sha", sa.String(length=64), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_system_diagnostic_runs_run_type", "system_diagnostic_runs", ["run_type"])
        op.create_index("ix_system_diagnostic_runs_status", "system_diagnostic_runs", ["status"])
        op.create_index("ix_system_diagnostic_runs_commit_sha", "system_diagnostic_runs", ["commit_sha"])

    if not _table_exists("system_incidents"):
        op.create_table(
            "system_incidents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dedupe_key", sa.String(length=160), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("check_key", sa.String(length=96), nullable=True),
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("current_commit", sa.String(length=64), nullable=True),
            sa.Column("last_healthy_commit", sa.String(length=64), nullable=True),
            sa.Column("fix_prompt", sa.Text(), nullable=True),
            sa.Column("admin_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("recovery_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("dedupe_key", name="uq_system_incidents_dedupe_key"),
        )
        op.create_index("ix_system_incidents_category", "system_incidents", ["category"])
        op.create_index("ix_system_incidents_severity", "system_incidents", ["severity"])
        op.create_index("ix_system_incidents_status", "system_incidents", ["status"])
        op.create_index("ix_system_incidents_check_key", "system_incidents", ["check_key"])

    if not _table_exists("backup_history"):
        op.create_table(
            "backup_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("backup_key", sa.String(length=160), nullable=False),
            sa.Column("backup_type", sa.String(length=16), nullable=False, server_default="daily"),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("storage_provider", sa.String(length=32), nullable=False, server_default="github-actions"),
            sa.Column("storage_reference", sa.String(length=255), nullable=True),
            sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("restore_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=96), nullable=True),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("backup_key", name="uq_backup_history_backup_key"),
        )
        op.create_index("ix_backup_history_backup_key", "backup_history", ["backup_key"])
        op.create_index("ix_backup_history_backup_type", "backup_history", ["backup_type"])
        op.create_index("ix_backup_history_status", "backup_history", ["status"])


def downgrade() -> None:
    if _table_exists("backup_history"):
        op.drop_index("ix_backup_history_status", table_name="backup_history")
        op.drop_index("ix_backup_history_backup_type", table_name="backup_history")
        op.drop_index("ix_backup_history_backup_key", table_name="backup_history")
        op.drop_table("backup_history")

    if _table_exists("system_incidents"):
        op.drop_index("ix_system_incidents_check_key", table_name="system_incidents")
        op.drop_index("ix_system_incidents_status", table_name="system_incidents")
        op.drop_index("ix_system_incidents_severity", table_name="system_incidents")
        op.drop_index("ix_system_incidents_category", table_name="system_incidents")
        op.drop_table("system_incidents")

    if _table_exists("system_diagnostic_runs"):
        op.drop_index("ix_system_diagnostic_runs_commit_sha", table_name="system_diagnostic_runs")
        op.drop_index("ix_system_diagnostic_runs_status", table_name="system_diagnostic_runs")
        op.drop_index("ix_system_diagnostic_runs_run_type", table_name="system_diagnostic_runs")
        op.drop_table("system_diagnostic_runs")
