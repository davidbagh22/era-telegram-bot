"""Additive expert platform tables (#616 slice): profiles, invites, suggestions."""

from alembic import op
import sqlalchemy as sa

revision = "0071_expert_platform"
down_revision = "0070_user_ui_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "expert_profiles" not in tables:
        op.create_table(
            "expert_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="draft",
            ),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column("organization", sa.String(length=200), nullable=True),
            sa.Column("bio_short", sa.String(length=500), nullable=True),
            sa.Column("topics", sa.Text(), nullable=True),
            sa.Column("claimed_telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "created_by_admin_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.CheckConstraint(
                "status IN ('draft', 'published')",
                name="ck_expert_profiles_status",
            ),
        )
        op.create_index(
            "ix_expert_profiles_status_published",
            "expert_profiles",
            ["status", "published_at"],
        )
        op.create_index(
            "ix_expert_profiles_claimed_telegram_id",
            "expert_profiles",
            ["claimed_telegram_id"],
        )
        op.create_index("ix_expert_profiles_user_id", "expert_profiles", ["user_id"])

    if "expert_suggestions" not in tables:
        op.create_table(
            "expert_suggestions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "nominator_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("expert_name", sa.String(length=200), nullable=False),
            sa.Column("field", sa.String(length=200), nullable=False),
            sa.Column("why_interesting", sa.Text(), nullable=False),
            sa.Column("contact_private", sa.String(length=500), nullable=False),
            sa.Column("links", sa.Text(), nullable=True),
            sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
            sa.Column(
                "submitted_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
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
            sa.CheckConstraint(
                "status IN ('pending', 'approved', 'rejected', 'withdrawn')",
                name="ck_expert_suggestions_status",
            ),
        )
        op.create_index(
            "ix_expert_suggestions_nominator_user_id",
            "expert_suggestions",
            ["nominator_user_id"],
        )
        op.create_index(
            "ix_expert_suggestions_nominator_created",
            "expert_suggestions",
            ["nominator_user_id", "created_at"],
        )

    if "expert_invites" not in tables:
        op.create_table(
            "expert_invites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "purpose",
                sa.String(length=32),
                nullable=False,
                server_default="profile",
            ),
            sa.Column(
                "state",
                sa.String(length=16),
                nullable=False,
                server_default="CREATED",
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "expert_profile_id",
                sa.Integer(),
                sa.ForeignKey("expert_profiles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "suggestion_id",
                sa.Integer(),
                sa.ForeignKey("expert_suggestions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_by_admin_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "revoked_by_admin_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("audit_note", sa.String(length=500), nullable=True),
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
            sa.CheckConstraint(
                "state IN ('CREATED', 'SENT', 'OPENED', 'CLAIMED', 'EXPIRED', 'REVOKED')",
                name="ck_expert_invites_state",
            ),
            sa.CheckConstraint(
                "purpose IN ('profile', 'article', 'event')",
                name="ck_expert_invites_purpose",
            ),
            sa.UniqueConstraint("token_hash", name="uq_expert_invites_token_hash"),
        )
        op.create_index(
            "ix_expert_invites_state_expires",
            "expert_invites",
            ["state", "expires_at"],
        )
        op.create_index(
            "ix_expert_invites_expert_profile_id",
            "expert_invites",
            ["expert_profile_id"],
        )
        op.create_index(
            "ix_expert_invites_created_by_admin_id",
            "expert_invites",
            ["created_by_admin_id"],
        )
        op.create_index(
            "ix_expert_invites_claimed_telegram_id",
            "expert_invites",
            ["claimed_telegram_id"],
        )


def downgrade() -> None:
    # Additive rollout tables; dropping would erase invite audit history.
    raise NotImplementedError(
        "Do not drop expert platform tables without an owner-approved data plan"
    )
