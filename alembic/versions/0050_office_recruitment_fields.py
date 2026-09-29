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


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_check(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspector.get_check_constraints(table_name)
    )


def upgrade() -> None:
    # This migration can be reached from historical schemas where some office
    # recruitment columns already exist. Keep it additive/idempotent so a clean
    # `alembic upgrade heads` and older live databases both converge safely.
    if not _has_column("offices", "recruitment_mode"):
        op.add_column(
            "offices",
            sa.Column(
                "recruitment_mode",
                sa.String(length=16),
                nullable=False,
                server_default="closed",
            ),
        )
    if not _has_column("offices", "expected_result"):
        op.add_column("offices", sa.Column("expected_result", sa.Text(), nullable=True))
    if not _has_column("offices", "workload"):
        op.add_column("offices", sa.Column("workload", sa.String(length=255), nullable=True))
    if not _has_check("offices", "ck_offices_recruitment_mode"):
        op.create_check_constraint(
            "ck_offices_recruitment_mode",
            "offices",
            "recruitment_mode IN ('auto', 'manual', 'closed')",
        )

    # Preserve admin intent: only offices already accepting applications are
    # migrated to an accepting mode; disabled offices stay closed.
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

    if not _has_column("position_applications", "relevant_experience"):
        op.add_column(
            "position_applications",
            sa.Column("relevant_experience", sa.Text(), nullable=True),
        )
    if not _has_column("position_applications", "attachment_url"):
        op.add_column(
            "position_applications",
            sa.Column("attachment_url", sa.String(length=1000), nullable=True),
        )


def downgrade() -> None:
    if _has_column("position_applications", "attachment_url"):
        op.drop_column("position_applications", "attachment_url")
    if _has_column("position_applications", "relevant_experience"):
        op.drop_column("position_applications", "relevant_experience")
    if _has_check("offices", "ck_offices_recruitment_mode"):
        op.drop_constraint("ck_offices_recruitment_mode", "offices", type_="check")
    if _has_column("offices", "workload"):
        op.drop_column("offices", "workload")
    if _has_column("offices", "expected_result"):
        op.drop_column("offices", "expected_result")
    if _has_column("offices", "recruitment_mode"):
        op.drop_column("offices", "recruitment_mode")
