"""Additive per-user Mini App appearance preferences (accent colour)."""
from alembic import op
import sqlalchemy as sa

revision = "0070_user_ui_preferences"
down_revision = "0069_event_public_listing"
branch_labels = None
depends_on = None

TABLE = "user_ui_preferences"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if TABLE in inspector.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade():
    # Purely cosmetic data in a table nothing else references: safe to drop.
    inspector = sa.inspect(op.get_bind())
    if TABLE in inspector.get_table_names():
        op.drop_table(TABLE)
