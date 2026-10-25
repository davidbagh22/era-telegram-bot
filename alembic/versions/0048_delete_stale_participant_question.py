"""Delete one stale participant question that blocks the admin dashboard.

Revision ID: 0048_delete_stale_question
Revises: 0047_approve_arame_davtyan
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_delete_stale_question"
down_revision = "0047_approve_arame_davtyan"
branch_labels = None
depends_on = None


TARGET_QUESTION_ID = 10
TARGET_USER_ID = 48
TARGET_TEXT = "Т"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_questions
            WHERE id = :question_id
              AND user_id = :user_id
              AND status = 'new'
              AND text = :text
              AND file_id IS NULL
              AND admin_answer IS NULL
              AND answered_by IS NULL
            """
        ),
        {
            "question_id": TARGET_QUESTION_ID,
            "user_id": TARGET_USER_ID,
            "text": TARGET_TEXT,
        },
    )


def downgrade() -> None:
    # Operational cleanup is intentionally not recreated on rollback.
    pass
