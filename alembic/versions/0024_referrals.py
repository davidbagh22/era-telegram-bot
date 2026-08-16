"""referral program

Revision ID: 0024_referrals
Revises: 0023_career_portfolio
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_referrals"
down_revision = "0023_career_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_codes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_referral_codes_code", "referral_codes", ["code"], unique=True)

    op.create_table(
        "referral_relationships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inviter_id", sa.Integer(), nullable=False),
        sa.Column("invitee_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("registration_rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_event_rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_event_id", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("inviter_id <> invitee_id", name="ck_referral_not_self"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invitee_id"),
    )
    op.create_index(
        "ix_referral_relationships_inviter_id",
        "referral_relationships",
        ["inviter_id"],
    )
    op.create_index(
        "ix_referral_relationships_invitee_id",
        "referral_relationships",
        ["invitee_id"],
        unique=True,
    )
    op.create_index(
        "ix_referral_relationships_first_event_id",
        "referral_relationships",
        ["first_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_referral_relationships_first_event_id",
        table_name="referral_relationships",
    )
    op.drop_index(
        "ix_referral_relationships_invitee_id",
        table_name="referral_relationships",
    )
    op.drop_index(
        "ix_referral_relationships_inviter_id",
        table_name="referral_relationships",
    )
    op.drop_table("referral_relationships")
    op.drop_index("ix_referral_codes_code", table_name="referral_codes")
    op.drop_table("referral_codes")
