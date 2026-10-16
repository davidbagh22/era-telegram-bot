"""Retain observed Telegram message IDs with durable delivery acknowledgements.

Additive, nullable metadata only. Code rollback keeps the column; downgrade is
optional and discards message metadata, never notification rows or user data.
"""
from alembic import op
import sqlalchemy as sa

revision = '0061_notification_message'
down_revision = '0060_media_chat_bigint'
branch_labels = None
depends_on = None


def upgrade():
    columns = {field['name'] for field in sa.inspect(op.get_bind()).get_columns('notification_deliveries')}
    if 'message_id' not in columns:
        op.add_column('notification_deliveries', sa.Column('message_id', sa.BigInteger(), nullable=True))


def downgrade():
    columns = {field['name'] for field in sa.inspect(op.get_bind()).get_columns('notification_deliveries')}
    if 'message_id' in columns:
        with op.batch_alter_table('notification_deliveries') as batch:
            batch.drop_column('message_id')
