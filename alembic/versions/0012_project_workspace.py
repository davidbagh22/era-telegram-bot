"""Add project workspace models."""

import sqlalchemy as sa
from alembic import op

revision = "0012_project_workspace"
down_revision = "0011_pending_chat_join_requests"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return index_name in {index["name"] for index in _inspector().get_indexes(table_name)}


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return constraint_name in {
        foreign_key.get("name") for foreign_key in _inspector().get_foreign_keys(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists("tasks", "project_id"):
        op.add_column("tasks", sa.Column("project_id", sa.Integer(), nullable=True))
    if not _index_exists("tasks", "ix_tasks_project_id"):
        op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    if bind.dialect.name != "sqlite" and not _foreign_key_exists(
        "tasks", "fk_tasks_project_id_projects"
    ):
        op.create_foreign_key(
            "fk_tasks_project_id_projects",
            "tasks",
            "projects",
            ["project_id"],
            ["id"],
        )

    if not _table_exists("project_roles"):
        op.create_table(
            "project_roles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("requirements", sa.Text(), nullable=True),
            sa.Column("capacity", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "title", name="uq_project_roles_project_title"),
        )
    if not _index_exists("project_roles", "ix_project_roles_project_id"):
        op.create_index("ix_project_roles_project_id", "project_roles", ["project_id"])
    if not _index_exists("project_roles", "ix_project_roles_status"):
        op.create_index("ix_project_roles_status", "project_roles", ["status"])

    if not _table_exists("project_members"):
        op.create_table(
            "project_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
            sa.Column("application_text", sa.Text(), nullable=True),
            sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column(
                "contribution_status",
                sa.String(length=32),
                server_default="unconfirmed",
                nullable=False,
            ),
            sa.Column("contribution_summary", sa.Text(), nullable=True),
            sa.Column("contribution_role_title", sa.String(length=120), nullable=True),
            sa.Column("contribution_result", sa.Text(), nullable=True),
            sa.Column("contribution_confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("contribution_confirmed_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["contribution_confirmed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["role_id"], ["project_roles.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        )
    if not _index_exists("project_members", "ix_project_members_project_id"):
        op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    if not _index_exists("project_members", "ix_project_members_user_id"):
        op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    if not _index_exists("project_members", "ix_project_members_role_id"):
        op.create_index("ix_project_members_role_id", "project_members", ["role_id"])
    if not _index_exists("project_members", "ix_project_members_status"):
        op.create_index("ix_project_members_status", "project_members", ["status"])
    if not _index_exists("project_members", "ix_project_members_contribution_status"):
        op.create_index(
            "ix_project_members_contribution_status",
            "project_members",
            ["contribution_status"],
        )

    if not _table_exists("project_milestones"):
        op.create_table(
            "project_milestones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("responsible_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["completed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["responsible_id"], ["users.id"]),
            sa.UniqueConstraint("project_id", "sort_order", name="uq_project_milestones_order"),
        )
    if not _index_exists("project_milestones", "ix_project_milestones_project_id"):
        op.create_index("ix_project_milestones_project_id", "project_milestones", ["project_id"])
    if not _index_exists("project_milestones", "ix_project_milestones_deadline"):
        op.create_index("ix_project_milestones_deadline", "project_milestones", ["deadline"])
    if not _index_exists("project_milestones", "ix_project_milestones_responsible_id"):
        op.create_index("ix_project_milestones_responsible_id", "project_milestones", ["responsible_id"])
    if not _index_exists("project_milestones", "ix_project_milestones_status"):
        op.create_index("ix_project_milestones_status", "project_milestones", ["status"])


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists("project_milestones"):
        op.drop_table("project_milestones")
    if _table_exists("project_members"):
        op.drop_table("project_members")
    if _table_exists("project_roles"):
        op.drop_table("project_roles")

    if bind.dialect.name == "sqlite":
        return

    if _foreign_key_exists("tasks", "fk_tasks_project_id_projects"):
        op.drop_constraint("fk_tasks_project_id_projects", "tasks", type_="foreignkey")
    if _index_exists("tasks", "ix_tasks_project_id"):
        op.drop_index("ix_tasks_project_id", table_name="tasks")
    if _column_exists("tasks", "project_id"):
        op.drop_column("tasks", "project_id")
