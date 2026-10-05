"""Add opt-in flag for the daily book club."""
from alembic import op
import sqlalchemy as sa

revision = "0058_book_club"
down_revision = "0057_pulse_archive"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("book_club_subscribed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_book_club_subscribed", "users", ["book_club_subscribed"])

def downgrade() -> None:
    op.drop_index("ix_users_book_club_subscribed", table_name="users")
    op.drop_column("users", "book_club_subscribed")
