from alembic import op
import sqlalchemy as sa


revision = '20260918_0005'
down_revision = '20260917_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('reminders_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('digest_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('reminder_lead_minutes', sa.Integer(), nullable=False, server_default='10'),
    )
    op.create_check_constraint(
        'ck_users_reminder_lead_minutes',
        'users',
        'reminder_lead_minutes BETWEEN 1 AND 1440',
    )
    op.add_column(
        'notes',
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_notes_scheduled_at', 'notes', ['scheduled_at'])
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'note_id',
            sa.String(length=36),
            sa.ForeignKey('notes.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('delivery_key', sa.String(length=255), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('delivery_key', name='uq_notification_deliveries_delivery_key'),
    )
    op.create_index('ix_notification_deliveries_user_id', 'notification_deliveries', ['user_id'])
    op.create_index('ix_notification_deliveries_note_id', 'notification_deliveries', ['note_id'])


def downgrade():
    op.drop_table('notification_deliveries')
    op.drop_index('ix_notes_scheduled_at', table_name='notes')
    op.drop_column('notes', 'scheduled_at')
    op.drop_constraint('ck_users_reminder_lead_minutes', 'users', type_='check')
    op.drop_column('users', 'reminder_lead_minutes')
    op.drop_column('users', 'digest_enabled')
    op.drop_column('users', 'reminders_enabled')
