"""ERA v2 foundation without destructive data changes."""

import sqlalchemy as sa
from alembic import op

revision = "0002_era_v2_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column("users", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("archived_by", sa.Integer()))
    op.create_foreign_key(
        "fk_users_archived_by_users", "users", "users", ["archived_by"], ["id"]
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_is_archived", "users", ["is_archived"])

    op.add_column("events", sa.Column("project_id", sa.Integer()))
    op.create_foreign_key(
        "fk_events_project_id_projects",
        "events",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_index("ix_events_project_id", "events", ["project_id"])

    op.add_column(
        "portfolio_items",
        sa.Column("status", sa.String(32), server_default="verified", nullable=False),
    )
    op.add_column("portfolio_items", sa.Column("submitted_by", sa.Integer()))
    op.add_column("portfolio_items", sa.Column("verified_by", sa.Integer()))
    op.add_column("portfolio_items", sa.Column("admin_comment", sa.Text()))
    op.create_foreign_key(
        "fk_portfolio_submitted_by_users",
        "portfolio_items",
        "users",
        ["submitted_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_portfolio_verified_by_users",
        "portfolio_items",
        "users",
        ["verified_by"],
        ["id"],
    )
    op.create_index("ix_portfolio_items_status", "portfolio_items", ["status"])

    op.add_column(
        "projects",
        sa.Column(
            "form_data",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "projects",
        sa.Column(
            "venue_status",
            sa.String(32),
            server_default="not_requested",
            nullable=False,
        ),
    )
    op.add_column("projects", sa.Column("venue_comment", sa.Text()))
    op.add_column(
        "projects",
        sa.Column(
            "venue_reminder_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column("projects", sa.Column("venue_remind_at", sa.DateTime(timezone=True)))
    op.add_column("projects", sa.Column("proposed_date", sa.Date()))
    op.add_column("projects", sa.Column("proposed_time", sa.Time()))
    op.add_column("projects", sa.Column("submitted_at", sa.DateTime(timezone=True)))

    op.alter_column("tasks", "assignee_id", existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "tasks",
        sa.Column("task_type", sa.String(32), server_default="private", nullable=False),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "audience_filter_json",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "reward_json",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column("tasks", sa.Column("chat_url", sa.String(500)))
    op.add_column("tasks", sa.Column("max_participants", sa.Integer()))
    op.add_column("tasks", sa.Column("remind_at", sa.DateTime(timezone=True)))
    op.add_column(
        "tasks",
        sa.Column("reminder_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_tasks_task_type", "tasks", ["task_type"])

    op.create_table(
        "offices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(150), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column(
            "scope_type", sa.String(32), nullable=False, server_default="community"
        ),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id")),
        sa.Column("direction_id", sa.Integer(), sa.ForeignKey("directions.id")),
        sa.Column(
            "public_contact", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_offices_is_active", "offices", ["is_active"])

    op.create_table(
        "user_offices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=False
        ),
        sa.Column(
            "appointed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("starts_at", sa.Date(), nullable=False),
        sa.Column("ends_at", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "office_id", "starts_at"),
    )
    op.create_index("ix_user_offices_user_id", "user_offices", ["user_id"])
    op.create_index("ix_user_offices_office_id", "user_offices", ["office_id"])
    op.create_index("ix_user_offices_is_active", "user_offices", ["is_active"])

    op.create_table(
        "permission_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("permission", sa.String(100), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "granted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "permission", "scope_type", "scope_id"),
    )
    op.create_index("ix_permission_grants_user_id", "permission_grants", ["user_id"])
    op.create_index(
        "ix_permission_grants_permission", "permission_grants", ["permission"]
    )
    op.create_index(
        "ix_permission_grants_is_active", "permission_grants", ["is_active"]
    )

    op.create_table(
        "chat_greetings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_key", sa.String(50), nullable=False, unique=True),
        sa.Column("chat_id", sa.BigInteger()),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_greetings_is_enabled", "chat_greetings", ["is_enabled"])

    op.create_table(
        "event_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "submission_type", sa.String(32), nullable=False, server_default="text"
        ),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id")),
        sa.Column("certificate_title", sa.String(255)),
        sa.Column(
            "requires_review", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_event_activities_event_id", "event_activities", ["event_id"])
    op.create_index("ix_event_activities_is_active", "event_activities", ["is_active"])

    op.create_table(
        "event_activity_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("event_activities.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("file_id", sa.String(255)),
        sa.Column("file_type", sa.String(32)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("points_awarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("activity_id", "user_id"),
    )
    op.create_index(
        "ix_event_activity_submissions_activity_id",
        "event_activity_submissions",
        ["activity_id"],
    )
    op.create_index(
        "ix_event_activity_submissions_user_id",
        "event_activity_submissions",
        ["user_id"],
    )
    op.create_index(
        "ix_event_activity_submissions_status", "event_activity_submissions", ["status"]
    )

    op.create_table(
        "task_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="joined"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_participants_task_id", "task_participants", ["task_id"])
    op.create_index("ix_task_participants_user_id", "task_participants", ["user_id"])
    op.create_index("ix_task_participants_status", "task_participants", ["status"])

    op.create_table(
        "task_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("file_id", sa.String(255)),
        sa.Column(
            "collaborators_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("admin_comment", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_task_submissions_task_id", "task_submissions", ["task_id"])
    op.create_index("ix_task_submissions_user_id", "task_submissions", ["user_id"])
    op.create_index("ix_task_submissions_status", "task_submissions", ["status"])

    op.create_table(
        "reward_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("point_cost", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer()),
        sa.Column("image_file_id", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_reward_items_is_active", "reward_items", ["is_active"])

    op.create_table(
        "reward_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "reward_id", sa.Integer(), sa.ForeignKey("reward_items.id"), nullable=False
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("points_spent", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("admin_comment", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_reward_redemptions_reward_id", "reward_redemptions", ["reward_id"]
    )
    op.create_index("ix_reward_redemptions_user_id", "reward_redemptions", ["user_id"])
    op.create_index("ix_reward_redemptions_status", "reward_redemptions", ["status"])

    op.create_table(
        "auctions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "audience_filter_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minimum_bid", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("bid_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("winner_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_auctions_status", "auctions", ["status"])

    op.create_table(
        "auction_bids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "auction_id", sa.Integer(), sa.ForeignKey("auctions.id"), nullable=False
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("selected_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("selected_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("auction_id", "user_id"),
    )
    op.create_index("ix_auction_bids_auction_id", "auction_bids", ["auction_id"])
    op.create_index("ix_auction_bids_user_id", "auction_bids", ["user_id"])
    op.create_index("ix_auction_bids_status", "auction_bids", ["status"])


def downgrade() -> None:
    for table in (
        "auction_bids",
        "auctions",
        "reward_redemptions",
        "reward_items",
        "task_submissions",
        "task_participants",
        "event_activity_submissions",
        "event_activities",
        "chat_greetings",
        "permission_grants",
        "user_offices",
        "offices",
    ):
        op.drop_table(table)

    for column in (
        "reminder_count",
        "remind_at",
        "max_participants",
        "chat_url",
        "reward_json",
        "audience_filter_json",
        "task_type",
    ):
        op.drop_column("tasks", column)
    op.alter_column("tasks", "assignee_id", existing_type=sa.Integer(), nullable=False)

    for column in (
        "submitted_at",
        "proposed_time",
        "proposed_date",
        "venue_remind_at",
        "venue_reminder_count",
        "venue_comment",
        "venue_status",
        "current_step",
        "form_data",
    ):
        op.drop_column("projects", column)

    for column in ("admin_comment", "verified_by", "submitted_by", "status"):
        op.drop_column("portfolio_items", column)

    op.drop_constraint("fk_events_project_id_projects", "events", type_="foreignkey")
    op.drop_column("events", "project_id")

    op.drop_constraint("fk_users_archived_by_users", "users", type_="foreignkey")
    for column in ("archived_by", "archived_at", "is_archived", "email"):
        op.drop_column("users", column)
