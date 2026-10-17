"""Add support history without rewriting legacy questions or delivery receipts.

Code rollback leaves this additive schema intact. Downgrade refuses to discard
history or new ticket metadata; archive/export it before a deliberate downgrade.
"""
from alembic import op
import sqlalchemy as sa

revision = '0062_support_threads'
down_revision = '0061_notification_message'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('user_questions')}
    with op.batch_alter_table('user_questions') as batch:
        if 'category' not in columns:
            batch.add_column(sa.Column('category', sa.String(32), nullable=True))
        if 'assigned_to' not in columns:
            batch.add_column(sa.Column('assigned_to', sa.Integer(), nullable=True))
            batch.create_foreign_key('fk_question_assignee', 'users', ['assigned_to'], ['id'])
        if 'waiting_since' not in columns:
            batch.add_column(sa.Column('waiting_since', sa.DateTime(timezone=True), nullable=True))
        if 'thread_revision' not in columns:
            batch.add_column(sa.Column('thread_revision', sa.Integer(), nullable=False, server_default='0'))
        if 'ix_user_questions_assigned_to' not in {index['name'] for index in inspector.get_indexes('user_questions')}:
            batch.create_index('ix_user_questions_assigned_to', ['assigned_to'])
    # The project's first migration uses current metadata on an empty DB.
    # Consequently a clean upgrade can already have the new table/columns.
    if 'support_messages' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('support_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('user_questions.id'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('source_key', sa.String(80), nullable=False, unique=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('file_id', sa.String(255), nullable=True),
        sa.Column('delivery_status', sa.String(24), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_support_messages_question_id', 'support_messages', ['question_id'])
    op.create_index('ix_support_messages_delivery_status', 'support_messages', ['delivery_status'])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT COUNT(*) FROM support_messages')).scalar() or bind.execute(
            sa.text('SELECT COUNT(*) FROM user_questions WHERE category IS NOT NULL OR assigned_to IS NOT NULL OR thread_revision > 0')).scalar():
        raise RuntimeError('Support history exists: roll back code and retain the additive schema')
    op.drop_table('support_messages')
    with op.batch_alter_table('user_questions') as batch:
        batch.drop_index('ix_user_questions_assigned_to')
        batch.drop_constraint('fk_question_assignee', type_='foreignkey')
        for name in ('category', 'assigned_to', 'waiting_since', 'thread_revision'):
            batch.drop_column(name)
