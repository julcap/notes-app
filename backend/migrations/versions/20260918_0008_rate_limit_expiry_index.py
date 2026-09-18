from alembic import op


revision = '20260918_0008'
down_revision = '20260918_0007'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_auth_rate_limits_expires_at',
            'auth_rate_limits',
            ['expires_at'],
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            'ix_auth_rate_limits_expires_at',
            table_name='auth_rate_limits',
            postgresql_concurrently=True,
        )
