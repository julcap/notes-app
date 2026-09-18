from alembic import op
import sqlalchemy as sa


revision = '20260918_0007'
down_revision = '20260918_0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attachments', sa.Column('object_key', sa.String(length=1024), nullable=True))


def downgrade():
    op.drop_column('attachments', 'object_key')
