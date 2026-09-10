"""Restore the conference speaker survey after accidental archiving.

Revision ID: 0049_restore_conference_survey
Revises: 0048_delete_stale_question
"""

from alembic import op


revision = "0049_restore_conference_survey"
down_revision = "0048_delete_stale_question"
branch_labels = None
depends_on = None


SURVEY_ID = 13
SURVEY_TITLE = "Кого ты хочешь услышать на молодёжной конференции ЭРА?"


def upgrade() -> None:
    # Operational recovery: restore only the known conference survey and only
    # if it is currently archived. Existing responses remain untouched.
    op.execute(
        f"""
        UPDATE admin_surveys
        SET status = 'active',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {SURVEY_ID}
          AND title = '{SURVEY_TITLE}'
          AND status = 'archived'
        """
    )


def downgrade() -> None:
    # Do not re-archive a live survey during a schema rollback.
    pass
