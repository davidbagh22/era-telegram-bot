"""Add shared Pulse cycles, Leaders roster, and chat workflow metadata.

Revision ID: 0052_pulse_leaders_workcenter
Revises: 0051_era_registration_location
"""

from alembic import op
import sqlalchemy as sa


revision = "0052_pulse_leaders_workcenter"
down_revision = "0051_era_registration_location"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _has_foreign_key(table_name: str, name: str) -> bool:
    if table_name not in _tables():
        return False
    return any(
        constraint.get("name") == name
        for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def upgrade() -> None:
    tables = _tables()
    if "leadership_report_pulses" in tables and "answers_json" not in _columns(
        "leadership_report_pulses"
    ):
        op.add_column(
            "leadership_report_pulses",
            sa.Column("answers_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
    if "leadership_reports" in tables and "pulse_cycle_id" not in _columns("leadership_reports"):
        op.add_column("leadership_reports", sa.Column("pulse_cycle_id", sa.Integer(), nullable=True))
        op.create_index(
            "ix_leadership_reports_pulse_cycle_id", "leadership_reports", ["pulse_cycle_id"]
        )
    if "task_deliveries" in tables and "message_thread_id" not in _columns("task_deliveries"):
        op.add_column(
            "task_deliveries", sa.Column("message_thread_id", sa.Integer(), nullable=True)
        )
    if "task_deliveries" in tables and "reminder_count" not in _columns("task_deliveries"):
        op.add_column(
            "task_deliveries",
            sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "task_deliveries" in tables and "remind_at" not in _columns("task_deliveries"):
        op.add_column(
            "task_deliveries", sa.Column("remind_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "task_deliveries" in tables and "last_card_snapshot" not in _columns("task_deliveries"):
        op.add_column(
            "task_deliveries",
            sa.Column("last_card_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
    if "task_deliveries" in _tables() and not any(
        index["name"] == "ix_task_deliveries_reminder_due"
        for index in sa.inspect(op.get_bind()).get_indexes("task_deliveries")
    ):
        op.create_index(
            "ix_task_deliveries_reminder_due",
            "task_deliveries",
            ["chat_key", "status", "remind_at"],
        )

    if "weekly_pulse_cycles" not in tables:
        op.create_table(
            "weekly_pulse_cycles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("week_number", sa.Integer(), nullable=False),
            sa.Column("date_from", sa.Date(), nullable=False),
            sa.Column("date_to", sa.Date(), nullable=False),
            sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="scheduled"),
            sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("submitted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("report_generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("leader_chat_id", sa.BigInteger(), nullable=True),
            sa.Column("announcement_message_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("date_from", "date_to", name="uq_weekly_pulse_cycle_period"),
        )
        op.create_index("ix_weekly_pulse_cycles_status", "weekly_pulse_cycles", ["status"])
        op.create_index(
            "ix_weekly_pulse_cycles_status_deadline",
            "weekly_pulse_cycles",
            ["status", "deadline_at"],
        )

    if "leadership_reports" in _tables() and not _has_foreign_key(
        "leadership_reports", "fk_leadership_reports_pulse_cycle_id_weekly_pulse_cycles"
    ):
        op.create_foreign_key(
            "fk_leadership_reports_pulse_cycle_id_weekly_pulse_cycles",
            "leadership_reports",
            "weekly_pulse_cycles",
            ["pulse_cycle_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if "weekly_pulse_schedules" not in tables:
        op.create_table(
            "weekly_pulse_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("open_weekday", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("open_time", sa.Time(), nullable=False, server_default="18:00:00"),
            sa.Column("deadline_hours", sa.Integer(), nullable=False, server_default="48"),
            sa.Column("first_reminder_hours", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("final_reminder_hours", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("report_weekday", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Yerevan"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "leader_chat_memberships" not in tables:
        op.create_table(
            "leader_chat_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("leader_chat_id", sa.BigInteger(), nullable=False),
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("membership_status", sa.String(length=16), nullable=False, server_default="member"),
            sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_weekly_pulse_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("leader_chat_id", "telegram_user_id", name="uq_leader_chat_membership_user"),
        )
        op.create_index("ix_leader_chat_memberships_user_id", "leader_chat_memberships", ["user_id"])
        op.create_index("ix_leader_chat_memberships_leader_chat_id", "leader_chat_memberships", ["leader_chat_id"])
        op.create_index("ix_leader_chat_memberships_telegram_user_id", "leader_chat_memberships", ["telegram_user_id"])
        op.create_index("ix_leader_chat_memberships_is_weekly_pulse_eligible", "leader_chat_memberships", ["is_weekly_pulse_eligible"])
        op.create_index(
            "ix_leader_chat_memberships_eligible",
            "leader_chat_memberships",
            ["leader_chat_id", "is_weekly_pulse_eligible"],
        )

    if "broadcast_acknowledgements" not in tables:
        op.create_table(
            "broadcast_acknowledgements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("broadcast_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["broadcast_id"], ["broadcasts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_ack_user"),
        )
        op.create_index(
            "ix_broadcast_acknowledgements_broadcast_id",
            "broadcast_acknowledgements",
            ["broadcast_id"],
        )
        op.create_index(
            "ix_broadcast_acknowledgements_user_id",
            "broadcast_acknowledgements",
            ["user_id"],
        )


def downgrade() -> None:
    tables = _tables()
    if "broadcast_acknowledgements" in tables:
        op.drop_table("broadcast_acknowledgements")
    if "leader_chat_memberships" in tables:
        op.drop_table("leader_chat_memberships")
    if "weekly_pulse_schedules" in tables:
        op.drop_table("weekly_pulse_schedules")
    if "task_deliveries" in tables and "message_thread_id" in _columns("task_deliveries"):
        op.drop_column("task_deliveries", "message_thread_id")
    if "task_deliveries" in tables and "remind_at" in _columns("task_deliveries"):
        if any(
            index["name"] == "ix_task_deliveries_reminder_due"
            for index in sa.inspect(op.get_bind()).get_indexes("task_deliveries")
        ):
            op.drop_index("ix_task_deliveries_reminder_due", table_name="task_deliveries")
        op.drop_column("task_deliveries", "remind_at")
    if "task_deliveries" in tables and "last_card_snapshot" in _columns("task_deliveries"):
        op.drop_column("task_deliveries", "last_card_snapshot")
    if "task_deliveries" in tables and "reminder_count" in _columns("task_deliveries"):
        op.drop_column("task_deliveries", "reminder_count")
    if "leadership_reports" in tables and "pulse_cycle_id" in _columns("leadership_reports"):
        op.drop_index("ix_leadership_reports_pulse_cycle_id", table_name="leadership_reports")
        op.drop_constraint(
            "fk_leadership_reports_pulse_cycle_id_weekly_pulse_cycles",
            "leadership_reports",
            type_="foreignkey",
        )
        op.drop_column("leadership_reports", "pulse_cycle_id")
    if "leadership_report_pulses" in tables and "answers_json" in _columns(
        "leadership_report_pulses"
    ):
        op.drop_column("leadership_report_pulses", "answers_json")
    if "weekly_pulse_cycles" in tables:
        op.drop_table("weekly_pulse_cycles")
