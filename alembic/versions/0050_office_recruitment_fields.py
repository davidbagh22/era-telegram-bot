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


def upgrade() -> None:
    op.add_column(
        "offices",
        sa.Column("recruitment_mode", sa.String(length=16), nullable=False, server_default="closed"),
    )
    op.add_column("offices", sa.Column("expected_result", sa.Text(), nullable=True))
    op.add_column("offices", sa.Column("workload", sa.String(length=255), nullable=True))
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
        """
    )

    op.add_column(
        "position_applications",
        sa.Column("relevant_experience", sa.Text(), nullable=True),
    )
    op.add_column(
        "position_applications",
        sa.Column("attachment_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("position_applications", "attachment_url")
    op.drop_column("position_applications", "relevant_experience")
    op.drop_constraint("ck_offices_recruitment_mode", "offices", type_="check")
    op.drop_column("offices", "workload")
    op.drop_column("offices", "expected_result")
    op.drop_column("offices", "recruitment_mode")
