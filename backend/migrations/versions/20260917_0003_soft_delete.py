from alembic import op
import sqlalchemy as sa


revision = '20260917_0003'
down_revision = '20260917_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'notes',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_notes_deleted_at', 'notes', ['deleted_at'])


def downgrade():
    op.drop_index('ix_notes_deleted_at', table_name='notes')
    op.drop_column('notes', 'deleted_at')
