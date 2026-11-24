"""External event registration URL for partner events."""
from alembic import op
import sqlalchemy as sa

revision = "0067_external_event_registration"
down_revision = "0066_event_signup"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("event_experiences")}
    if "registration_url" not in columns:
        op.add_column(
            "event_experiences",
            sa.Column("registration_url", sa.String(length=500), nullable=True),
        )


def downgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("event_experiences")}
    if "registration_url" in columns:
        op.drop_column("event_experiences", "registration_url")
