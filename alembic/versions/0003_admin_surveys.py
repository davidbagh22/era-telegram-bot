"""Admin analytics surveys."""

import sqlalchemy as sa
from alembic import op

revision = "0003_admin_surveys"
down_revision = "0002_era_v2_foundation"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("admin_surveys"):
        op.create_table(
            "admin_surveys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("questions_json", sa.JSON(), nullable=False),
            sa.Column("audience_type", sa.String(50), nullable=False),
            sa.Column("audience_filter_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("is_monthly", sa.Boolean(), nullable=False),
            sa.Column("last_sent_month", sa.String(7), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_admin_surveys_title", "admin_surveys", ["title"])
        op.create_index("ix_admin_surveys_audience_type", "admin_surveys", ["audience_type"])
        op.create_index("ix_admin_surveys_status", "admin_surveys", ["status"])
        op.create_index("ix_admin_surveys_is_monthly", "admin_surveys", ["is_monthly"])
        op.create_index("ix_admin_surveys_last_sent_month", "admin_surveys", ["last_sent_month"])

    if not _table_exists("admin_survey_responses"):
        op.create_table(
            "admin_survey_responses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("survey_id", sa.Integer(), sa.ForeignKey("admin_surveys.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("answers_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("survey_id", "user_id", name="uq_admin_survey_user_response"),
        )
        op.create_index("ix_admin_survey_responses_survey_id", "admin_survey_responses", ["survey_id"])
        op.create_index("ix_admin_survey_responses_user_id", "admin_survey_responses", ["user_id"])
        op.create_index("ix_admin_survey_responses_status", "admin_survey_responses", ["status"])


def downgrade() -> None:
    if _table_exists("admin_survey_responses"):
        op.drop_table("admin_survey_responses")
    if _table_exists("admin_surveys"):
        op.drop_table("admin_surveys")
