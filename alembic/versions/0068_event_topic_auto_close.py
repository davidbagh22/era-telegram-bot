"""Admin-scheduled closing of Telegram event topics."""
from alembic import op
import sqlalchemy as sa

revision = "0068_event_topic_auto_close"
down_revision = "0067_external_event_registration"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_experiences")}
    if "topic_close_at" not in columns:
        op.add_column("event_experiences", sa.Column("topic_close_at", sa.DateTime(timezone=True), nullable=True))
    if "topic_closed_at" not in columns:
        op.add_column("event_experiences", sa.Column("topic_closed_at", sa.DateTime(timezone=True), nullable=True))
    if "topic_close_state" not in columns:
        op.add_column("event_experiences", sa.Column(
            "topic_close_state", sa.String(length=24), nullable=False,
            server_default="open",
        ))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_experiences")}
    for name in ("topic_close_state", "topic_closed_at", "topic_close_at"):
        if name in columns:
            op.drop_column("event_experiences", name)
