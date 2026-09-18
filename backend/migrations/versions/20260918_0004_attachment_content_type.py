from alembic import op
import sqlalchemy as sa


revision = '20260917_0004'
down_revision = '20260917_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'attachments',
        sa.Column(
            'content_type',
            sa.String(length=255),
            nullable=False,
            server_default='application/octet-stream',
        ),
    )


def downgrade():
    op.drop_column('attachments', 'content_type')
