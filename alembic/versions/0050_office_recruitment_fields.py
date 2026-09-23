"""Add unified office recruitment and position-application fields.

Revision ID: 0050_office_recruitment_fields
Revises: 0049_restore_conference_survey
"""

from alembic import op
import sqlalchemy as sa


revision = "0050_office_recruitment_fields"
down_revision = "0049_restore_conference_survey"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _check_constraints(table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    # 0001_initial creates tables from the current Base.metadata. On a clean
    # database that means fields introduced later can already exist before
    # this historical revision is reached. Keep this revision forward-safe
    # for both clean installs and production databases upgraded over time.
    offices_columns = _columns("offices")
    if "recruitment_mode" not in offices_columns:
        op.add_column(
            "offices",
            sa.Column(
                "recruitment_mode",
                sa.String(length=16),
                nullable=False,
                server_default="closed",
            ),
        )
    if "expected_result" not in offices_columns:
        op.add_column("offices", sa.Column("expected_result", sa.Text(), nullable=True))
    if "workload" not in offices_columns:
        op.add_column("offices", sa.Column("workload", sa.String(length=255), nullable=True))

    if "ck_offices_recruitment_mode" not in _check_constraints("offices"):
        op.create_check_constraint(
            "ck_offices_recruitment_mode",
            "offices",
            "recruitment_mode IN ('auto', 'manual', 'closed')",
        )

    # Existing offices never had an explicit auto mode. Preserve admin intent:
    # only offices that were already accepting applications are migrated to an
    # accepting mode; disabled offices stay closed instead of being reopened.
    op.execute(
        """
        UPDATE offices
        SET recruitment_mode = CASE
            WHEN application_enabled = TRUE AND max_holders IS NOT NULL THEN 'auto'
            WHEN application_enabled = TRUE THEN 'manual'
            ELSE 'closed'
        END
        WHERE recruitment_mode IS NULL OR recruitment_mode = 'closed'
        """
    )

    application_columns = _columns("position_applications")
    if "relevant_experience" not in application_columns:
        op.add_column(
            "position_applications",
            sa.Column("relevant_experience", sa.Text(), nullable=True),
        )
    if "attachment_url" not in application_columns:
        op.add_column(
            "position_applications",
            sa.Column("attachment_url", sa.String(length=1000), nullable=True),
        )


def downgrade() -> None:
    application_columns = _columns("position_applications")
    if "attachment_url" in application_columns:
        op.drop_column("position_applications", "attachment_url")
    if "relevant_experience" in application_columns:
        op.drop_column("position_applications", "relevant_experience")

    if "ck_offices_recruitment_mode" in _check_constraints("offices"):
        op.drop_constraint("ck_offices_recruitment_mode", "offices", type_="check")

    offices_columns = _columns("offices")
    if "workload" in offices_columns:
        op.drop_column("offices", "workload")
    if "expected_result" in offices_columns:
        op.drop_column("offices", "expected_result")
    if "recruitment_mode" in offices_columns:
        op.drop_column("offices", "recruitment_mode")
