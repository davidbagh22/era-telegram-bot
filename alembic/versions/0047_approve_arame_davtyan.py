"""Approve Arame Davtyan's archived pending application.

Revision ID: 0047_approve_arame_davtyan
Revises: 0046_survey_timestamps
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0047_approve_arame_davtyan"
down_revision = "0046_survey_timestamps"
branch_labels = None
depends_on = None


TARGET_USER_ID = 34
TARGET_TELEGRAM_ID = 1889433334
ACTOR_USER_ID = 10


def upgrade() -> None:
    bind = op.get_bind()

    row = bind.execute(
        sa.text(
            """
            SELECT application_status, is_archived
            FROM users
            WHERE id = :user_id AND telegram_id = :telegram_id
            """
        ),
        {"user_id": TARGET_USER_ID, "telegram_id": TARGET_TELEGRAM_ID},
    ).mappings().first()

    if row is None or row["application_status"] == "approved":
        return
    if row["application_status"] not in {"pending", "needs_info"}:
        return

    bind.execute(
        sa.text(
            """
            UPDATE users
            SET application_status = 'approved',
                role = 'participant',
                participation_status = 'new_member',
                is_archived = false,
                archived_at = NULL,
                archived_by = NULL,
                updated_at = now()
            WHERE id = 34 AND telegram_id = 1889433334
              AND application_status IN ('pending', 'needs_info')
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO points (
                user_id, points, reason, approved_by, created_at,
                source_type, source_id, idempotency_key, category
            )
            SELECT
                34, 100, 'Регистрация в боте', 10, now(),
                'registration_approval', 34, 'registration_approval:34', 'community'
            WHERE NOT EXISTS (
                SELECT 1 FROM points
                WHERE idempotency_key = 'registration_approval:34'
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO audit_logs (
                actor_id, action, entity_type, entity_id,
                old_value, new_value, created_at
            )
            VALUES (
                10, 'user.approved', 'user', 34,
                '{"application_status":"pending","is_archived":true}'::json,
                '{"application_status":"approved","is_archived":false}'::json,
                now()
            )
            """
        )
    )


def downgrade() -> None:
    # Operational approval is intentionally not reversed by schema rollback.
    pass
