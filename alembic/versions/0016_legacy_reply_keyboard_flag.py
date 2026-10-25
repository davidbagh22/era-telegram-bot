"""Add users.legacy_reply_keyboard_removed — one-time cleanup migration flag.

The bot's old persistent ReplyKeyboardMarkup main menu (main_menu(), see
app/keyboards/participant.py before this migration) is removed in this same
change. Telegram keeps a previously-sent persistent reply keyboard visible
on the client until the bot explicitly sends ReplyKeyboardRemove() — simply
no longer building one does not clear what a returning user's client
already cached from weeks ago.

Existing rows are backfilled to False ("needs cleanup") via server_default,
since any of them may have received the old keyboard at some point. New
rows created by the app after this ships get True from the ORM's
client-side `default=True` (see User.legacy_reply_keyboard_removed) — they
were never sent that keyboard, so there's nothing to clean up.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_legacy_reply_keyboard_flag"
down_revision = "0015_data_deletion_requests"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "legacy_reply_keyboard_removed"):
        op.add_column(
            "users",
            sa.Column(
                "legacy_reply_keyboard_removed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if _has_column("users", "legacy_reply_keyboard_removed"):
        op.drop_column("users", "legacy_reply_keyboard_removed")
