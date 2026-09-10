"""Use bigint for Telegram media chat ids.

Revision ID: 0046_media_chat_ids_bigint
Revises: 0045_confirmation_window
"""

from alembic import op
import sqlalchemy as sa


revision = "0046_media_chat_ids_bigint"
down_revision = "0045_confirmation_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "media_attachments",
        "source_chat_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="source_chat_id::bigint",
    )
    op.alter_column(
        "media_chat_activity",
        "chat_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="chat_id::bigint",
    )


def downgrade() -> None:
    op.alter_column(
        "media_chat_activity",
        "chat_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="chat_id::integer",
    )
    op.alter_column(
        "media_attachments",
        "source_chat_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="source_chat_id::integer",
    )
