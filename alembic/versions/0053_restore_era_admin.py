"""Restore the verified existing ERA admin identity without replacing its history."""
from alembic import op
import sqlalchemy as sa

revision = "0053_restore_era_admin"
down_revision = "0052_pulse_leaders_workcenter"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "community_member_identities" not in sa.inspect(bind).get_table_names():
        return
    bind.execute(sa.text("""
        UPDATE users SET telegram_id = 1593868942, is_archived = FALSE,
            archived_at = NULL, archived_by = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = 10 AND telegram_id = -1593868942000010 AND role = 'admin'
          AND EXISTS (SELECT 1 FROM community_member_identities
                      WHERE telegram_id = 1593868942 AND user_id = 10)
          AND NOT EXISTS (SELECT 1 FROM users WHERE telegram_id = 1593868942)
    """))


def downgrade():
    # Never re-archive a repaired production identity on rollback.
    pass
