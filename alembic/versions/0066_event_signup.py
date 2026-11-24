"""Optional registration snapshot for event-specific contact details."""
from alembic import op
import sqlalchemy as sa

revision = "0066_event_signup"
down_revision = "0065_project_cover"
branch_labels = None
depends_on = None


def upgrade():
    if "signup" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("event_registrations")}:
        op.add_column("event_registrations", sa.Column("signup", sa.JSON(), nullable=True))


    if "issue_certificate" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("event_experiences")}:
        op.add_column("event_experiences", sa.Column("issue_certificate", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("event_experiences", "issue_certificate")
    op.drop_column("event_registrations", "signup")
