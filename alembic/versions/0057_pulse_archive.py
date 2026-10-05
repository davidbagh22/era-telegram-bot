"""Frozen weekly Pulse archives."""
from alembic import op
import sqlalchemy as sa
revision = '0057_pulse_archive'
down_revision = '0056_remove_wrong_trajectory'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('tasks', 'deadline', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.create_table('weekly_pulse_archives',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('weekly_pulse_cycles.id'), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('docx_data', sa.LargeBinary()),
        sa.Column('pdf_data', sa.LargeBinary()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('weekly_pulse_participants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cycle_id', sa.Integer(), sa.ForeignKey('weekly_pulse_cycles.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='not_started'),
        sa.Column('override', sa.String(24)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('cycle_id','telegram_user_id',name='uq_pulse_participant_cycle_user'))
    op.create_index('ix_weekly_pulse_participants_cycle_id','weekly_pulse_participants',['cycle_id'])
    op.create_index('ix_weekly_pulse_archives_cycle_id', 'weekly_pulse_archives', ['cycle_id'], unique=True)


def downgrade():
    op.drop_table('weekly_pulse_participants')
    op.drop_table('weekly_pulse_archives')
