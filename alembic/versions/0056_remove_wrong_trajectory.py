"""Remove erroneous Trajectory events and stop their campaign."""
from alembic import op
import sqlalchemy as sa

revision = "0056_remove_wrong_trajectory"
down_revision = "0055_trajectory_event_polish"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM events
        WHERE event_date = DATE '2026-10-31'
          AND title ILIKE '%Траектория открытий%'
    """))


def downgrade():
    pass
