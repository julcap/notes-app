from alembic import op
import sqlalchemy as sa


revision = '20260918_0006'
down_revision = '20260918_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'meeting_shares',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('note_id', sa.String(length=36), sa.ForeignKey('notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permission', sa.String(length=10), nullable=False),
        sa.Column('shared_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("permission IN ('view', 'edit')", name='ck_meeting_shares_permission'),
        sa.UniqueConstraint('note_id', 'user_id', name='uq_meeting_shares_note_user'),
    )
    op.create_index('ix_meeting_shares_note_id', 'meeting_shares', ['note_id'])
    op.create_index('ix_meeting_shares_user_id', 'meeting_shares', ['user_id'])
    op.create_table(
        'sharing_contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.UniqueConstraint('owner_id', 'user_id', name='uq_sharing_contacts_owner_user'),
    )
    op.create_index('ix_sharing_contacts_owner_id', 'sharing_contacts', ['owner_id'])
    op.create_index('ix_sharing_contacts_user_id', 'sharing_contacts', ['user_id'])


def downgrade():
    op.drop_table('sharing_contacts')
    op.drop_table('meeting_shares')
